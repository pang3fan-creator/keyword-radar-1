"""Entity resolution: when two surface forms name the same thing.

The calibration set is 50 pairs that should merge and 50 that should not; 10 of them come
from the real lead table (the rest are built around the rule's edges). Merging two things is
worse than keeping a duplicate, so precision is the bar that matters.
"""
import json
from pathlib import Path

import pytest

from radar import entity

PAIRS = json.loads((Path(__file__).parent / "fixtures" / "entity_pairs.json").read_text(encoding="utf-8"))
SAME = [p for p in PAIRS if p["same"]]


def test_the_calibration_set_is_balanced():
    assert len(PAIRS) == 100
    assert len(SAME) == 50
    assert sum(1 for p in PAIRS if p["real"]) == 10


@pytest.mark.parametrize("pair", PAIRS, ids=[f"{p['a']} ~ {p['b']}" for p in PAIRS])
def test_same_entity(pair):
    assert entity.same_entity(pair["a"], pair["b"]) is pair["same"], pair["why"]
    assert entity.same_entity(pair["b"], pair["a"]) is pair["same"], "symmetry"


def test_precision_and_recall_clear_the_bar():
    tp = sum(entity.same_entity(p["a"], p["b"]) for p in SAME)
    fp = sum(entity.same_entity(p["a"], p["b"]) for p in PAIRS if not p["same"])
    precision = tp / (tp + fp)
    recall = tp / len(SAME)
    assert precision >= 0.95 and recall >= 0.80, f"precision {precision:.2f}, recall {recall:.2f}"


@pytest.mark.parametrize("forms, want", [
    (["mirelo sfx", "mirelo sfx 2.0"], "mirelo sfx 2.0"),
    (["spark open", "muse spark open", "meta muse spark open"], "muse spark open"),
    (["omnilingual asr", "meta omnilingual asr"], "omnilingual asr"),
    (["hy memory", "hy-memory-30b-a3b"], "hy memory"),
])
def test_canonical(forms, want):
    assert entity.canonical(forms) == want


def test_a_merge_needs_the_same_day_or_source():
    rows = [
        {"term": "mirelo sfx", "day": "2026-10-17", "source": "x"},
        {"term": "mirelo sfx 2.0", "day": "2026-10-17", "source": "x"},
        {"term": "beam", "day": "2026-10-16", "source": "hf"},
        {"term": "beam 1.0", "day": "2026-10-10", "source": "sitemap"},
    ]

    got = {c["canonical"]: c["aliases"] for c in entity.cluster(rows)}

    assert got["mirelo sfx 2.0"] == ["mirelo sfx", "mirelo sfx 2.0"]
    assert set(got) == {"mirelo sfx 2.0", "beam", "beam 1.0"}
