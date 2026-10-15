"""Date helpers: find event dates and date ranges in free text."""

from __future__ import annotations

import re
from datetime import date, datetime

MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

_M = r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\.?"
_D = r"(\d{1,2})(?:st|nd|rd|th)?"
_Y = r"(\d{4})"
_DASH = r"\s*(?:-|–|—|to|until)\s*"

# Each pattern maps its groups to (start, end) dates.
_PATTERNS: list[tuple[re.Pattern, callable]] = []


def _pattern(regex):
    def register(fn):
        _PATTERNS.append((re.compile(regex, re.IGNORECASE), fn))
        return fn
    return register


def _mk(y, m, d) -> date | None:
    try:
        return date(int(y), MONTHS[m.lower()] if isinstance(m, str) and not m.isdigit() else int(m), int(d))
    except (ValueError, KeyError):
        return None


@_pattern(r"\b(\d{4})-(\d{2})-(\d{2})(?:[T ][\d:.]+(?:Z|[+-]\d{2}:?\d{2})?)?(?:" + _DASH + r"(\d{4})-(\d{2})-(\d{2}))?")
def _iso(g):
    start = _mk(g[0], g[1], g[2])
    end = _mk(g[3], g[4], g[5]) if g[3] else None
    return start, end


# "30 March - 2 April 2026"
@_pattern(r"\b" + _D + r"\s+" + _M + r",?(?:\s+" + _Y + r")?" + _DASH + _D + r"\s+" + _M + r",?\s+" + _Y)
def _d_m_d_m_y(g):
    end = _mk(g[5], g[4], g[3])
    start = _mk(g[2] or g[5], g[1], g[0])
    return start, end


# "14-16 April 2026"
@_pattern(r"\b" + _D + _DASH + _D + r"\s+" + _M + r",?\s+" + _Y)
def _d_d_m_y(g):
    return _mk(g[3], g[2], g[0]), _mk(g[3], g[2], g[1])


# "March 30 - April 2, 2026"
@_pattern(r"\b" + _M + r"\s+" + _D + _DASH + _M + r"\s+" + _D + r",?\s+" + _Y)
def _m_d_m_d_y(g):
    return _mk(g[4], g[0], g[1]), _mk(g[4], g[2], g[3])


# "April 14-16, 2026"
@_pattern(r"\b" + _M + r"\s+" + _D + _DASH + _D + r",?\s+" + _Y)
def _m_d_d_y(g):
    return _mk(g[3], g[0], g[1]), _mk(g[3], g[0], g[2])


# "14 April 2026", "Tuesday, 14 April 2026"
@_pattern(r"\b" + _D + r"\s+(?:of\s+)?" + _M + r",?\s+" + _Y)
def _d_m_y(g):
    return _mk(g[2], g[1], g[0]), None


# "April 14, 2026"
@_pattern(r"\b" + _M + r"\s+" + _D + r",?\s+" + _Y)
def _m_d_y(g):
    return _mk(g[2], g[0], g[1]), None


def find_date_range(text: str | None) -> tuple[date | None, date | None]:
    """Return the first (start, end) date range found in ``text``.

    The earliest match in the text wins; on a tie the longest match (usually a
    full range) wins. ``end`` is None for single-day dates.
    """
    if not text:
        return None, None
    best = None
    for regex, build in _PATTERNS:
        for m in regex.finditer(text):
            start, end = build(m.groups())
            if not start:
                continue
            key = (m.start(), -(m.end() - m.start()))
            if best is None or key < best[0]:
                best = (key, start, end)
            break  # only the first match per pattern matters
    if not best:
        return None, None
    _, start, end = best
    if end and end < start:
        end = None
    if end == start:
        end = None
    return start, end


def parse_iso(value: str | None) -> date | None:
    """Parse ISO-8601 dates/datetimes (as used by <time datetime> and JSON-LD)."""
    if not value:
        return None
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    start, _ = find_date_range(value)
    return start


def parse_ical_date(value: str | None) -> date | None:
    """Parse iCalendar DATE / DATE-TIME values such as 20260414 or 20260414T100000Z."""
    if not value:
        return None
    m = re.match(r"(\d{4})(\d{2})(\d{2})", value.strip())
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None
