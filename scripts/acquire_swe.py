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
- HuggingFace dataset ID (SWE-agent Format A: action/observation steps)
- HuggingFace dataset ID (nebius format: trajectory list with role/text turns)
  e.g. "nebius/SWE-agent-trajectories"
- HuggingFace dataset ID (chat-messages format)
  e.g. "JetBrains-Research/agent-trajectories-swe-bench-test-minus-verified"

Format auto-detection
---------------------
Records with a "trajectory" key whose turns have a "text" field (and role
"ai") are treated as nebius format.  Records with "traj" (action/observation
steps) or "messages" (chat format) use the existing SWE parser directly.

Recommended HuggingFace source
-------------------------------
  nebius/SWE-agent-trajectories  (80K records, SWE-agent, has resolved label)

Gate 2 check
------------
Exits with code 1 if fewer than --gate-threshold usable trajectories are
found, as required by spec §5 (Gate 2: ≥ 400 usable SWE-bench trajectories).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parser_swe import filter_trajectory, parse_swe_trajectory, TrajectoryLog


# ---------------------------------------------------------------------------
# Nebius format converter
# ---------------------------------------------------------------------------

_CODE_BLOCK_RE = re.compile(r"```(?:\w+)?\n?(.*?)\n?```", re.DOTALL)


def _extract_action_from_ai_turn(text: str) -> str:
    """Extract the shell command from an AI turn's ``` code block."""
    m = _CODE_BLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    # Fall back: last non-empty line of thought text (no code block)
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    return lines[-1] if lines else ""


def _is_nebius_record(raw: dict) -> bool:
    """Return True if this is a nebius/SWE-agent-trajectories format record."""
    traj = raw.get("trajectory")
    if not isinstance(traj, list) or not traj:
        return False
    first = traj[0] if isinstance(traj[0], dict) else {}
    # Nebius turns have "text" and "role" keys (role can be "ai"); no "action" key
    return "text" in first and "action" not in first


def _convert_nebius_to_swe(raw: dict) -> dict:
    """
    Convert a nebius/SWE-agent-trajectories record to SWE-agent Format A.

    The nebius format uses role=system/user/ai turns with a "text" field.
    We extract (action, observation) pairs from consecutive ai→user turn pairs
    and map them to Format A's action/observation step list.
    """
    trajectory = raw.get("trajectory", [])

    steps: list[dict] = []
    pending_action: str | None = None

    for turn in trajectory:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role", "")
        text = turn.get("text") or ""

        if role == "ai":
            action = _extract_action_from_ai_turn(text)
            if action:
                pending_action = action

        elif role == "user" and pending_action is not None:
            steps.append({"action": pending_action, "observation": text})
            pending_action = None

    # Map target (bool) to exit_status the SWE parser understands
    resolved = raw.get("target", False)
    exit_status = "submitted" if resolved else "early_exit"

    return {
        "instance_id": raw.get("instance_id", "unknown"),
        "model_name_or_path": raw.get("model_name", "unknown"),
        "agent": raw.get("agent", "swe-agent"),
        "traj": steps,
        "info": {"exit_status": exit_status},
    }


def _is_jetbrains_record(raw: dict) -> bool:
    """Return True if this is a JetBrains chat-messages format record."""
    msgs = raw.get("messages")
    return (
        isinstance(msgs, list)
        and bool(msgs)
        and isinstance(msgs[0], dict)
        and "role" in msgs[0]
        and "content" in msgs[0]
        and "instance_id" in raw
    )


def _convert_jetbrains_to_swe(raw: dict) -> dict:
    """Convert JetBrains agent-trajectories record to SWE Format A."""
    messages = raw.get("messages", [])
    steps: list[dict] = []
    pending_action: str | None = None

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "") or ""

        if role == "assistant":
            # Extract bash command from code block
            m = _CODE_BLOCK_RE.search(content)
            if m:
                pending_action = m.group(1).strip()
            elif content.strip():
                # No code block — take the full text as action
                pending_action = content.strip()

        elif role == "user" and pending_action is not None:
            steps.append({"action": pending_action, "observation": content})
            pending_action = None

    resolved = raw.get("resolved")
    exit_status_raw = str(raw.get("exit_status", "")).lower()
    if resolved is True:
        exit_status = "submitted"
    elif resolved is False:
        exit_status = "early_exit"
    elif "submitted" in exit_status_raw:
        exit_status = "submitted"
    else:
        exit_status = "early_exit"

    return {
        "instance_id": raw.get("instance_id", "unknown"),
        "model_name_or_path": (
            raw.get("selected_models", ["unknown"])[0]
            if raw.get("selected_models")
            else "unknown"
        ),
        "agent": "swe-agent",
        "traj": steps,
        "info": {"exit_status": exit_status},
    }


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
    nebius_count = 0
    jetbrains_count = 0
    native_count = 0

    print(f"Reading from: {args.source}")
    for raw in _iter_source(args.source):
        total_seen += 1
        try:
            if _is_nebius_record(raw):
                converted = _convert_nebius_to_swe(raw)
                log = parse_swe_trajectory(converted)
                nebius_count += 1
            elif _is_jetbrains_record(raw):
                converted = _convert_jetbrains_to_swe(raw)
                log = parse_swe_trajectory(converted)
                jetbrains_count += 1
            else:
                log = parse_swe_trajectory(raw)
                native_count += 1
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
        f"\n  Nebius format    : {nebius_count}"
        f"\n  JetBrains format : {jetbrains_count}"
        f"\n  Native SWE format: {native_count}"
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
