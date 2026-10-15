"""Offline tests for the parsers. Run with: python -m unittest discover tests"""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from scraper import run as runner
from scraper.dates import find_date_range, parse_ical_date, parse_iso
from scraper.filters import is_youth_related
from scraper.parsers import parse_detail_page, parse_feed, parse_html, parse_ical

LISTING = """
<html><body>
<header><nav><a href="/youth">Youth programmes and initiatives</a></nav></header>
<main>
  <div class="views-row">
    <h3><a href="/events/ecosoc-youth-forum-2027">ECOSOC Youth Forum 2027</a></h3>
    <span class="date">14-16 April 2027</span>
    <span class="location">UN Headquarters, New York</span>
    <a href="/events/ecosoc-youth-forum-2027">Read more</a>
  </div>
  <div class="views-row">
    <h3><a href="/events/budget-committee">Fifth Committee budget session</a></h3>
    <time datetime="2027-03-02T10:00:00Z">2 March 2027</time>
  </div>
  <div class="views-row">
    <h3><a href="/events/young-leaders">Young Leaders for the SDGs dialogue</a></h3>
    <p>Online event</p>
  </div>
</main>
<footer><a href="/youth-day">International Youth Day 12 August 2027</a></footer>
</body></html>
"""

JSONLD = """
<html><head><script type="application/ld+json">
{"@context": "https://schema.org", "@graph": [
  {"@type": "Event", "name": "Youth Climate Summit", "url": "/youth-climate",
   "startDate": "2027-09-20", "endDate": "2027-09-21",
   "location": {"@type": "Place", "name": "Palais des Nations",
                "address": {"addressLocality": "Geneva"}}}
]}
</script></head><body></body></html>
"""

