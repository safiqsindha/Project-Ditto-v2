#!/usr/bin/env python3
"""
Acquire Terminal-Bench 2.0 trajectories and save usable ones as JSONL.

Usage
-----
    python scripts/acquire_tb.py \\
        --source <local-path-or-hf-dataset-id> \\
        --out data/terminal_bench/ \\
        --target 500

Source formats accepted
-----------------------
- Local directory of .json / .jsonl files (inspect-ai eval logs)
- Local .json eval log file (dict with "samples" list)
- Local .jsonl file (one sample per line)
- HuggingFace dataset ID (e.g. "terminal-bench/terminal-bench-2.0")

Gate 1 check
------------
Exits with code 1 if fewer than --gate-threshold usable trajectories are
found, as required by spec §5 (Gate 1: ≥ 400 usable TB trajectories).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parser_tb import filter_trajectory, parse_tb_trajectory, TrajectoryLog


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

def _iter_local(path: Path):
    """Yield raw sample dicts from a local file or directory."""
    if path.is_dir():
        # Prefer JSONL files (one sample per line) then JSON eval logs
        found_any = False
        for suffix in ("*.jsonl", "*.json"):
            for fp in sorted(path.glob(suffix)):
                found_any = True
                yield from _iter_file(fp)
        if not found_any:
            raise FileNotFoundError(f"No .json/.jsonl files found in {path}")
    else:
        yield from _iter_file(path)


def _iter_file(fp: Path):
    """Yield raw sample dicts from a single .json or .jsonl file."""
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
                # inspect-ai eval log: samples are under "samples" key
                if "samples" in data:
                    yield from data["samples"]
                else:
                    yield data


def _iter_huggingface(dataset_id: str, split: str = "train"):
    """Yield raw sample dicts from a HuggingFace dataset."""
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
    """Dispatch to the appropriate loader based on whether source is a path."""
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
        description="Acquire Terminal-Bench 2.0 trajectories"
    )
    parser.add_argument(
        "--source", required=True,
        help="Local path (file or dir) or HuggingFace dataset ID",
    )
    parser.add_argument(
        "--out", required=True,
        help="Output directory (receives trajectories.jsonl + SOURCE.md)",
    )
    parser.add_argument(
        "--target", type=int, default=500,
        help="Maximum number of usable trajectories to save (default: 500)",
    )
    parser.add_argument(
        "--gate-threshold", type=int, default=400,
        help="Minimum usable count required by Gate 1 (default: 400)",
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
            log = parse_tb_trajectory(raw)
        except (ValueError, KeyError, TypeError) as exc:
            total_parse_errors += 1
            if total_parse_errors <= 5:
                print(f"  [skip] parse error on record {total_seen}: {exc}", file=sys.stderr)
            continue

        if filter_trajectory(log, min_events=args.min_events):
            usable.append(log)
            if len(usable) >= args.target:
                break

    # Write JSONL output
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

    # Gate 1 check
    if len(usable) < args.gate_threshold:
        print(
            f"\nGATE 1 FAIL: {len(usable)} usable trajectories < "
            f"{args.gate_threshold} required.  "
            "Stop and find alternative sources (see SPEC.md §5).",
            file=sys.stderr,
        )
        sys.exit(1)
    else:
        print(f"\nGATE 1 PASS: {len(usable)} >= {args.gate_threshold}")


if __name__ == "__main__":
    main()
