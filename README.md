# UN Youth Events

A single-page website listing youth-related events from across the United Nations
system. A Python scraper collects the events from UN websites every day.

```
index.html               the website (static, no build step)
data/events.json         scraped events (written by the scraper)
data/events.js           same data, so index.html also works opened from disk
data/manual_events.json  events you add by hand (always included)
scraper/sources.py       the list of websites to scrape  ← add sources here
scraper/run.py           scraper entry point
tests/                   offline tests
```

## How the scraper works

For every source in `scraper/sources.py` it:

1. Downloads the page or feed. It understands HTML listing pages, schema.org
   JSON-LD event data, iCalendar (`.ics`) and RSS/Atom feeds.
2. On HTML pages, finds each event "card" (a title link plus the nearest date)
   without site-specific code, so most new sources only need a URL.
3. Keeps only youth-related events by checking for keywords such as *youth*,
   *young people*, *adolescents*, *students*, *MGCY*, *YOUNGO*, *jeunesse* and
   *juventud* (see `scraper/filters.py`). Sources marked `youth_focused` skip this check.
4. Opens the event's own page to find its date when the listing doesn't show one,
   and drops anything that still has no date.
5. Removes duplicates, keeps past events for 180 days, and writes `data/events.json`.

If a site is down or blocks the scraper, its events from the previous run are
kept. The website's footer ("Sources checked in the last update") shows each
source's status and event count, so you can spot a source that needs fixing.

## Run it locally

```bash
pip install -r requirements.txt
python -m scraper.run             # all sources
python -m scraper.run --only UNICEF -v
python -m unittest discover tests
```

Then open `index.html` in a browser.

## Automatic daily updates and hosting (GitHub Actions + Pages)

`.github/workflows/scrape.yml` runs the tests and the scraper every day at 05:17 UTC,
commits the new `data/events.*` files, and publishes the site to GitHub Pages.

One-time setup:

1. **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. **Settings → Actions → General → Workflow permissions: Read and write**.
3. Make sure the workflow is on the default branch (scheduled runs only fire there),
   then start it from **Actions → Scrape UN youth events → Run workflow**.

## Adding events or sources

- **A source:** add `{"name": ..., "url": ..., "type": "html"}` to
  `scraper/sources.py`, then run `python -m scraper.run --only <name> -v` to check it.
- **A single event** the scraper can't find: add it to `data/manual_events.json`.
