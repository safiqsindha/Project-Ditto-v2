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
- HuggingFace dataset ID (inspect-ai format, e.g. "terminal-bench/terminal-bench-2.0")
- HuggingFace dataset ID (ATIF/terminus format, e.g.
  "mlfoundations-dev/terminal-bench-traces-local"
  "DCAgent/claude-sonnet-4-5-terminal-bench-2")

Format auto-detection
---------------------
Records with a "conversations" key use the ATIF terminus format (DCAgent /
mlfoundations-dev datasets).  Records with a "messages" key use the inspect-ai
eval log format.  Local files may mix both.

Gate 1 check
------------
Exits with code 1 if fewer than --gate-threshold usable trajectories are
found, as required by spec §5 (Gate 1: ≥ 400 usable TB trajectories).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parser_tb import (
    filter_trajectory,
    parse_tb_trajectory,
    TrajectoryEvent,
    TrajectoryLog,
    _classify_command,
    _detect_test_framework,
    _ERROR_RE,
    _extract_error_class,
    _extract_file_path,
    _extract_test_outcome,
    _count_tests,
)


# ---------------------------------------------------------------------------
# ATIF (terminus / DCAgent / mlfoundations) format parser
# ---------------------------------------------------------------------------

_TB_PASS_RE = re.compile(
    r"(TEST_\w+:\s*PASS"
    r"|\d+\s+passed(?:\s+in\s+[\d.]+s)?"
    r"|\bOK\b"
    r"|all\s+tests?\s+pass(?:ed)?"
    r"|Tests\s+run:\s*\d+,\s*Failures:\s*0"
    r"|TESTS\s+PASSED)",
    re.IGNORECASE,
)

_TB_FAIL_RE = re.compile(
    r"(TEST_\w+:\s*FAIL"
    r"|\d+\s+failed"
    r"|FAILED\s+\("
    r"|Errors:\s*\d+"
    r"|TESTS\s+FAILED)",
    re.IGNORECASE,
)

_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_atif_commands(content: str) -> list[str]:
    """Extract shell keystrokes from an ATIF assistant-turn JSON payload."""
    m = _JSON_OBJ_RE.search(content)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    commands: list[str] = []
    for cmd in data.get("commands", []):
        if isinstance(cmd, dict):
            ks = (cmd.get("keystrokes") or "").strip()
            if ks:
                commands.append(ks)
        elif isinstance(cmd, str) and cmd.strip():
            commands.append(cmd.strip())
    return commands


def _infer_atif_outcome(conversations: list[dict]) -> str:
    """Infer pass/fail from terminal outputs in an ATIF conversation."""
    # Check last assistant turn for is_task_complete flag
    for turn in reversed(conversations):
        if turn.get("role") == "assistant":
            content = turn.get("content", "") or ""
            m = _JSON_OBJ_RE.search(content)
            if m:
                try:
                    data = json.loads(m.group(0))
                    if data.get("is_task_complete"):
                        return "pass"
                except json.JSONDecodeError:
                    pass
            break

    # Scan user turns for test results (keep the last one found)
    last_outcome: str | None = None
    for turn in conversations:
        if turn.get("role") != "user":
            continue
        raw = turn.get("content", "") or ""
        if "New Terminal Output:" in raw:
            output = raw.split("New Terminal Output:", 1)[1]
        else:
            output = raw
        if _TB_PASS_RE.search(output):
            last_outcome = "pass"
        elif _TB_FAIL_RE.search(output):
            last_outcome = "fail"

    return last_outcome if last_outcome is not None else "fail"


