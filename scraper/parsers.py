"""Turn fetched pages and feeds into raw event dicts.

Every parser returns a list of dicts with the keys:
title, url, start, end, location, description (start/end are ``date`` or None).
The parsers are deliberately generic so that new sources can usually be added
by URL alone, without writing site-specific code.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .dates import find_date_range, parse_ical_date, parse_iso

GENERIC_LINK_TEXT = re.compile(
    r"^(read|learn|see|view|find out|show|load)( more| all| details)?|^more( info)?$|^register|^details$|^watch|^here$|^next|^previous|^share",
    re.IGNORECASE,
)
SKIP_CONTAINERS = {"nav", "header", "footer", "aside", "form"}
SKIP_HREF = re.compile(r"^(mailto:|tel:|javascript:|#)|facebook\.com|twitter\.com|x\.com/|linkedin\.com|instagram\.com|youtube\.com/(?:@|c/|channel|user)|whatsapp", re.IGNORECASE)


def clean(text: str | None, limit: int | None = None) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return text


def _event(title, url, start=None, end=None, location="", description=""):
    return {
        "title": clean(title, 300),
        "url": url,
        "start": start,
        "end": end,
        "location": clean(location, 200),
        "description": clean(description, 400),
    }


# --------------------------------------------------------------------------
# schema.org JSON-LD
# --------------------------------------------------------------------------

def _walk_jsonld(node):
    if isinstance(node, list):
        for item in node:
            yield from _walk_jsonld(item)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "itemListElement", "item", "subEvent", "mainEntity"):
            if key in node:
                yield from _walk_jsonld(node[key])


def _jsonld_location(loc) -> str:
    if isinstance(loc, list):
        return ", ".join(filter(None, (_jsonld_location(x) for x in loc)))
    if isinstance(loc, str):
        return loc
    if isinstance(loc, dict):
        parts = [loc.get("name")]
        addr = loc.get("address")
        if isinstance(addr, str):
            parts.append(addr)
        elif isinstance(addr, dict):
            parts.append(addr.get("addressLocality"))
            parts.append(addr.get("addressCountry") if isinstance(addr.get("addressCountry"), str) else None)
        if loc.get("@type") == "VirtualLocation" and not loc.get("name"):
            parts.append("Online")
        return ", ".join(p for p in parts if p)
    return ""


def parse_jsonld(soup: BeautifulSoup, base_url: str) -> list[dict]:
    events = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _walk_jsonld(data):
            types = node.get("@type", [])
            types = [types] if isinstance(types, str) else types
            if not any(isinstance(t, str) and t.endswith("Event") for t in types):
                continue
            title = node.get("name") or node.get("headline")
            if not title:
                continue
            events.append(_event(
                title,
                urljoin(base_url, node.get("url") or base_url),
                parse_iso(node.get("startDate")),
                parse_iso(node.get("endDate")),
                _jsonld_location(node.get("location")),
                node.get("description") or "",
            ))
    return events


# --------------------------------------------------------------------------
# iCalendar
# --------------------------------------------------------------------------

def _ical_unescape(value: str) -> str:
    return (value.replace("\\n", " ").replace("\\N", " ")
            .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\"))


def parse_ical(text: str, base_url: str) -> list[dict]:
    # Unfold continuation lines (RFC 5545 §3.1).
    text = re.sub(r"\r?\n[ \t]", "", text)
    events, current = [], None
    for line in text.splitlines():
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            if current.get("SUMMARY"):
                events.append(_event(
                    current["SUMMARY"],
                    current.get("URL") or base_url,
                    parse_ical_date(current.get("DTSTART")),
                    parse_ical_date(current.get("DTEND")),
                    current.get("LOCATION", ""),
                    current.get("DESCRIPTION", ""),
                ))
            current = None
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            current[key.split(";", 1)[0].upper()] = _ical_unescape(value)
    # All-day DTEND is exclusive; it is good enough as a display end date.
    for ev in events:
        if ev["end"] and ev["start"] and ev["end"] <= ev["start"]:
            ev["end"] = None
    return events


# --------------------------------------------------------------------------
# RSS / Atom
# --------------------------------------------------------------------------

def parse_feed(text: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(text, "xml")
    events = []
    for item in soup.find_all(["item", "entry"]):
        title = item.find("title")
        link = item.find("link")
        url = ""
        if link is not None:
            url = link.get("href") or link.get_text(strip=True)
        desc_el = item.find(["description", "summary", "content"])
        desc = BeautifulSoup(desc_el.get_text(), "lxml").get_text(" ") if desc_el else ""
        title_text = title.get_text(strip=True) if title else ""
        # Feed publication dates are not event dates: only use dates in the text.
        start, end = find_date_range(f"{title_text} {desc}")
        events.append(_event(title_text, urljoin(base_url, url), start, end, "", desc))
    return [e for e in events if e["title"]]


# --------------------------------------------------------------------------
# Generic HTML listing pages
# --------------------------------------------------------------------------

def _in_skipped_container(el) -> bool:
    for parent in el.parents:
        if parent.name in SKIP_CONTAINERS:
            return True
        role = parent.get("role") if hasattr(parent, "get") else None
        if role in ("navigation", "banner", "contentinfo", "menu"):
            return True
    return False


def _is_title_link(a) -> bool:
    text = clean(a.get_text(" "))
    return len(text) >= 10 and not GENERIC_LINK_TEXT.match(text)


def _card_title(card, link) -> str:
    heading = card.find(["h1", "h2", "h3", "h4", "h5"])
    if heading and len(clean(heading.get_text(" "))) >= 6:
        return clean(heading.get_text(" "))
    return clean(link.get_text(" "))


def _card_dates(card):
    for t in card.find_all("time"):
        start = parse_iso(t.get("datetime")) or find_date_range(t.get_text(" "))[0]
        if start:
            times = card.find_all("time")
            end = parse_iso(times[-1].get("datetime")) if len(times) > 1 else None
            return start, (end if end and end > start else None)
    return find_date_range(card.get_text(" "))


def parse_html_listing(soup: BeautifulSoup, base_url: str, max_depth: int = 6) -> list[dict]:
    """Find event "cards" on a listing page.

    For each title-like link, climb to the smallest ancestor that contains a
    date, stopping before the ancestor starts to hold other title links (at
    that point we would be looking at the list, not the card).
    """
    events, seen = [], set()
    for a in soup.select("a[href]"):
        href = a["href"].strip()
        if SKIP_HREF.search(href) or not _is_title_link(a) or _in_skipped_container(a):
            continue
        url = urljoin(base_url, href).split("#")[0]
        if url in seen or url.rstrip("/") == base_url.rstrip("/"):
            continue

        card, start, end = a, None, None
        el = a
        for _ in range(max_depth):
            el = el.parent
            if el is None or el.name in ("body", "html", "main", "[document]"):
                break
            other_titles = {
                urljoin(base_url, x["href"]).split("#")[0]
                for x in el.select("a[href]") if _is_title_link(x)
            } - {url}
            if other_titles:
                break
            card = el
            start, end = _card_dates(el)
            if start:
                break

        seen.add(url)
        title = _card_title(card, a) if card is not a else clean(a.get_text(" "))
        text = clean(card.get_text(" "))
        description = text.replace(title, "", 1).strip(" -–|·")
        loc = card.find(class_=re.compile("location|venue|place", re.I))
        events.append(_event(title, url, start, end, loc.get_text(" ") if loc else "", description))
    return events


def parse_html(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    events = parse_jsonld(soup, base_url)
    known = {e["url"] for e in events}
    events += [e for e in parse_html_listing(soup, base_url) if e["url"] not in known]
    return events


# --------------------------------------------------------------------------
# Event detail pages (used to fill in missing dates)
# --------------------------------------------------------------------------

def parse_detail_page(html: str, url: str) -> dict:
    """Return whatever we can learn about one event from its own page."""
    soup = BeautifulSoup(html, "lxml")
    info: dict = {}
    for ev in parse_jsonld(soup, url):
        if ev["start"]:
            info.update({k: v for k, v in ev.items() if v and k != "url"})
            return info

    meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
    if meta and meta.get("content"):
        info["description"] = clean(meta["content"], 400)

    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    start, end = None, None
    for t in main.find_all("time"):
        start = parse_iso(t.get("datetime"))
        if start:
            break
    if not start:
        start, end = find_date_range(main.get_text(" "))
    if start:
        info["start"], info["end"] = start, end
    return info


def domain(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.")
