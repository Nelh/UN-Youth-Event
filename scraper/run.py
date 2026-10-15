"""Scrape youth-related UN events and write data/events.json + data/events.js.

Usage:
    python -m scraper.run                 # scrape every source
    python -m scraper.run --only UNICEF   # scrape sources whose name contains "UNICEF"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from .filters import is_youth_related
from .parsers import domain, parse_detail_page, parse_feed, parse_html, parse_ical
from .sources import SOURCES

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MANUAL_FILE = DATA_DIR / "manual_events.json"

USER_AGENT = (
    "Mozilla/5.0 (compatible; UN-Youth-Events-Bot/1.0; "
    "+https://github.com/nelh/un-youth-event)"
)
KEEP_PAST_DAYS = 180       # past events stay listed (under "Past") this long
MAX_DETAIL_FETCHES = 25    # per source, to find dates for undated listings

log = logging.getLogger("scraper")


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "en;q=0.9",
    })
    adapter = requests.adapters.HTTPAdapter(max_retries=requests.adapters.Retry(
        total=2, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504)))
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch(session: requests.Session, url: str) -> str:
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    return resp.text


def scrape_source(session: requests.Session, source: dict, enrich: bool = True) -> list[dict]:
    text = fetch(session, source["url"])
    parser = {"html": parse_html, "ical": parse_ical, "rss": parse_feed}[source["type"]]
    events = parser(text, source["url"])

    youth_focused = source.get("youth_focused", False)
    if not youth_focused:
        events = [e for e in events if is_youth_related(e["title"], e["description"])]

    # Listing pages often show the date only on the event's own page.
    if enrich and source["type"] == "html":
        for ev in [e for e in events if not e["start"]][:MAX_DETAIL_FETCHES]:
            try:
                info = parse_detail_page(fetch(session, ev["url"]), ev["url"])
            except requests.RequestException as exc:
                log.debug("detail fetch failed for %s: %s", ev["url"], exc)
                continue
            for key, value in info.items():
                if value and not ev.get(key):
                    ev[key] = value
            time.sleep(0.5)

    # Without a date we cannot tell an event from any other link on the page.
    events = [e for e in events if e["start"]]
    if not youth_focused:
        events = [e for e in events if is_youth_related(e["title"], e["description"])]
    for ev in events:
        ev["source"] = source["name"]
        ev["source_url"] = source["url"]
    return events


def event_id(ev: dict) -> str:
    key = f"{ev['url'].rstrip('/').lower()}|{ev['start']}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def normalise(ev: dict) -> dict:
    out = dict(ev)
    for key in ("start", "end"):
        if isinstance(out.get(key), date):
            out[key] = out[key].isoformat()
    out.setdefault("location", "")
    out.setdefault("description", "")
    out["organization"] = out.get("organization") or domain(out["url"])
    out["id"] = event_id(out)
    return out


def dedupe(events: list[dict]) -> list[dict]:
    by_key: dict[str, dict] = {}
    for ev in events:
        keys = [ev["url"].rstrip("/").lower() + "|" + ev["start"],
                ev["title"].lower().strip() + "|" + ev["start"]]
        existing = next((by_key[k] for k in keys if k in by_key), None)
        if existing:
            # Keep the richer record.
            for field in ("end", "location", "description"):
                if not existing.get(field) and ev.get(field):
                    existing[field] = ev[field]
            continue
        for k in keys:
            by_key[k] = ev
    unique = {id(e): e for e in by_key.values()}
    return list(unique.values())


def load_previous(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def load_manual() -> list[dict]:
    try:
        items = json.loads(MANUAL_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    for ev in items:
        ev.setdefault("source", "Curated")
        ev.setdefault("source_url", ev["url"])
    return items


def run(only: str | None = None, enrich: bool = True, out_dir: Path = DATA_DIR) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    previous = load_previous(out_dir / "events.json")
    prev_by_source: dict[str, list[dict]] = {}
    for ev in previous.get("events", []):
        prev_by_source.setdefault(ev.get("source_url", ""), []).append(ev)

    sources = [s for s in SOURCES if not only or only.lower() in s["name"].lower()]
    session = make_session()

    def work(source):
        started = time.time()
        try:
            events = scrape_source(session, source, enrich)
            status = {"status": "ok", "count": len(events)}
        except Exception as exc:  # one broken site must not stop the others
            log.warning("%s failed: %s", source["url"], exc)
            events = prev_by_source.get(source["url"], [])  # keep last good data
            status = {"status": "error", "error": str(exc)[:200], "count": len(events)}
        status.update(name=source["name"], url=source["url"], seconds=round(time.time() - started, 1))
        log.info("%-40s %-5s %3d events", source["name"][:40], status["status"], status["count"])
        return events, status

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(work, sources))

    events = [normalise(e) for evs, _ in results for e in evs]
    # With --only, keep the previous data of the sources that were not scraped.
    scraped = {s["url"] for s in sources}
    events += [e for url, evs in prev_by_source.items()
               if url not in scraped and url not in {m.get("source_url") for m in load_manual()}
               for e in evs]
    events += [normalise(e) for e in load_manual()]
    cutoff = (date.today() - timedelta(days=KEEP_PAST_DAYS)).isoformat()
    events = [e for e in dedupe(events) if (e.get("end") or e["start"]) >= cutoff]
    events.sort(key=lambda e: (e["start"], e["title"].lower()))

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event_count": len(events),
        "sources": [status for _, status in results],
        "events": events,
    }
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    (out_dir / "events.json").write_text(payload + "\n", encoding="utf-8")
    # events.js lets index.html work when opened straight from disk (file://).
    (out_dir / "events.js").write_text(f"window.UN_YOUTH_EVENTS = {payload};\n", encoding="utf-8")
    log.info("Wrote %d events to %s", len(events), out_dir)
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="only scrape sources whose name contains this text")
    ap.add_argument("--no-enrich", action="store_true", help="do not open event pages to find missing dates")
    ap.add_argument("--out", type=Path, default=DATA_DIR, help="output directory (default: data/)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    run(args.only, not args.no_enrich, args.out)


if __name__ == "__main__":
    main()
