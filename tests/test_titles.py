"""The 40-title sample M3 was judged on, pinned so the extraction cannot drift silently.

20 Show HN titles and 20 recent official-feed titles, fetched 2026-10-17. 19 of them name a
thing and are pinned to it; two are known misses (a lowercase first letter, a name that is
not at the start of the title). Fixing a miss means updating this fixture, which is the
point: the number stops being a memory.
"""
import json
from pathlib import Path

import pytest

from radar import hn, official

CASES = json.loads((Path(__file__).parent / "fixtures" / "titles_40.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[f"{c['source']}:{c['title'][:36]}" for c in CASES])
def test_a_title_gives_the_name_the_sample_pinned(case):
    got = hn.title_name(case["title"]) if case["source"] == "hn" else official.launch_name(case["title"])

    assert got == case["expected"]


def test_the_sample_still_holds_nineteen_names_and_two_known_misses():
    assert len(CASES) == 40
    assert sum(1 for c in CASES if c["expected"]) == 19
    assert sum(1 for c in CASES if c.get("known_miss")) == 2
