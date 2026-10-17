"""Autocomplete discovery: free suggestions, filtered into combo-word candidates."""
import pytest

from radar import autocomplete


@pytest.fixture(autouse=True)
def no_wait(cfg):
    cfg["slow"]["delay"] = 0

SUGGEST = ["ai headshot", ["ai headshot generator", "ai headshots", "ai headshot generator free"],
           [], {"google:suggestsubtypes": [[512], [512], [512]]}]


def test_a_suggestion_list_is_parsed(monkeypatch):
    monkeypatch.setattr(autocomplete, "_get", lambda url: SUGGEST)

    assert autocomplete.suggest("ai headshot") == ["ai headshot generator", "ai headshots", "ai headshot generator free"]


def test_a_broken_answer_is_an_error_not_an_empty_list(monkeypatch):
    monkeypatch.setattr(autocomplete, "_get", lambda url: {"not": "a suggestion list"})

    try:
        autocomplete.suggest("ai headshot")
    except RuntimeError as exc:
        assert "unexpected" in str(exc)
    else:
        raise AssertionError("a malformed answer must raise")


def test_seeds_are_the_object_action_matrix(cfg):
    cfg["slow"]["objects"] = ["headshot", "logo"]
    cfg["slow"]["actions"] = ["generator", "remover"]

    assert autocomplete.seeds(cfg) == ["ai headshot generator", "ai headshot remover",
                                       "ai logo generator", "ai logo remover"]


def test_candidates_keep_combo_words_that_share_a_seed_word(cfg, monkeypatch):
    monkeypatch.setattr(autocomplete, "suggest", lambda seed: [
        "ai headshot generator", "ai headshot generator free", "ai headshot", "ai", "tattoo generator",
        "AI Headshot Maker", "how to make ai headshot"])

    got, errors = autocomplete.candidates(["ai headshot"], lambda t: "", cfg)

    assert errors == []
    assert [r["term"] for r in got] == ["ai headshot generator", "ai headshot generator free", "ai headshot maker"]


def test_a_known_term_is_not_a_candidate(cfg, monkeypatch):
    monkeypatch.setattr(autocomplete, "suggest", lambda seed: ["ai headshot generator", "ai headshot editor"])

    got, _ = autocomplete.candidates(["ai headshot"], lambda t: "covered" if "generator" in t else "", cfg)

    assert [r["term"] for r in got] == ["ai headshot editor"]


def test_two_seeds_that_name_the_same_phrase_give_one_candidate(cfg, monkeypatch):
    monkeypatch.setattr(autocomplete, "suggest", lambda seed: ["ai avatar app free"])

    got, _ = autocomplete.candidates(["ai avatar generator", "ai avatar editor"], lambda t: "", cfg)

    assert [r["term"] for r in got] == ["ai avatar app free"]
    assert got[0]["objects"] == ["avatar"] and len(got[0]["seeds"]) == 2


def test_a_shared_action_word_is_not_enough(cfg, monkeypatch):
    monkeypatch.setattr(autocomplete, "suggest", lambda seed: ["ai picture summarizer free"])

    got, _ = autocomplete.candidates(["ai photo summarizer"], lambda t: "", cfg)

    assert got == []


def test_a_plural_still_counts_for_its_category(cfg, monkeypatch):
    monkeypatch.setattr(autocomplete, "suggest", lambda seed: ["ai headshots free"])

    got, _ = autocomplete.candidates(["ai headshot generator"], lambda t: "", cfg)

    assert [r["term"] for r in got] == ["ai headshots free"]


def test_a_failing_seed_is_a_line_and_the_others_still_answer(cfg, monkeypatch):
    def suggest(seed):
        if "logo" in seed:
            raise RuntimeError("HTTP 429")
        return ["ai headshot generator free"]
    monkeypatch.setattr(autocomplete, "suggest", suggest)

    got, errors = autocomplete.candidates(["ai headshot generator", "ai logo generator"], lambda t: "", cfg)

    assert [r["term"] for r in got] == ["ai headshot generator free"]
    assert errors and errors[0].startswith("ai logo generator:")


def test_the_query_cap_is_respected(cfg, monkeypatch):
    asked = []

    def suggest(seed):
        asked.append(seed)
        return []
    monkeypatch.setattr(autocomplete, "suggest", suggest)
    cfg["slow"]["max_queries"] = 2

    autocomplete.candidates(autocomplete.seeds(cfg), lambda t: "", cfg)

    assert asked == autocomplete.seeds(cfg)[:2]
