#!/usr/bin/env python3
"""Write a compact public research summary from normalized data."""

from __future__ import annotations

from pathlib import Path

from model import ROOT, load


def main() -> int:
    rankings = load("rankings")["rankings"]
    bags = load("bags")
    sellers = load("sellers")
    evidence = load("evidence")
    research = load("research")
    ranked = [row for row in rankings if row["rank_status"] == "ranked"]
    lines = [
        "# Research snapshot",
        "",
        f"- Bags tracked: {len(bags)}",
        f"- Sellers tracked: {len(sellers)}",
        f"- Public evidence records: {len(evidence)}",
        f"- Ranked offerings: {len(ranked)}",
        f"- Saturation reached: {'yes' if research['saturation_reached'] else 'no'}",
        "",
        "Scores express evidence confidence, not a guarantee of seller behavior, availability, authenticity, or outcome.",
        "",
    ]
    (ROOT / "RESEARCH_SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote RESEARCH_SUMMARY.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