def parse_atif_record(raw: dict) -> TrajectoryLog:
    """
    Parse an ATIF-format terminus conversation record into a TrajectoryLog.

    Handles both DCAgent format (analysis/plan/commands with duration) and
    mlfoundations format (state_analysis/explanation/commands with is_blocking).

    Parameters
    ----------
    raw : dict
        One record from a DCAgent or mlfoundations-dev HuggingFace dataset.
        Required: ``conversations`` (list of {role, content} dicts).

    Returns
    -------
    TrajectoryLog with ``source="tb"``
    """
    conversations: list[dict] = raw.get("conversations", [])
    task_id = str(
        raw.get("task") or raw.get("trial_name") or raw.get("run_id") or "unknown"
    )
    model = str(raw.get("model") or "unknown")
    agent = str(raw.get("agent") or "terminus")

    events: list[TrajectoryEvent] = []
    step = 0

    # Skip first turn if it's the user system prompt
    start = 1 if (conversations and conversations[0].get("role") == "user") else 0

    for i in range(start, len(conversations)):
        turn = conversations[i]
        role = turn.get("role", "user")
        content = turn.get("content", "") or ""

        if role == "assistant":
            commands = _extract_atif_commands(content)

            # Peek at the next user turn for terminal output
            next_output = ""
            if i + 1 < len(conversations):
                nxt = conversations[i + 1]
                if nxt.get("role") == "user":
                    nc = nxt.get("content", "") or ""
                    if "New Terminal Output:" in nc:
                        next_output = nc.split("New Terminal Output:", 1)[1].strip()
                    else:
                        next_output = nc.strip()

            # If terminal output shows test results, the LAST non-trivial command
            # in this batch was the test runner (retroactive classification).
            has_test_output = bool(
                next_output and (
                    _TB_PASS_RE.search(next_output) or _TB_FAIL_RE.search(next_output)
                )
            )
            real_cmds = [c for c in commands if c]

            for cmd_idx, cmd in enumerate(real_cmds):
                evt_type = _classify_command(cmd)

                # Override: if this is the last command AND terminal output shows
                # test results, treat it as a test_run (retroactive classification).
                is_last_cmd = (cmd_idx == len(real_cmds) - 1)
                if has_test_output and is_last_cmd and evt_type in ("bash_call", "file_read"):
                    evt_type = "test_run"

                if evt_type == "test_run":
                    events.append(TrajectoryEvent(
                        type="test_run",
                        step=step,
                        args={
                            "command": cmd,
                            "framework": _detect_test_framework(cmd),
                            "outcome": _extract_test_outcome(next_output),
                            "tests_run": _count_tests(next_output),
                        },
                        raw={"keystrokes": cmd},
                    ))
                elif evt_type == "file_read":
                    events.append(TrajectoryEvent(
                        type="file_read",
                        step=step,
                        args={"command": cmd, "path": _extract_file_path(cmd)},
                        raw={"keystrokes": cmd},
                    ))
                elif evt_type == "file_edit":
                    events.append(TrajectoryEvent(
                        type="file_edit",
                        step=step,
                        args={
                            "command": cmd,
                            "path": _extract_file_path(cmd),
                            "operation": "modify",
                        },
                        raw={"keystrokes": cmd},
                    ))
                else:
                    events.append(TrajectoryEvent(
                        type="bash_call",
                        step=step,
                        args={"command": cmd},
                        raw={"keystrokes": cmd},
                    ))
                step += 1

        elif role == "user" and i > start:
            # Extract terminal output and look for error patterns
            raw_content = content
            if "New Terminal Output:" in raw_content:
                output = raw_content.split("New Terminal Output:", 1)[1]
            else:
                output = raw_content
            if _ERROR_RE.search(output):
                events.append(TrajectoryEvent(
                    type="error_reveal",
                    step=step,
                    args={
                        "error_type": _extract_error_class(output),
                        "message": output[:300],
                    },
                    raw={"content": output[:300]},
                ))
                step += 1

    outcome = _infer_atif_outcome(conversations)

    return TrajectoryLog(
        task_id=task_id,
        model=model,
        agent=agent,
        outcome=outcome,
        events=events,
        source="tb",
    )


def _is_atif_record(raw: dict) -> bool:
    """Return True if this record uses ATIF (terminus/DCAgent) conversation format."""
    return "conversations" in raw and isinstance(raw.get("conversations"), list)


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
        description="Acquire Terminal-Bench 2.0 trajectories (inspect-ai or ATIF format)"
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
    atif_count = 0
    inspectai_count = 0

    print(f"Reading from: {args.source}")
    for raw in _iter_source(args.source):
        total_seen += 1
        try:
            if _is_atif_record(raw):
                log = parse_atif_record(raw)
                atif_count += 1
            else:
                log = parse_tb_trajectory(raw)
                inspectai_count += 1
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
        f"\n  ATIF format      : {atif_count}"
        f"\n  Inspect-ai format: {inspectai_count}"
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
