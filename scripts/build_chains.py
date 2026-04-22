#!/usr/bin/env python3
"""
Build constraint chain JSONL files from raw trajectory data.

Full pipeline (per trajectory):
  1. Load  — read trajectories.jsonl from data/<source>/
  2. Parse — reconstruct TrajectoryEvent objects
  3. Aggregate — compress events (source-specific rules)
  4. Translate — T-code: events → Constraint dataclass instances
  5. Observability — apply asymmetric information reveal
  6. Filter  — is_valid_chain() must pass; skip invalid chains
  7. Render  — abstract English (leakage check runs inside render_chain)
  8. Shuffle — three seeded shuffled variants per chain (seeds 42, 1337, 7919)
  9. Save   — real chain to chains/real/<source>/<id>.jsonl
              shuffled variants to chains/shuffled/<source>/<id>_shuffled_<seed>.jsonl

Usage
-----
    python scripts/build_chains.py \\
        --source tb \\
        --data data/terminal_bench/ \\
        --out-real chains/real/tb/ \\
        --out-shuffled chains/shuffled/tb/

    python scripts/build_chains.py \\
        --source swe \\
        --data data/swe_bench_verified/ \\
        --out-real chains/real/swe/ \\
        --out-shuffled chains/shuffled/swe/

    python scripts/build_chains.py \\
        --source human \\
        --data data/human_sessions/ \\
        --out-real chains/real/human/ \\
        --out-shuffled chains/shuffled/human/

Gate 3 check
------------
After building, --gate3 checks that ≥ 20 rendered chains per source
pass the leakage check.  Exits with code 1 if the gate fails.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.aggregation import aggregate_events
from src.filter import is_valid_chain
from src.observability import apply_asymmetric_observability
from src.parser_tb import TrajectoryEvent
from src.renderer import render_chain, check_programming_leakage
from src.shuffler import shuffle_chain
from src.translation import (
    constraint_to_dict,
    constraint_from_dict,
    translate_trajectory,
)


# Seeds for shuffled control condition (spec §5.3)
_SHUFFLE_SEEDS = [42, 1337, 7919]

# Minimum chains required for Gate 3 leakage check (spec §5 Gate 3)
_GATE3_MIN_CHAINS = 20


# ---------------------------------------------------------------------------
# Trajectory loading (raw JSONL → list[TrajectoryEvent])
# ---------------------------------------------------------------------------

def _load_events(record: dict) -> list[TrajectoryEvent]:
    """Reconstruct TrajectoryEvent objects from a serialised trajectory record."""
    raw_events = record.get("events", [])
    events = []
    for e in raw_events:
        events.append(TrajectoryEvent(
            type=e["type"],
            step=e["step"],
            args=e.get("args", {}),
            raw=e.get("raw", {}),
        ))
    return events


def _iter_records(data_dir: Path) -> list[dict]:
    """Yield all trajectory records from trajectories.jsonl in data_dir."""
    traj_file = data_dir / "trajectories.jsonl"
    if not traj_file.exists():
        print(f"  WARNING: {traj_file} not found — no trajectories to process",
              file=sys.stderr)
        return []

    records = []
    with traj_file.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"  WARNING: line {line_no}: JSON decode error — {exc}",
                      file=sys.stderr)
    return records


# ---------------------------------------------------------------------------
# Chain serialisation
# ---------------------------------------------------------------------------

def _chain_to_dict(
    chain_id: str,
    source: str,
    task_id: str,
    constraints: list,
    active_pairs: list[tuple[str, str]],
    rendered: str,
) -> dict:
    """Serialise a real chain to a JSON-compatible dict."""
    constraint_dicts = [constraint_to_dict(c) for c in constraints]
    cutoff_k = len(constraint_dicts) // 2
    action_at_step = constraint_dicts[cutoff_k]["type"] if constraint_dicts else None
    per_step_actions = [
        {"step_idx": i, "action": c["type"]}
        for i, c in enumerate(constraint_dicts)
    ]
    return {
        "chain_id": chain_id,
        "match_id": chain_id,
        "source": source,
        "task_id": task_id,
        "constraints": constraint_dicts,
        "active_pair_by_step": list(active_pairs),
        "rendered": rendered,
        "cutoff_k": cutoff_k,
        "action_at_step": action_at_step,
        "per_step_actions": per_step_actions,
    }


def _save_chain(chain_dict: dict, out_dir: Path) -> None:
    """Write a chain dict to out_dir/<chain_id>.jsonl (one record per file)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{chain_dict['chain_id']}.jsonl"
    with out_file.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(chain_dict) + "\n")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def process_trajectory(
    record: dict,
    source: str,
    out_real: Path,
    out_shuffled: Path,
    verbose: bool = False,
    record_idx: int = 0,
) -> tuple[bool, str]:
    """
    Run the full pipeline for one trajectory record.

    Returns
    -------
    (success, reason) — reason is "" on success or a short rejection message.
    """
    task_id = record.get("task_id", "unknown")

    # 1. Reconstruct events
    events = _load_events(record)
    if not events:
        return False, "no_events"

    # 2. Aggregate
    try:
        agg_events, _agg_log = aggregate_events(events, source)
    except Exception as exc:
        return False, f"aggregate_error:{exc}"

    # 3. Translate (T-code)
    try:
        constraints, active_pairs = translate_trajectory(agg_events, source)
    except Exception as exc:
        return False, f"translate_error:{exc}"

    # 4. Asymmetric observability
    try:
        from src.observability import apply_asymmetric_observability_with_indices
        constraints, kept_indices = apply_asymmetric_observability_with_indices(
            translate_trajectory(agg_events, source)[0]
        )
        active_pairs = [active_pairs[i] for i in kept_indices]
    except Exception as exc:
        return False, f"observability_error:{exc}"

    # 4b. Truncate to spec max length (20-40 constraints).
    # Chains longer than 40 are trimmed to their first 40 constraints;
    # this preserves temporal order and the opening sub-goal structure.
    _MAX_LEN = 40
    if len(constraints) > _MAX_LEN:
        constraints = constraints[:_MAX_LEN]
        active_pairs = active_pairs[:_MAX_LEN]

    # 5. Filter
    if not is_valid_chain(constraints):
        return False, "filter_fail"

    # 6. Render (leakage check inside render_chain)
    try:
        rendered = render_chain(constraints, perspective=source)
    except ValueError as exc:
        return False, f"leakage:{exc}"
    except Exception as exc:
        return False, f"render_error:{exc}"

    # 7. Save real chain
    # Include record_idx to avoid collisions when multiple trajectories share
    # the same task_id (e.g., same task evaluated under different models).
    chain_id = f"{source}_{record_idx:04d}_{task_id}"
    chain_dict = _chain_to_dict(
        chain_id=chain_id,
        source=source,
        task_id=task_id,
        constraints=constraints,
        active_pairs=active_pairs,
        rendered=rendered,
    )
    _save_chain(chain_dict, out_real)

    # 8. Shuffle + save shuffled variants
    for seed in _SHUFFLE_SEEDS:
        shuffled = shuffle_chain(chain_dict, seed=seed)

        # Render shuffled variant (leakage check)
        shuffled_constraints = [constraint_from_dict(c) for c in shuffled["constraints"]]
        try:
            shuffled_rendered = render_chain(shuffled_constraints, perspective=source)
        except ValueError as exc:
            # Skip this seed variant but don't fail the whole trajectory
            if verbose:
                print(f"  WARNING: shuffle seed {seed} leakage for {task_id}: {exc}",
                      file=sys.stderr)
            continue
        shuffled["rendered"] = shuffled_rendered
        _save_chain(shuffled, out_shuffled)

    return True, ""


