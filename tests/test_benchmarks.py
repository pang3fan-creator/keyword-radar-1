"""The benchmark basket: which keywords may size a name, and how the median is taken."""
from datetime import date, timedelta

from radar import benchmarks

START = date(2026, 8, 1)


def _series(values, start=START):
    return [(start + timedelta(days=i), v) for i, v in enumerate(values)]


def test_a_stable_benchmark_is_usable():
    flat = [20] * 60 + [21] * 30                      # +5% over the quarter

    assert benchmarks.drift(_series(flat), [("2026-09", 9000), ("2026-08", 8800)]) == {"ok": True, "reason": ""}


def test_a_benchmark_that_moved_a_quarter_fails_on_slope():
    rising = [10] * 60 + [30] * 30                    # +200%

    got = benchmarks.drift(_series(rising), [("2026-09", 9000), ("2026-08", 8800)])

    assert not got["ok"] and got["reason"].startswith("slope")


def test_a_benchmark_with_one_day_blowup_is_left_out():
    spiky = [20] * 89 + [200]                         # x10 one day

    got = benchmarks.drift(_series(spiky), [("2026-09", 9000), ("2026-08", 8800)])

    assert not got["ok"] and got["reason"].startswith("spike")


def test_a_benchmark_whose_volume_jumped_fails_month_over_month():
    flat = [20] * 90

    got = benchmarks.drift(_series(flat), [("2026-09", 14000), ("2026-08", 9000)])

    assert not got["ok"] and got["reason"].startswith("month over month")


def test_too_little_history_is_not_a_benchmark():
    assert benchmarks.drift(_series([20] * 30), [])["reason"] == "too little history"


def test_the_size_is_the_median_of_each_benchmark_estimate():
    ratios = {"a": 0.5, "b": 0.4, "c": 0.9}
    dailies = {"a": 1000, "b": 1000, "c": 1000}

    assert benchmarks.size(ratios, dailies) == 500      # 500, 400, 900


def test_one_benchmark_cannot_carry_a_size():
    assert benchmarks.size({"a": 0.5}, {"a": 1000}) is None


def test_a_benchmark_without_a_daily_size_is_ignored():
    assert benchmarks.size({"a": 0.5, "b": 0.5}, {"a": 1000}) is None
    assert benchmarks.daily(9000) == 300


def test_usable_filters_on_the_check():
    checked = {"a": {"ok": True}, "b": {"ok": False, "reason": "slope"}}

    assert benchmarks.usable(checked) == ["a"]
