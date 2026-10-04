"""Budget guard.

Every paid step reads the planned spend from the blueprint and refuses to run
when it would break the cap. Rates come from ``slopcore-hf`` when importable so
the two projects never disagree, with a local fallback table.

The guard is intentionally conservative: generated video overshoots (divergence
covers, retries), so a buffer is applied to the Seedance estimate.
"""

from __future__ import annotations

from .blueprint import Blueprint, Budgets
from .errors import BudgetError
from .logging_setup import get_logger

log = get_logger("budget")

# 2026 EvoLink published rates (fallback if slopcore-hf is unavailable).
RATES_USD_PER_SECOND = {"480p": 0.138, "720p": 0.296}
SUNO_USD = 0.118  # one request, four takes
PLATE_USD = 0.068  # one Seedream plate
RETRY_BUFFER = 1.35  # covers and retries overshoot the plan


def _rate(quality: str) -> float:
    """Prefer slopcore-hf's rate table, fall back to the local copy."""
    try:
        from .vendor import add_slopcore_to_path

        add_slopcore_to_path()
        from slopcore_hf.config import SEEDANCE_RATES  # type: ignore

        return float(SEEDANCE_RATES[quality])
    except Exception:  # noqa: BLE001 - any failure falls back
        return RATES_USD_PER_SECOND.get(quality, RATES_USD_PER_SECOND["720p"])


def estimate(blueprint: Blueprint) -> Budgets:
    """Planned spend for a blueprint (Seedance + plates + song + buffer)."""
    quality = blueprint.budgets.seedance_quality or "720p"
    clip_seconds = sum(clip.duration for clip in blueprint.seedance)
    if not clip_seconds:  # lipsync windows imply clip seconds too
        clip_seconds = blueprint.sung_seconds
    seedance_usd = round(clip_seconds * _rate(quality) * RETRY_BUFFER, 2)
    images_usd = round(len(blueprint.plates) * PLATE_USD, 2)
    suno_usd = SUNO_USD
    return Budgets(
        cap_usd=blueprint.budgets.cap_usd,
        seedance_seconds=round(clip_seconds, 1),
        seedance_quality=quality,
        seedance_usd=seedance_usd,
        suno_usd=suno_usd,
        images_usd=images_usd,
        total_usd=round(seedance_usd + images_usd + suno_usd, 2),
    )


def apply_estimate(blueprint: Blueprint) -> Budgets:
    """Recompute and store the blueprint's budgets, preserving the cap."""
    blueprint.budgets = estimate(blueprint)
    return blueprint.budgets


def guard(blueprint: Blueprint, extra_usd: float = 0.0, cap_usd: float | None = None) -> None:
    """Raise :class:`BudgetError` when planned spend would exceed the cap."""
    cap = blueprint.budgets.cap_usd if cap_usd is None else cap_usd
    planned = blueprint.budgets.total_usd + extra_usd
    if cap and planned > cap:
        raise BudgetError(
            f"planned spend ${planned:.2f} exceeds cap ${cap:.2f} "
            f"(seedance {blueprint.budgets.seedance_seconds:.0f}s @ "
            f"{blueprint.budgets.seedance_quality})"
        )
    if cap:
        log.info("budget ok: planned $%.2f / cap $%.2f", planned, cap)


def report(blueprint: Blueprint) -> str:
    b = blueprint.budgets
    lines = [
        f"seedance   {b.seedance_seconds:>7.1f} s @ {b.seedance_quality}  ${b.seedance_usd:>7.2f}",
        f"plates     {len(blueprint.plates):>7d}                         ${b.images_usd:>7.2f}",
        f"song                                        ${b.suno_usd:>7.2f}",
        f"total                                       ${b.total_usd:>7.2f}",
    ]
    if b.cap_usd:
        lines.append(f"cap                                         ${b.cap_usd:>7.2f}")
    return "\n".join(lines)
