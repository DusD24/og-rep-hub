#!/usr/bin/env python3
"""Generate or check deterministic seller/offering rankings."""

from __future__ import annotations

import argparse
import json
from datetime import date

from model import DATA, bag_confidence, load, recommendation, seller_reliability, tier_for


def generate() -> dict:
    sellers = {item["id"]: item for item in load("sellers")}
    evidence = {item["id"]: item for item in load("evidence")}
    rows = []

    for offering in load("offerings"):
        evidence_rows = [evidence[item] for item in offering.get("evidence_ids", [])]
        quality_rows = [item for item in evidence_rows if item["source_type"] != "catalog"]
        authors = {
            item["author"].casefold()
            for item in quality_rows
            if item.get("author")
        }
        exact_variant = any(item.get("exact_product_match") is True for item in quality_rows)
        major_negative = any(
            item.get("major_negative") is True and item.get("resolved") is not True
            for item in evidence_rows
        )
        if not quality_rows or not offering.get("bag_metrics"):
            reason = "No non-catalog quality evidence" if not quality_rows else "Insufficient exact-variant evidence for scoring"
            rows.append(
                {
                    "offering_id": offering["id"],
                    "seller_id": offering["seller_id"],
                    "bag_id": offering["bag_id"],
                    "seller_reliability": None,
                    "bag_confidence": None,
                    "recommendation_score": None,
                    "tier": None,
                    "rank_status": "unranked",
                    "reason": reason
                }
            )
            continue

        seller = sellers[offering["seller_id"]]
        seller_score = seller_reliability(seller["reliability_metrics"])
        bag_score = bag_confidence(offering["bag_metrics"])
        score = recommendation(bag_score, seller_score)
        tier = tier_for(
            score,
            exact_variant=exact_variant,
            independent_authors=len(authors),
            unresolved_major_negative=major_negative,
            quality_evidence=bool(quality_rows),
        )
        rows.append(
            {
                "offering_id": offering["id"],
                "seller_id": offering["seller_id"],
                "bag_id": offering["bag_id"],
                "seller_reliability": seller_score,
                "bag_confidence": bag_score,
                "recommendation_score": score,
                "tier": tier,
                "rank_status": "ranked",
                "independent_authors": len(authors),
                "exact_variant_evidence": exact_variant,
                "unresolved_major_negative": major_negative,
            }
        )

    rows.sort(
        key=lambda row: (
            row["recommendation_score"] is None,
            -(row["recommendation_score"] or -1),
            row["offering_id"],
        )
    )
    return {
        "generated_at": date.today().isoformat(),
        "method_version": "1.0.0",
        "rankings": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = DATA / "rankings.json"
    generated = generate()
    if args.check:
        current = json.loads(target.read_text(encoding="utf-8"))
        comparable = {**generated, "generated_at": current.get("generated_at")}
        if current != comparable:
            print("rankings.json is stale; run python3 scripts/score.py")
            return 1
        print(f"rankings are deterministic ({len(current['rankings'])} offerings)")
        return 0
    target.write_text(json.dumps(generated, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(generated['rankings'])} rankings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
