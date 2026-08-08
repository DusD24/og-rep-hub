"""Shared data loading and deterministic score rules for OG Rep Hub."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load(name: str) -> Any:
    with (DATA / f"{name}.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def round_score(value: float) -> float:
    return round(value + 1e-9, 1)


def seller_reliability(metrics: dict[str, float]) -> float:
    return round_score(
        metrics["fulfillment"] * 0.30
        + metrics["service_communication"] * 0.25
        + metrics["qc_transparency"] * 0.20
        + metrics["shipping_consistency"] * 0.15
        + metrics["payment_risk_signals"] * 0.10
    )


def bag_confidence(metrics: dict[str, float]) -> float:
    return round_score(
        metrics["accuracy"] * 0.35
        + metrics["construction_materials"] * 0.25
        + metrics["exact_variant_availability"] * 0.20
        + metrics["independent_corroboration"] * 0.10
        + metrics["recency"] * 0.10
    )


def recommendation(bag_score: float, seller_score: float) -> float:
    return round_score(bag_score * 0.65 + seller_score * 0.35)


def tier_for(
    score: float,
    *,
    exact_variant: bool,
    independent_authors: int,
    unresolved_major_negative: bool,
    quality_evidence: bool,
) -> str | None:
    if not quality_evidence:
        return None
    if (
        score >= 80
        and exact_variant
        and independent_authors >= 2
        and not unresolved_major_negative
    ):
        return "A"
    if score >= 65 and exact_variant and not unresolved_major_negative:
        return "B"
    if score >= 50:
        return "C"
    return "Watchlist"

