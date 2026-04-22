"""
Terminal-Bench trajectory parser (Session 2).

Parses raw Terminal-Bench 2.0 trajectory format (Harbor framework JSON) into
canonical TrajectoryLog / TrajectoryEvent objects for downstream T-code translation.

Primary function: parse_tb_trajectory(raw: dict) -> TrajectoryLog

Event types produced:
  bash_call      — a bash/terminal command executed by the agent
  file_read      — the agent read a file
  file_edit      — the agent created, modified, or deleted a file
  test_run       — the agent ran a test suite (outcome: pass | fail)
  error_reveal   — an error message or stack trace appeared in command output
  context_update — context window token count changed
  task_transition — the agent moved to a new sub-task or phase

Implemented in Session 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TrajectoryEvent:
    """
    A single event in a parsed trajectory.

    Analogous to v1's BattleEvent.  Used by T-code and aggregation modules.
    """
    type: str               # one of the event types listed in the module docstring
    step: int               # 0-indexed step within the trajectory
    args: dict[str, Any]    # event-type-specific payload
    raw: dict               # original raw dict (for inspection/debugging)


@dataclass
class TrajectoryLog:
    """
    A parsed trajectory ready for T-code translation.

    Analogous to v1's BattleLog.
    """
    task_id: str
    model: str
    agent: str
    outcome: str                          # "pass" | "fail"
    events: list[TrajectoryEvent] = field(default_factory=list)
    source: str = "tb"


def parse_tb_trajectory(raw: dict) -> TrajectoryLog:
    """
    Parse a raw Terminal-Bench trajectory dict into a TrajectoryLog.

    Parameters
    ----------
    raw : dict with keys: task_id, model, agent, outcome, trajectory (list of events)

    Returns
    -------
    TrajectoryLog with typed TrajectoryEvent objects

    Raises
    ------
    ValueError if the raw dict is missing required fields.
    """
    raise NotImplementedError("parse_tb_trajectory not yet implemented (Session 2)")


def filter_trajectory(log: TrajectoryLog, min_events: int = 15) -> bool:
    """Return True if the trajectory meets inclusion criteria.

    Criteria (spec §3.4):
    - At least min_events events
    - Not an early-terminated run (outcome must be "pass" or "fail", not "timeout")
    """
    if len(log.events) < min_events:
        return False
    if log.outcome not in ("pass", "fail"):
        return False
    return True
