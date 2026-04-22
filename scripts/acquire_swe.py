#!/usr/bin/env python3
"""
Acquire SWE-bench Verified agent trajectories and save usable ones as JSONL.

Usage
-----
    python scripts/acquire_swe.py \\
        --source <local-path-or-hf-dataset-id> \\
        --out data/swe_bench_verified/ \\
        --target 500

Source formats accepted
-----------------------
- Local directory of .json / .jsonl trajectory files
- Local .jsonl file (one SWE-agent trajectory per line)
- HuggingFace dataset ID (e.g. "princeton-nlp/SWE-agent-trajectories")

Recommended HuggingFace source
-------------------------------
SWE-agent trajectories for SWE-bench Verified are available as separate
prediction submission datasets.  Known public datasets include:
  - "SWE-bench/trajectories"
  - "princeton-nlp/SWE-bench_Verified"  (task descriptions only, not trajectories)

If you have a local directory of SWE-agent trajectory JSON files (one file per
instance), pass the directory path as --source.

Gate 2 check
------------
Exits with code 1 if fewer than --gate-threshold usable trajectories are
found, as required by spec §5 (Gate 2: ≥ 400 usable SWE-bench trajectories).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parser_swe import filter_trajectory, parse_swe_trajectory, TrajectoryLog


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def _log_to_dict(log: TrajectoryLog) -> dict:
    return {
        "task_id": log.task_id,
        "model": log.model,
        "agent": log.agent,
        "outcome": log.outcome,
        "source": log.source,
        "events": [
            {"type": e.type, "step": e.step, "args": e.args}
            for e in log.events
        ],
    }


# ---------------------------------------------------------------------------
# Source loaders
# ---------------------------------------------------------------------------

def _iter_file(fp: Path):
    """Yield raw trajectory dicts from a single .json or .jsonl file."""
    with fp.open(encoding="utf-8") as fh:
        if fp.suffix == ".jsonl":
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)
        else:
            data = json.load(fh)
            if isinstance(data, list):
                yield from data
            elif isinstance(data, dict):
                # Single trajectory file (one JSON object per file)
                yield data


def _iter_local(path: Path):
    """Yield raw trajectory dicts from a local file or directory."""
    if path.is_dir():
        found_any = False
        for suffix in ("*.jsonl", "*.json"):
            for fp in sorted(path.glob(suffix)):
                found_any = True
                yield from _iter_file(fp)
        if not found_any:
            raise FileNotFoundError(f"No .json/.jsonl files found in {path}")
    else:
        yield from _iter_file(path)


def _iter_huggingface(dataset_id: str, split: str = "train"):
    """Yield raw trajectory dicts from a HuggingFace dataset."""
    try:
        from datasets import load_dataset
    except ImportError:
        print(
            "ERROR: 'datasets' package not installed.  "
            "Run: pip install datasets",
            file=sys.stderr,
        )
        sys.exit(1)

    import os
    hf_token = os.environ.get("HF_TOKEN")
    print(f"Loading HuggingFace dataset: {dataset_id} (split={split})")
    ds = load_dataset(dataset_id, split=split, token=hf_token)
    for item in ds:
        yield dict(item)


def _iter_source(source: str):
    p = Path(source)
    if p.exists():
        yield from _iter_local(p)
    else:
        yield from _iter_huggingface(source)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Acquire SWE-bench Verified agent trajectories"
    )
    parser.add_argument(
        "--source", required=True,
        help="Local path (file or dir) or HuggingFace dataset ID",
    )
    parser.add_argument(
        "--out", required=True,
        help="Output directory (receives trajectories.jsonl)",
    )
    parser.add_argument(
        "--target", type=int, default=500,
        help="Maximum number of usable trajectories to save (default: 500)",
    )
    parser.add_argument(
        "--gate-threshold", type=int, default=400,
        help="Minimum usable count required by Gate 2 (default: 400)",
    )
    parser.add_argument(
        "--min-events", type=int, default=15,
        help="Minimum events per trajectory (default: 15)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    usable: list[TrajectoryLog] = []
    total_seen = 0
    total_parse_errors = 0

    print(f"Reading from: {args.source}")
    for raw in _iter_source(args.source):
        total_seen += 1
        try:
            log = parse_swe_trajectory(raw)
        except (ValueError, KeyError, TypeError) as exc:
            total_parse_errors += 1
            if total_parse_errors <= 5:
                print(f"  [skip] parse error on record {total_seen}: {exc}", file=sys.stderr)
            continue

        if filter_trajectory(log, min_events=args.min_events):
            usable.append(log)
            if len(usable) >= args.target:
                break

    out_file = out_dir / "trajectories.jsonl"
    with out_file.open("w", encoding="utf-8") as fh:
        for log in usable:
            fh.write(json.dumps(_log_to_dict(log)) + "\n")

    print(
        f"\nSummary:"
        f"\n  Records examined : {total_seen}"
        f"\n  Parse errors     : {total_parse_errors}"
        f"\n  Usable saved     : {len(usable)}"
        f"\n  Output file      : {out_file}"
    )

    # Gate 2 check
    if len(usable) < args.gate_threshold:
        print(
            f"\nGATE 2 FAIL: {len(usable)} usable trajectories < "
            f"{args.gate_threshold} required.  "
            "Stop and find alternative sources (see SPEC.md §5).",
            file=sys.stderr,
        )
        sys.exit(1)
    else:
        print(f"\nGATE 2 PASS: {len(usable)} >= {args.gate_threshold}")


if __name__ == "__main__":
    main()
