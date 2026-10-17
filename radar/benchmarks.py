"""A basket of benchmark keywords, so one keyword's own swing does not resize every name.

`gpts` alone could not be sized on M0, and a single benchmark that drifts silently bends every
estimate. A benchmark earns its place with three checks over the last quarter (docs/05 §4.3 C):
its Trends slope stays within +-20%, its month-over-month volume within +-30%, and it has no
single day above three times its median. Fewer than two usable benchmarks means the size is
`uncalibrated` and names are shown without an estimate -- never guessed.
"""
from __future__ import annotations

import statistics
from datetime import date

SLOPE = 0.20          # a benchmark may move this much over the quarter
MOM = 0.30            # month-over-month volume
SPIKE = 3.0           # one day against its own median
MIN_BENCHMARKS = 2


def _mean(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def drift(series: list[tuple[date, int]], months: list[tuple[str, int]], today: date | None = None) -> dict:
    """Whether a benchmark is stable enough to size other words. `reason` is the first check it
    failed, so the report can say why it was left out."""
    points = [(d, v) for d, v in series if v]
    if len(points) < 60:
        return {"ok": False, "reason": "too little history"}
    median = statistics.median([v for _, v in points])
    peak = max(v for _, v in points)
    if median and peak > SPIKE * median:        # a single blowup is the sharper diagnosis
        return {"ok": False, "reason": f"spike x{peak / median:.1f}"}
    recent = _mean([v for _, v in points[-30:]])
    before = _mean([v for _, v in points[-60:-30]])
    if before and abs(recent / before - 1) > SLOPE:
        return {"ok": False, "reason": f"slope {recent / before - 1:+.0%}"}
    if len(months) >= 2:
        now, prev = months[0][1], months[1][1]
        if prev and abs(now / prev - 1) > MOM:
            return {"ok": False, "reason": f"month over month {now / prev - 1:+.0%}"}
    return {"ok": True, "reason": ""}


def daily(volume: int) -> int:
    return round(volume / 30)


def size(ratios: dict[str, float], dailies: dict[str, int]) -> int | None:
    """Median of `name / benchmark` times the benchmark's daily searches. None when fewer than
    two benchmarks can carry the estimate."""
    found = [ratios[b] * dailies[b] for b in ratios if dailies.get(b)]
    if len(found) < MIN_BENCHMARKS:
        return None
    return round(statistics.median(found))


def usable(checked: dict[str, dict]) -> list[str]:
    return [term for term, r in checked.items() if r.get("ok")]
