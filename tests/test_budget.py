"""Budget guard tests."""

from __future__ import annotations

import pytest

from slopcore_factory.blueprint import Blueprint, Budgets, SeedanceClip
from slopcore_factory.budget import apply_estimate, estimate, guard
from slopcore_factory.errors import BudgetError


def _blueprint(seconds: float = 30.0, cap: float = 0.0) -> Blueprint:
    return Blueprint(
        title="t",
        duration=180.0,
        seedance=[SeedanceClip(clip=f"sd{i}", duration=seconds / 3) for i in range(3)],
        budgets=Budgets(cap_usd=cap),
    )


def test_estimate_scales_with_seconds() -> None:
    budgets = estimate(_blueprint(seconds=30.0))
    assert budgets.seedance_seconds == 30.0
    assert budgets.seedance_usd > 0
    assert budgets.total_usd > budgets.seedance_usd


def test_guard_raises_over_cap() -> None:
    bp = _blueprint(seconds=60.0, cap=1.0)
    apply_estimate(bp)
    with pytest.raises(BudgetError):
        guard(bp)


def test_guard_passes_under_cap() -> None:
    bp = _blueprint(seconds=10.0, cap=1000.0)
    apply_estimate(bp)
    guard(bp)  # does not raise


def test_retry_buffer_one_shot_is_cheaper_than_default() -> None:
    one_shot = _blueprint(seconds=30.0)
    one_shot.budgets.retry_buffer = 1.0
    assert estimate(one_shot).retry_buffer == 1.0
    assert estimate(one_shot).seedance_usd < estimate(_blueprint(seconds=30.0)).seedance_usd
