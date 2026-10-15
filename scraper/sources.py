"""The websites the scraper visits.

Each source has:
  name          Shown on the website as the event's source.
  url           Page or feed to fetch.
  type          "html" (listing page, also reads schema.org JSON-LD),
                "ical" (iCalendar feed) or "rss" (RSS/Atom feed).
  youth_focused True when every event on the page is a youth event, so the
                youth keyword filter is skipped.

To add a source, append an entry. Most UN sites work with type "html" and no
custom code; check the "sources" section of data/events.json after a run to see
how many events each source produced and whether it failed.
"""

SOURCES = [
    # --- Dedicated youth bodies ------------------------------------------------
    {"name": "UN Youth Office", "url": "https://www.un.org/youthaffairs/en/events", "type": "html", "youth_focused": True},
    {"name": "UN DESA – Youth", "url": "https://social.desa.un.org/issues/youth/events", "type": "html", "youth_focused": True},
    {"name": "ECOSOC Youth Forum", "url": "https://ecosoc.un.org/en/what-we-do/ecosoc-youth-forum", "type": "html", "youth_focused": True},
    {"name": "UN Major Group for Children & Youth", "url": "https://www.unmgcy.org/events", "type": "html", "youth_focused": True},

    # --- UN-wide calendars (filtered by youth keywords) ------------------------
    {"name": "UN DESA", "url": "https://social.desa.un.org/events", "type": "html"},
    {"name": "ECOSOC", "url": "https://ecosoc.un.org/en/events", "type": "html"},
    {"name": "UN SDGs", "url": "https://sdgs.un.org/events", "type": "html"},
    {"name": "UN Web TV", "url": "https://webtv.un.org/en/schedule", "type": "html"},
    {"name": "UN Indico", "url": "https://indico.un.org/export/categ/0.ics?from=-30d&to=%2B365d&limit=1000", "type": "ical"},

    # --- UN agencies, funds and programmes -----------------------------------
    {"name": "UNESCO", "url": "https://www.unesco.org/en/events", "type": "html"},
    {"name": "UNICEF", "url": "https://www.unicef.org/events", "type": "html"},
    {"name": "UNFPA", "url": "https://www.unfpa.org/events", "type": "html"},
    {"name": "UNDP", "url": "https://www.undp.org/events", "type": "html"},
    {"name": "UN Volunteers", "url": "https://www.unv.org/events", "type": "html"},
    {"name": "UN-Habitat", "url": "https://unhabitat.org/events", "type": "html"},
    {"name": "UNEP", "url": "https://www.unep.org/events", "type": "html"},
    {"name": "UN Women", "url": "https://www.unwomen.org/en/news-stories/events", "type": "html"},
    {"name": "ILO", "url": "https://www.ilo.org/events-and-meetings", "type": "html"},
    {"name": "WHO", "url": "https://www.who.int/news-room/events", "type": "html"},
    {"name": "ITU", "url": "https://www.itu.int/en/events/Pages/default.aspx", "type": "html"},
    {"name": "UNCCD", "url": "https://www.unccd.int/events/other-meetings-events", "type": "html"},
    {"name": "UNFCCC", "url": "https://unfccc.int/calendar", "type": "html"},
]
