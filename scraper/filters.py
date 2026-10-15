"""Decide whether an event is youth related."""

from __future__ import annotations

import re

YOUTH_PATTERN = re.compile(
    r"""
    \byouths?\b
    | \byoung\s+(?:people|persons?|leaders?|women|men|girls|boys|professionals?|
                  innovators?|activists?|changemakers?|entrepreneurs?|voices?|
                  scientists?|researchers?|delegates?|peacebuilders?|generation)\b
    | \badolescen
    | \bstudents?\b
    | \bteen(?:s|agers?)?\b
    | \bmodel\s+(?:united\s+nations|un)\b
    | \bmun\b
    | \byoungo\b
    | \bmgcy\b
    | \bnext\s+generation\b
    | \bfuture\s+generations?\b
    | \bgen[\s-]?z\b
    | \bjuvenil
    | \bjeunes(?:se)?\b
    | \bjuventud\b
    | \bjóvenes\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def is_youth_related(*texts: str | None) -> bool:
    return any(t and YOUTH_PATTERN.search(t) for t in texts)