# ---------------------------------------------------------------------------
# Gate 3 check
# ---------------------------------------------------------------------------

def gate3_check(out_real: Path, min_chains: int = _GATE3_MIN_CHAINS) -> bool:
    """
    Verify that ≥ min_chains chain files exist and all pass the leakage check.

    Returns True if gate passes.
    """
    chain_files = list(out_real.glob("*.jsonl"))
    if len(chain_files) < min_chains:
        print(
            f"GATE 3 FAIL: only {len(chain_files)} chains found "
            f"(need {min_chains})",
            file=sys.stderr,
        )
        return False

    leakage_failures = 0
    sample = chain_files[:min_chains]
    for cf in sample:
        with cf.open(encoding="utf-8") as fh:
            record = json.loads(fh.read().strip())
        rendered = record.get("rendered", "")
        leaked = check_programming_leakage(rendered)
        if leaked:
            print(
                f"GATE 3 FAIL: leakage in {cf.name}: {leaked}",
                file=sys.stderr,
            )
            leakage_failures += 1

    if leakage_failures:
        print(
            f"GATE 3 FAIL: {leakage_failures} chains with programming vocabulary leakage",
            file=sys.stderr,
        )
        return False

    print(f"GATE 3 PASS: {len(chain_files)} chains, {min_chains} checked — no leakage")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build constraint chain JSONL files from trajectory data"
    )
    parser.add_argument(
        "--source", required=True, choices=["tb", "swe", "human"],
        help="Trajectory source: tb | swe | human",
    )
    parser.add_argument(
        "--data", required=True,
        help="Directory containing trajectories.jsonl",
    )
    parser.add_argument(
        "--out-real", required=True,
        help="Output directory for real chains",
    )
    parser.add_argument(
        "--out-shuffled", required=True,
        help="Output directory for shuffled chains",
    )
    parser.add_argument(
        "--gate3", action="store_true",
        help="Run Gate 3 leakage check after building",
    )
    parser.add_argument(
        "--gate3-threshold", type=int, default=_GATE3_MIN_CHAINS,
        help=f"Minimum chains for Gate 3 (default: {_GATE3_MIN_CHAINS})",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print per-trajectory status",
    )
    args = parser.parse_args()

    data_dir   = Path(args.data)
    out_real   = Path(args.out_real)
    out_shuffled = Path(args.out_shuffled)

    records = _iter_records(data_dir)
    print(f"Loaded {len(records)} trajectory records from {data_dir}")

    stats = {
        "total":        len(records),
        "accepted":     0,
        "no_events":    0,
        "filter_fail":  0,
        "leakage":      0,
        "other_error":  0,
    }

    for i, record in enumerate(records):
        task_id = record.get("task_id", f"idx_{i}")
        success, reason = process_trajectory(
            record, args.source, out_real, out_shuffled,
            verbose=args.verbose, record_idx=i,
        )
        if success:
            stats["accepted"] += 1
            if args.verbose:
                print(f"  [{i+1}/{len(records)}] {task_id}: OK")
        else:
            key = "other_error"
            if reason == "no_events":
                key = "no_events"
            elif reason == "filter_fail":
                key = "filter_fail"
            elif reason.startswith("leakage"):
                key = "leakage"
            stats[key] += 1
            if args.verbose:
                print(f"  [{i+1}/{len(records)}] {task_id}: SKIP ({reason})")

    print("\nBuild summary:")
    for k, v in stats.items():
        print(f"  {k:20s}: {v}")
    print(f"\n  Real chains     : {out_real}")
    print(f"  Shuffled chains : {out_shuffled}")

    if args.gate3:
        print()
        passed = gate3_check(out_real, min_chains=args.gate3_threshold)
        if not passed:
            sys.exit(1)


if __name__ == "__main__":
    main()
