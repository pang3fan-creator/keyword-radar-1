"""When a name has no size yet, what the signals said about it decides.

A new word usually has no search volume, and the benchmark basket can be uncalibrated, so the
size is often unknown. The rule here is deliberately plain instead of a score with weights nobody
can audit: a name is strong when at least two signals found it *and* the name judge scored it at
or above the read threshold. `label` is what the table shows, so a reader can check the rule.
"""
from __future__ import annotations

STRONG_SIGNALS = 2
STRONG_NAMED = 0.8


def strong(kinds: list[str] | None, named: float | None) -> bool:
    return len(set(kinds or [])) >= STRONG_SIGNALS and (named or 0) >= STRONG_NAMED


def label(kinds: list[str] | None, named: float | None) -> str:
    count = len(set(kinds or []))
    score = "—" if named is None else f"{named:.2f}"
    return f"{count} signal{'s' if count != 1 else ''} · {score}"
