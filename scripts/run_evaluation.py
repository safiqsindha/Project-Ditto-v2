#!/usr/bin/env python3
"""
Full evaluation script — Session 11.

Submits one Anthropic Messages Batch per source (tb, swe, human), covering
all chains × 2 models × 3 seeds.  Results written to results/raw/<source>/
and results/blinded/.

Usage
-----
    python scripts/run_evaluation.py                    # all three sources
    python scripts/run_evaluation.py --source tb        # single source
    python scripts/run_evaluation.py --source tb --n 5  # quick smoke-test

Cost estimate (Batches API, 50% off):
    ~2,300 calls × 350 tokens avg → < $1 total
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.runner import run_batch_evaluation, MODELS, EVAL_CONFIGS

_SOURCES = ["tb", "swe", "human"]

_CHAINS_REAL = {
    "tb":    Path("chains/real/tb"),
    "swe":   Path("chains/real/swe"),
    "human": Path("chains/real/human"),
}
_CHAINS_SHUFFLED = {
    "tb":    Path("chains/shuffled/tb"),
    "swe":   Path("chains/shuffled/swe"),
    "human": Path("chains/shuffled/human"),
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run full Ditto v2 evaluation via Batches API"
    )
    parser.add_argument(
        "--source", choices=_SOURCES + ["all"], default="all",
        help="Which source to evaluate (default: all)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("results/raw"),
        help="Root directory for raw results",
    )
    parser.add_argument(
        "--n", type=int, default=None,
        help="Limit to first N chain files per source/condition (smoke-test)",
    )
    args = parser.parse_args()

    sources = _SOURCES if args.source == "all" else [args.source]

    print(f"Evaluation matrix: {sources} × {list(MODELS)} × {len(EVAL_CONFIGS)} configs")
    print(f"Mode: Batches API (50% cost reduction)")
    print()

    all_summaries = []

    for source in sources:
        for condition, chains_dir in [("real", _CHAINS_REAL[source]),
                                      ("shuffled", _CHAINS_SHUFFLED[source])]:
            if not chains_dir.exists():
                print(f"[skip] {chains_dir} does not exist")
                continue

            chain_count = len(list(chains_dir.glob("*.jsonl")))
            if chain_count == 0:
                print(f"[skip] {chains_dir} is empty")
                continue

            print(f"=== {source.upper()} / {condition} ({chain_count} chains) ===")
            summary = run_batch_evaluation(
                chains_dir=chains_dir,
                source=source,
                output_dir=args.output_dir,
                n=args.n,
            )
            summary["condition"] = condition
            all_summaries.append(summary)
            print()

    # Write run manifest
    manifest_path = args.output_dir / "run_manifest.json"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w") as fh:
        json.dump(all_summaries, fh, indent=2)

    total_succeeded = sum(s["succeeded"] for s in all_summaries)
    total_errored = sum(s["errored"] for s in all_summaries)
    print(f"All done: {total_succeeded} succeeded, {total_errored} errored")
    print(f"Manifest: {manifest_path}")

    if total_errored > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
