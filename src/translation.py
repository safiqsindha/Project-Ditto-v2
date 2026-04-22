"""
Translation function T-code: converts parsed trajectory events into abstract Constraint objects.

This module owns the six constraint dataclasses (identical to v1's T-battle types) plus
the full trajectory translation logic.  The dataclasses are defined here first so that
filter.py, shuffler.py, and other pipeline modules can import them without depending on
any domain-specific translation logic.

T-code is implemented in Session 6.  Until then this module exports only the constraint
dataclasses and the Constraint union type.

Frozen at git tag T-code-v1.0-frozen after Session 8 validation.  No modifications after
that tag without a new pre-registration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Constraint dataclasses  (identical to v1's T-battle types — spec §3.1)
# ---------------------------------------------------------------------------

@dataclass
class ResourceBudget:
    """Continuous or depleting pool: context window, patience budget, time."""
    timestamp: int          # step / event index within trajectory
    resource: str           # e.g. "context_window", "patience_budget", "hp_unit_A"
    amount: float           # normalised 0.0–1.0
    decay: str              # "none" | "monotone_decrease" | "monotone_decrease_if_turn_based"
    recover_in: int | None  # expected steps until replenished, or None


@dataclass
class ToolAvailability:
    """Discrete on/off: command available/unavailable, file created/deleted."""
    timestamp: int
    tool: str               # e.g. "command_1", "file_A"
    state: str              # "available" | "unavailable"
    recover_in: int | None  # None ↔ permanent


@dataclass
class SubGoalTransition:
    """Regime change in the agent's task plan."""
    timestamp: int
    from_phase: str         # e.g. "exploration", "implementation"
    to_phase: str           # e.g. "validation", "debugging"
    trigger: str            # e.g. "test_pass", "test_fail", "task_transition"


@dataclass
class InformationState:
    """Partial observability events — what the agent can now see."""
    timestamp: int
    observable_added: list[str]    # e.g. ["file_A", "error_class_B"]
    observable_removed: list[str]
    uncertainty: float             # 0.0 = fully known, 1.0 = fully unknown


@dataclass
class CoordinationDependency:
    """Module or dependency relationships that constrain the agent's actions."""
    timestamp: int
    role: str               # e.g. "affected_module_M1"
    dependency: str         # e.g. "blocker_type_B"
    expected_action: str    # abstract action hint


@dataclass
class OptimizationCriterion:
    """Objective shifts: correctness → performance, or test-suite state changes."""
    timestamp: int
    objective: str          # e.g. "correctness_primary", "performance_primary"
    weight_shift: str       # descriptor of the shift


# Union type for all constraints
Constraint = (
    ResourceBudget
    | ToolAvailability
    | SubGoalTransition
    | InformationState
    | CoordinationDependency
    | OptimizationCriterion
)

# Abstract label pools (spec §3.2)
_MAX_FILES = 26
_FILE_LABELS = [f"file_{chr(ord('A') + i)}" for i in range(_MAX_FILES)]      # file_A … file_Z

_MAX_COMMANDS = 26
_COMMAND_LABELS = [f"command_{i + 1}" for i in range(_MAX_COMMANDS)]          # command_1 … command_26

_MAX_ERRORS = 26
_ERROR_LABELS = [f"error_class_{chr(ord('A') + i)}" for i in range(_MAX_ERRORS)]  # error_class_A … error_class_Z

# Sub-task phase vocabulary (fixed — spec §3.1)
PHASE_VOCABULARY = frozenset({
    "exploration",
    "hypothesis",
    "implementation",
    "validation",
    "debugging",
    "forced_switch_required",
    "initial",
})


# ---------------------------------------------------------------------------
# Translation context  (Session 6 will fill in the translation logic)
# ---------------------------------------------------------------------------

@dataclass
class TranslationContext:
    """
    Mutable state accumulated across events within a single trajectory.

    All mappings use abstract labels only; domain-specific names are hashed
    on first encounter and never stored after the mapping is established.
    """
    source: str = "tb"  # "tb" | "swe" | "human"

    # file path → abstract file label (file_A … file_Z / file_OVERFLOW_N)
    _file_map: dict[str, str] = field(default_factory=dict)
    # command string → abstract command label (command_1 … command_N)
    _command_map: dict[str, str] = field(default_factory=dict)
    # error type string → abstract error label (error_class_A … error_class_Z)
    _error_map: dict[str, str] = field(default_factory=dict)

    # current sub-task phase
    phase: str = "initial"

    # resource counters
    context_tokens_used: int = 0
    context_tokens_max: int = 200_000
    retry_count: int = 0

    def _get_file_label(self, path: str) -> str:
        """Return the abstract label for a file path, assigning one if new."""
        if path not in self._file_map:
            idx = len(self._file_map)
            if idx < _MAX_FILES:
                label = _FILE_LABELS[idx]
            else:
                label = f"file_OVERFLOW_{idx - _MAX_FILES + 1}"
                import logging
                logging.warning(
                    "T-code: trajectory uses >26 distinct files; "
                    f"assigning overflow label {label} to {path!r}"
                )
            self._file_map[path] = label
        return self._file_map[path]

    def _get_command_label(self, command: str) -> str:
        """Return the abstract label for a command string, assigning one if new."""
        if command not in self._command_map:
            idx = len(self._command_map)
            label = _COMMAND_LABELS[min(idx, _MAX_COMMANDS - 1)]
            self._command_map[command] = label
        return self._command_map[command]

    def _get_error_label(self, error_type: str) -> str:
        """Return the abstract label for an error type, assigning one if new."""
        if error_type not in self._error_map:
            idx = len(self._error_map)
            label = _ERROR_LABELS[min(idx, _MAX_ERRORS - 1)]
            self._error_map[error_type] = label
        return self._error_map[error_type]


# ---------------------------------------------------------------------------
# Translation functions  (stubs — implemented in Session 6)
# ---------------------------------------------------------------------------

def translate_event(event: Any, ctx: TranslationContext) -> list[Constraint]:
    """Translate a single TrajectoryEvent into zero or more Constraint objects.

    Implemented in Session 6.
    """
    raise NotImplementedError("T-code translate_event not yet implemented (Session 6)")


def translate_trajectory(events: list[Any], source: str) -> list[Constraint]:
    """Translate a full sequence of TrajectoryEvents from a given source.

    Parameters
    ----------
    events : list of TrajectoryEvent objects from the appropriate parser
    source : "tb" | "swe" | "human"

    Returns
    -------
    Ordered list of Constraint objects.
    """
    raise NotImplementedError("T-code translate_trajectory not yet implemented (Session 6)")
