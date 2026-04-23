"""
Supplementary Analysis 3: Error analysis on model responses.

REQUIREMENT: results/raw/ must contain per-chain response JSON files
(one file per chain_id, with fields: chain_id, model, response, cutoff_k, source).

STATUS: results/raw/ was not committed to this repository.
This script documents the expected format and will run to completion if
raw/ is populated. It exits gracefully with a clear message if data is absent.

To populate results/raw/ from the local evaluation run:
    git add results/raw/
    git commit -m "Add raw evaluation responses"
    git push origin main
"""

from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

SCORED = Path("results/scored.json")
RAW_DIR = Path("results/raw")
CHAINS_REAL = Path("chains/real")
CHAINS_SHUFFLED = Path("chains/shuffled")
OUT_DIR = Path("supplementary/error_analysis")

MODELS = ["haiku", "sonnet"]
SOURCES = ["tb", "swe"]
SAMPLE_N = 20
SEED = 42


def check_data_available() -> bool:
    raw_files = list(RAW_DIR.glob("**/*.json"))
    # Filter to actual result files (not the blinded manifest)
    result_files = [f for f in raw_files if f.stat().st_size > 0]
    return len(result_files) > 0


def load_chains() -> dict[str, dict]:
    index = {}
    for d in [CHAINS_REAL, CHAINS_SHUFFLED]:
        for f in sorted(d.glob("**/*.jsonl")):
            try:
                chain = json.loads(f.read_text().strip().split("\n")[0])
                index[chain["chain_id"]] = chain
            except Exception:
                pass
    return index


def describe_expected_output():
    """Describe what this analysis would produce if results/raw/ were populated."""
    print("=" * 70)
    print("Analysis 3: Error Analysis")
    print("=" * 70)
    print()
    print("STATUS: results/raw/ is empty — raw model responses not committed.")
    print()
    print("This analysis requires per-chain response files in results/raw/.")
    print("Each file should contain:")
    print("  {")
    print('    "chain_id": "tb_0042_some-task",')
    print('    "model": "haiku",')
    print('    "response": "use file_b",')
    print('    "cutoff_k": 11,')
    print('    "source": "tb",')
    print('    "seed": 42,')
    print('    "temperature": 0.0')
    print("  }")
    print()
    print("Output this analysis would produce:")
    print("  supplementary/error_analysis/haiku_tb_real_matches.jsonl")
    print("  supplementary/error_analysis/haiku_tb_real_failures.jsonl")
    print("  supplementary/error_analysis/haiku_swe_real_matches.jsonl")
    print("  ... (8 files total: 4 cells × 2 conditions)")
    print()
    print("Each record would contain:")
    print("  - chain_id, model, source, condition (real/shuffled)")
    print("  - model_response, ground_truth_entity, constraint_type_at_cutoff")
    print("  - last_5_constraints (context window)")
    print("  - top_3_reference_actions (from reference distribution)")
    print("  - match (0 or 1)")
    print("  - qualitative_observation (one-line note on why match/failure)")
    print()
    print("To run this analysis:")
    print("  1. Push results/raw/ from local machine")
    print("  2. Re-run: python3 scripts/supplementary/03_error_analysis.py")
    print()


def run_analysis(chain_index: dict[str, dict]) -> dict:
    """Sample cases and produce error analysis output."""
    raw_files = sorted(RAW_DIR.glob("**/*.json"))
    results_by_cell: dict[tuple[str, str], dict[str, list]] = defaultdict(
        lambda: {"real_match": [], "real_fail": [], "shuf_match": [], "shuf_fail": []}
    )

    for f in raw_files:
        try:
            r = json.loads(f.read_text())
        except Exception:
            continue
        if "chain_id" not in r or "response" not in r:
            continue

        chain_id = r["chain_id"]
        model = r.get("model", "unknown")
        source = r.get("source", "unknown")
        is_real = "_shuffled_" not in chain_id
        condition = "real" if is_real else "shuffled"
        chain = chain_index.get(chain_id, {})
        if not chain:
            continue

        cutoff_k = r.get("cutoff_k", chain.get("cutoff_k", 0))
        constraints = chain.get("constraints", [])
        if cutoff_k >= len(constraints):
            continue

        gt = constraints[cutoff_k]
        ctype = gt.get("type", "")
        response = r.get("response", "").strip().lower()

        # Entity match (same logic as scorer.py)
        from src.scorer import extract_entity_from_constraint
        from src.normalize import normalize_action
        entity = extract_entity_from_constraint(gt)
        if entity is None:
            continue
        match = 1 if normalize_action(entity) in normalize_action(response) else 0

        record = {
            "chain_id": chain_id,
            "model": model,
            "source": source,
            "condition": condition,
            "model_response": r.get("response", ""),
            "ground_truth_entity": entity,
            "constraint_type_at_cutoff": ctype,
            "last_5_constraints": constraints[max(0, cutoff_k - 5):cutoff_k],
            "match": match,
        }

        cell_key = (model, source)
        bucket = f"{condition}_{'match' if match else 'fail'}"
        results_by_cell[cell_key][bucket].append(record)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    output_files = []

    for (model, source), buckets in results_by_cell.items():
        for bucket, records in buckets.items():
            sampled = rng.sample(records, min(SAMPLE_N, len(records)))
            cond, outcome = bucket.split("_")
            fname = f"{model}_{source}_{cond}_{outcome}s.jsonl"
            out_path = OUT_DIR / fname
            with open(out_path, "w") as fp:
                for rec in sampled:
                    fp.write(json.dumps(rec) + "\n")
            output_files.append(str(out_path))

    return {"files_written": output_files, "status": "complete"}


def main():
    if not check_data_available():
        describe_expected_output()

        # Write a placeholder JSON so the analysis is not entirely missing
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        placeholder = {
            "status": "raw_results_not_available",
            "message": (
                "results/raw/ was not committed to this repository. "
                "Push raw evaluation responses and re-run this script."
            ),
            "expected_files": [
                f"{model}_{source}_{cond}_{outcome}s.jsonl"
                for model in MODELS
                for source in SOURCES
                for cond in ["real", "shuffled"]
                for outcome in ["match", "failure"]
            ],
        }
        (OUT_DIR / "_status.json").write_text(json.dumps(placeholder, indent=2))
        sys.exit(0)

    print("results/raw/ found — running analysis...")
    chain_index = load_chains()
    result = run_analysis(chain_index)
    print(f"Written {len(result['files_written'])} output files.")
    for f in result["files_written"]:
        print(f"  {f}")


if __name__ == "__main__":
    main()
