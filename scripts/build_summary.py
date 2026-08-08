#!/usr/bin/env python3
"""Write a compact public research summary from normalized data."""

from __future__ import annotations

from pathlib import Path

from model import ROOT, load


def main() -> int:
    rankings = load("rankings")["rankings"]
    families = load("bag_families")
    bags = load("bags")
    sellers = load("sellers")
    contacts = load("contacts")
    evidence = load("evidence")
    research = load("research")
    ranked = [row for row in rankings if row["rank_status"] == "ranked"]
    lane_summary = "; ".join(
        f"r/{lane['subreddit_focus']}: {lane.get('families_checked', 0)}"
        for lane in research.get("research_lanes", [])
    )
    lines = [
        "# Research snapshot",
        "",
        f"- Bag families mapped: {len(families)}",
        f"- Families published with Reddit tiles: {sum(row['publication_status'] == 'published' for row in families)}",
        f"- Exact variants retained: {len(bags)}",
        f"- Sellers tracked: {len(sellers)}",
        f"- Community-listed contacts: {len(contacts)}",
        f"- Public evidence records: {len(evidence)}",
        f"- Ranked offerings: {len(ranked)}",
        f"- Research lanes checked: {lane_summary}",
        f"- Original campaign saturation reached: {'yes' if research['saturation_reached'] else 'no'}",
        "",
        "Scores express evidence confidence, not a guarantee of seller behavior, availability, authenticity, or outcome.",
        "",
    ]
    (ROOT / "RESEARCH_SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote RESEARCH_SUMMARY.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
