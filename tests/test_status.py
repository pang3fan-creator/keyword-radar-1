"""Every source that ran leaves a line in the data-status section, even one nobody labelled."""
from radar import report


def _lines(**blocks) -> str:
    b = {"x": {"skipped": True}, "hf": {"skipped": True}, "breakout": {"skipped": True},
         "sitemap": {"skipped": True}}
    b.update(blocks)
    return "\n".join(report._status_lines(b, {}, []))


def test_a_source_that_ran_reports_what_it_read_and_found():
    text = _lines(hn={"read": 42, "found": 3})

    assert "⑨ HN" in text and "42 read, 3 new" in text


def test_a_source_that_failed_says_so_in_its_own_line():
    text = _lines(official={"error": "URLError: timed out"})

    assert "⑧ official" in text and "URLError: timed out" in text


def test_a_source_that_was_skipped_still_leaves_a_line():
    text = _lines(hn={"skipped": True})

    assert "⑨ HN: skipped" in text


def test_a_feed_that_failed_is_named_even_when_the_others_answered():
    text = _lines(official={"read": 30, "found": 2, "failed": ["mistral"]})

    assert "30 read, 2 new" in text and "failed: mistral" in text


def test_a_source_without_a_label_is_not_silent():
    text = _lines(newsource={"read": 5, "found": 0})

    assert "newsource" in text and "5 read, 0 new" in text


def test_a_new_site_block_says_how_many_sites_and_which_query_failed():
    text = _lines(newsite={"read": 9, "found": 4, "failed": ["video"], "sites": [{"new": True}]})

    assert "③ new site" in text and "9 read, 4 new" in text and "failed: video" in text


def test_a_skipped_sitemap_says_so():
    text = _lines(sitemap={"skipped": True})

    assert "③ sitemaps: skipped" in text
