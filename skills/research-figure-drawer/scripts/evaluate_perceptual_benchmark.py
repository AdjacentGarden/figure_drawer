#!/usr/bin/env python3
"""Aggregate a five-reviewer, reference-guided scientific-figure blind test.

This is deliberately separate from pixel identity.  It cannot certify that two
images are numerically 95% alike; it records five independent human/agent
judgements of visual similarity and origin distinguishability.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate(verdicts: list[dict], minimum_similarity: float = 95.0) -> dict:
    if len(verdicts) != 5:
        raise ValueError("Exactly five independent verdicts are required")
    reviewer_ids = [str(v.get("reviewer_id", "")) for v in verdicts]
    if not all(reviewer_ids) or len(set(reviewer_ids)) != 5:
        raise ValueError("Five distinct nonempty reviewer_id values are required")
    results = []
    for v in verdicts:
        score = float(v["similarity_0_100"])
        distinguishable = v["reliably_distinguishable"]
        if not 0 <= score <= 100 or not isinstance(distinguishable, bool):
            raise ValueError("Invalid similarity or distinguishability field")
        results.append({
            "reviewer_id": str(v["reviewer_id"]),
            "similarity_0_100": score,
            "reliably_distinguishable": distinguishable,
            "original_guess": v.get("original_guess", "uncertain"),
            "confidence_0_1": v.get("confidence_0_1"),
            "passed": score >= minimum_similarity and not distinguishable,
        })
    passed = all(r["passed"] for r in results)
    return {
        "schema_version": 1,
        "mode": "perceptual-95-blind",
        "minimum_similarity_each": minimum_similarity,
        "reviewer_count": 5,
        "similarity_min": min(r["similarity_0_100"] for r in results),
        "similarity_mean": round(sum(r["similarity_0_100"] for r in results) / 5, 2),
        "reliably_distinguishable_count": sum(r["reliably_distinguishable"] for r in results),
        "verdicts": results,
        "passed": passed,
        "claim_boundary": "A passing blind test supports perceptual parity for this case and reviewer panel; it does not prove pixel identity, generalization to other figures, or that every PPTX object is editable."
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--verdict", action="append", type=Path,
                        help="One JSON verdict file; provide five, each from a distinct reviewer")
    source.add_argument("--verdicts-json", type=Path,
                        help="One JSON array containing five independent reviewer verdicts")
    parser.add_argument("--minimum-similarity", type=float, default=95.0)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    verdicts = (json.loads(args.verdicts_json.read_text(encoding="utf-8"))
                if args.verdicts_json else
                [json.loads(p.read_text(encoding="utf-8")) for p in args.verdict])
    report = evaluate(verdicts, args.minimum_similarity)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