ICAL = (
    "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nSUMMARY:Youth dialogue on peace\r\n  and security\r\n"
    "DTSTART;TZID=America/New_York:20270115T100000\r\nDTEND:20270116\r\n"
    "URL:https://indico.un.org/event/1/\r\nLOCATION:Conference Room 4\\, UNHQ\r\nEND:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Global Youth Summit, 3 May 2027</title><link>https://example.org/gys</link>
<description>&lt;p&gt;Join young people from around the world&lt;/p&gt;</description></item>
</channel></rss>"""


class DateTests(unittest.TestCase):
    def test_formats(self):
        cases = {
            "14 April 2027": (date(2027, 4, 14), None),
            "Tuesday, April 14, 2027 10:00": (date(2027, 4, 14), None),
            "14–16 April 2027": (date(2027, 4, 14), date(2027, 4, 16)),
            "April 14 - 16, 2027": (date(2027, 4, 14), date(2027, 4, 16)),
            "30 March - 2 April 2027": (date(2027, 3, 30), date(2027, 4, 2)),
            "March 30 to April 2, 2027": (date(2027, 3, 30), date(2027, 4, 2)),
            "2027-01-05": (date(2027, 1, 5), None),
            "12 Sept. 2027": (date(2027, 9, 12), None),
            "no date here": (None, None),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(find_date_range(text), expected)

    def test_earliest_match_wins(self):
        self.assertEqual(find_date_range("Event on 3 May 2027. Posted 1 January 2027")[0], date(2027, 5, 3))

    def test_iso_and_ical(self):
        self.assertEqual(parse_iso("2027-09-20T09:00:00+02:00"), date(2027, 9, 20))
        self.assertEqual(parse_ical_date("20270115T100000Z"), date(2027, 1, 15))


class FilterTests(unittest.TestCase):
    def test_keywords(self):
        self.assertTrue(is_youth_related("ECOSOC Youth Forum"))
        self.assertTrue(is_youth_related("Dialogue with young people on climate"))
        self.assertTrue(is_youth_related("Forum mondial de la jeunesse", "pour les jeunes"))
        self.assertFalse(is_youth_related("Fifth Committee budget session"))
        self.assertFalse(is_youth_related("Youngstown sister city"))


class ParserTests(unittest.TestCase):
    def test_html_listing(self):
        events = {e["title"]: e for e in parse_html(LISTING, "https://example.un.org/events")}
        forum = events["ECOSOC Youth Forum 2027"]
        self.assertEqual(forum["url"], "https://example.un.org/events/ecosoc-youth-forum-2027")
        self.assertEqual((forum["start"], forum["end"]), (date(2027, 4, 14), date(2027, 4, 16)))
        self.assertIn("New York", forum["location"])
        self.assertEqual(events["Fifth Committee budget session"]["start"], date(2027, 3, 2))
        self.assertIsNone(events["Young Leaders for the SDGs dialogue"]["start"])
        # navigation and footer links are not events
        self.assertNotIn("Youth programmes and initiatives", events)
        self.assertFalse(any("International Youth Day" in t for t in events))

    def test_jsonld(self):
        [ev] = parse_html(JSONLD, "https://example.un.org/")
        self.assertEqual(ev["title"], "Youth Climate Summit")
        self.assertEqual(ev["url"], "https://example.un.org/youth-climate")
        self.assertEqual(ev["end"], date(2027, 9, 21))
        self.assertEqual(ev["location"], "Palais des Nations, Geneva")

    def test_ical(self):
        [ev] = parse_ical(ICAL, "https://indico.un.org/")
        self.assertEqual(ev["title"], "Youth dialogue on peace and security")
        self.assertEqual(ev["start"], date(2027, 1, 15))
        self.assertEqual(ev["location"], "Conference Room 4, UNHQ")

    def test_feed(self):
        [ev] = parse_feed(RSS, "https://example.org/feed")
        self.assertEqual(ev["start"], date(2027, 5, 3))
        self.assertIn("young people", ev["description"])

    def test_detail_page(self):
        html = '<html><head><meta name="description" content="A youth event"></head><body><nav>1 January 2020</nav><main><p>Date: 8 December 2027</p></main></body></html>'
        info = parse_detail_page(html, "https://example.org/e")
        self.assertEqual(info["start"], date(2027, 12, 8))
        self.assertEqual(info["description"], "A youth event")


class RunTests(unittest.TestCase):
    def test_end_to_end_with_failure_fallback(self):
        sources = [
            {"name": "Listing", "url": "https://example.un.org/events", "type": "html"},
            {"name": "Broken", "url": "https://broken.un.org/events", "type": "html"},
        ]
        previous = {"events": [{
            "title": "Kept youth event", "url": "https://broken.un.org/e/1", "start": "2099-01-01",
            "end": None, "location": "", "description": "", "source": "Broken",
            "source_url": "https://broken.un.org/events",
        }]}
        detail = '<main><p>Young Leaders dialogue, 9 June 2099</p></main>'

        def fake_fetch(session, url):
            if url == "https://example.un.org/events":
                return LISTING.replace("2027", "2099")
            if url.endswith("/young-leaders"):
                return detail
            raise runner.requests.ConnectionError("down")

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(runner, "SOURCES", sources), \
                mock.patch.object(runner, "fetch", fake_fetch), \
                mock.patch.object(runner, "load_manual", lambda: []), \
                mock.patch.object(runner.time, "sleep", lambda s: None):
            out = Path(tmp)
            (out / "events.json").write_text(json.dumps(previous))
            data = runner.run(out_dir=out)
            titles = [e["title"] for e in data["events"]]
            self.assertEqual(titles, ["Kept youth event", "ECOSOC Youth Forum 2099",
                                      "Young Leaders for the SDGs dialogue"])
            self.assertEqual(data["events"][2]["start"], "2099-06-09")
            self.assertEqual([s["status"] for s in data["sources"]], ["ok", "error"])
            self.assertTrue((out / "events.js").read_text().startswith("window.UN_YOUTH_EVENTS"))


if __name__ == "__main__":
    unittest.main()
