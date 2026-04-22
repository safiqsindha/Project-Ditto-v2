"""
Translation function T-code: converts parsed trajectory events into abstract Constraint objects.

This module owns the six constraint dataclasses (identical to v1's T-battle types) plus
the full trajectory translation logic.  The dataclasses are defined here first so that
filter.py, shuffler.py, and other pipeline modules can import them without depending on
any domain-specific translation logic.

T-code design
-------------
Each TrajectoryEvent type maps to one or more Constraint objects:

  bash_call       → ResourceBudget(context_window)
  file_read       → InformationState(observable_added=[file_label])
  file_edit       → SubGoalTransition (first edit) OR ToolAvailability(available)
  test_run pass   → SubGoalTransition(→ validation) + OptimizationCriterion
  test_run fail   → SubGoalTransition(→ debugging) + ResourceBudget(patience_budget)
                    + ToolAvailability(test_suite, unavailable, recover_in=3)
  error_reveal    → InformationState OR CoordinationDependency (alternating)
  context_update  → ResourceBudget(context_window) + ToolAvailability(unavailable)
                    if context > 80%
  task_transition → SubGoalTransition

Guaranteed filter invariants (spec §3.4):
  ≥ 10 ResourceBudget  — one per bash_call + each context_update + test_run fail
  ≥ 2  SubGoalTransition — first file_edit + first test_run outcome change
  ≥ 1  ToolAvailability(unavailable) — test_run fail emits test_suite unavailable

Frozen at git tag T-code-v1.0-frozen after Session 8 validation.  No modifications
after that tag without a new pre-registration.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from typing import Any

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constraint dataclasses  (identical to v1's T-battle types — spec §3.1)
# ---------------------------------------------------------------------------

@dataclass
class ResourceBudget:
    """Continuous or depleting pool: context window, patience budget."""
    timestamp: int
    resource: str           # "context_window" | "patience_budget"
    amount: float           # normalised 0.0–1.0
    decay: str              # "none" | "monotone_decrease" | "monotone_decrease_if_turn_based"
    recover_in: int | None  # expected steps until replenished, or None


@dataclass
class ToolAvailability:
    """Discrete on/off: command or file available/unavailable."""
    timestamp: int
    tool: str               # e.g. "command_1", "file_A", "test_suite", "context_window"
    state: str              # "available" | "unavailable"
    recover_in: int | None  # None ↔ permanent or unknown


@dataclass
class SubGoalTransition:
    """Regime change in the agent's task plan."""
    timestamp: int
    from_phase: str
    to_phase: str
    trigger: str


@dataclass
class InformationState:
    """Partial observability events — what the agent can now see."""
    timestamp: int
    observable_added: list[str]
    observable_removed: list[str]
    uncertainty: float             # 0.0 = fully known, 1.0 = fully unknown


@dataclass
class CoordinationDependency:
    """Module or dependency relationships that constrain the agent's actions."""
    timestamp: int
    role: str
    dependency: str
    expected_action: str


@dataclass
class OptimizationCriterion:
    """Objective shifts: correctness → performance, or test-suite state changes."""
    timestamp: int
    objective: str
    weight_shift: str


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
_MAX_FILES    = 26
_MAX_COMMANDS = 26
_MAX_ERRORS   = 26

_FILE_LABELS    = [f"file_{chr(ord('A') + i)}"        for i in range(_MAX_FILES)]
_COMMAND_LABELS = [f"command_{i + 1}"                 for i in range(_MAX_COMMANDS)]
_ERROR_LABELS   = [f"error_class_{chr(ord('A') + i)}" for i in range(_MAX_ERRORS)]

PHASE_VOCABULARY = frozenset({
    "exploration", "hypothesis", "implementation",
    "validation", "debugging", "initial",
})


# ---------------------------------------------------------------------------
# Translation context
# ---------------------------------------------------------------------------

@dataclass
class TranslationContext:
    """
    Mutable state accumulated across events within a single trajectory.

    All mappings use abstract labels only; domain-specific names are mapped
    on first encounter and never stored after the label is assigned.
    """
    source: str = "tb"

    # Abstract label maps (domain names → abstract labels)
    _file_map:    dict[str, str] = field(default_factory=dict)
    _command_map: dict[str, str] = field(default_factory=dict)
    _error_map:   dict[str, str] = field(default_factory=dict)

    # Current sub-task phase
    phase: str = "exploration"

    # Resource tracking
    context_tokens_used: int = 0
    context_tokens_max:  int = 200_000
    patience_budget:   float = 1.0
    uncertainty:       float = 0.5

    # Internal flags
    _context_unavailable_emitted: bool = False
    _error_count: int = 0
    _first_edit_done: bool = False
    _last_command_label: str = "command_1"

    def get_file_label(self, path: str) -> str:
        if not path:
            path = f"_unknown_{len(self._file_map)}"
        if path not in self._file_map:
            idx = len(self._file_map)
            if idx < _MAX_FILES:
                label = _FILE_LABELS[idx]
            else:
                label = f"file_OVERFLOW_{idx - _MAX_FILES + 1}"
                _log.warning("T-code: >26 distinct files; assigning %s to %r", label, path)
            self._file_map[path] = label
        return self._file_map[path]

    def get_command_label(self, command: str) -> str:
        stem = command.strip().split()[0] if command.strip() else "unknown"
        if stem not in self._command_map:
            idx = len(self._command_map)
            self._command_map[stem] = _COMMAND_LABELS[min(idx, _MAX_COMMANDS - 1)]
        label = self._command_map[stem]
        self._last_command_label = label
        return label

    def get_error_label(self, error_type: str) -> str:
        if not error_type:
            error_type = "RuntimeError"
        if error_type not in self._error_map:
            idx = len(self._error_map)
            self._error_map[error_type] = _ERROR_LABELS[min(idx, _MAX_ERRORS - 1)]
        return self._error_map[error_type]

    # Legacy aliases (kept for backwards compatibility with any existing callers)
    def _get_file_label(self, path: str) -> str:
        return self.get_file_label(path)

    def _get_command_label(self, command: str) -> str:
        return self.get_command_label(command)

    def _get_error_label(self, error_type: str) -> str:
        return self.get_error_label(error_type)

    def context_fraction_remaining(self) -> float:
        if self.context_tokens_max <= 0:
            return 0.0
        return max(0.0, 1.0 - self.context_tokens_used / self.context_tokens_max)

    def increment_context(self, tokens: int = 150) -> None:
        self.context_tokens_used = min(
            self.context_tokens_used + tokens, self.context_tokens_max
        )


# ---------------------------------------------------------------------------
# Per-event translators
# ---------------------------------------------------------------------------

def _translate_bash_call(event: Any, ctx: TranslationContext) -> list[Constraint]:
    cmd = event.args.get("command", "")
    ctx.get_command_label(cmd)
    ctx.increment_context(tokens=150)

    amount = round(ctx.context_fraction_remaining(), 3)
    result: list[Constraint] = [ResourceBudget(
        timestamp=event.step,
        resource="context_window",
        amount=amount,
        decay="monotone_decrease",
        recover_in=None,
    )]

    if amount < 0.2 and not ctx._context_unavailable_emitted:
        result.append(ToolAvailability(
            timestamp=event.step,
            tool="context_window",
            state="unavailable",
            recover_in=None,
        ))
        ctx._context_unavailable_emitted = True

    return result


def _translate_file_read(event: Any, ctx: TranslationContext) -> list[Constraint]:
    path = event.args.get("path", "")
    file_label = ctx.get_file_label(path)
    ctx.uncertainty = max(0.0, ctx.uncertainty - 0.04)

    return [InformationState(
        timestamp=event.step,
        observable_added=[file_label],
        observable_removed=[],
        uncertainty=round(ctx.uncertainty, 3),
    )]


def _translate_file_edit(event: Any, ctx: TranslationContext) -> list[Constraint]:
    path = event.args.get("path", "")
    file_label = ctx.get_file_label(path)

    if not ctx._first_edit_done or ctx.phase not in ("implementation", "debugging"):
        old_phase = ctx.phase
        ctx.phase = "implementation"
        ctx._first_edit_done = True
        return [SubGoalTransition(
            timestamp=event.step,
            from_phase=old_phase,
            to_phase="implementation",
            trigger="first_edit",
        )]
    else:
        return [ToolAvailability(
            timestamp=event.step,
            tool=file_label,
            state="available",
            recover_in=None,
        )]


def _translate_test_run(event: Any, ctx: TranslationContext) -> list[Constraint]:
    outcome = event.args.get("outcome") or "fail"
    result: list[Constraint] = []

    if outcome == "pass":
        if ctx.phase != "validation":
            old_phase = ctx.phase
            ctx.phase = "validation"
            result.append(SubGoalTransition(
                timestamp=event.step,
                from_phase=old_phase,
                to_phase="validation",
                trigger="test_pass",
            ))
        result.append(OptimizationCriterion(
            timestamp=event.step,
            objective="correctness_primary",
            weight_shift="correctness_increase",
        ))
    else:
        if ctx.phase != "debugging":
            old_phase = ctx.phase
            ctx.phase = "debugging"
            result.append(SubGoalTransition(
                timestamp=event.step,
                from_phase=old_phase,
                to_phase="debugging",
                trigger="test_fail",
            ))
        ctx.patience_budget = max(0.0, ctx.patience_budget - 0.15)
        result.append(ResourceBudget(
            timestamp=event.step,
            resource="patience_budget",
            amount=round(ctx.patience_budget, 3),
            decay="monotone_decrease_if_turn_based",
            recover_in=None,
        ))
        result.append(ToolAvailability(
            timestamp=event.step,
            tool="test_suite",
            state="unavailable",
            recover_in=3,
        ))

    return result


def _translate_error_reveal(event: Any, ctx: TranslationContext) -> list[Constraint]:
    error_type = event.args.get("error_type", "RuntimeError")
    error_label = ctx.get_error_label(error_type)
    ctx.uncertainty = min(1.0, ctx.uncertainty + 0.08)

    if ctx._error_count % 2 == 0:
        result: Constraint = InformationState(
            timestamp=event.step,
            observable_added=[error_label],
            observable_removed=[],
            uncertainty=round(ctx.uncertainty, 3),
        )
    else:
        result = CoordinationDependency(
            timestamp=event.step,
            role="affected_module_M1",
            dependency=error_label,
            expected_action=f"resolve_{error_label}",
        )
    ctx._error_count += 1
    return [result]


def _translate_context_update(event: Any, ctx: TranslationContext) -> list[Constraint]:
    tokens_used = int(event.args.get("tokens_used", 0) or 0)
    tokens_max  = int(event.args.get("tokens_max", 200_000) or 200_000)
    ctx.context_tokens_used = tokens_used
    ctx.context_tokens_max  = max(1, tokens_max)

    amount = round(ctx.context_fraction_remaining(), 3)
    result: list[Constraint] = [ResourceBudget(
        timestamp=event.step,
        resource="context_window",
        amount=amount,
        decay="monotone_decrease",
        recover_in=None,
    )]

    if amount < 0.2 and not ctx._context_unavailable_emitted:
        result.append(ToolAvailability(
            timestamp=event.step,
            tool="context_window",
            state="unavailable",
            recover_in=None,
        ))
        ctx._context_unavailable_emitted = True

    return result


def _translate_task_transition(event: Any, ctx: TranslationContext) -> list[Constraint]:
    from_phase = event.args.get("from_phase", ctx.phase)
    to_phase   = event.args.get("to_phase", "exploration")
    trigger    = (event.args.get("reason") or event.args.get("trigger") or "task_transition")

    if from_phase not in PHASE_VOCABULARY:
        from_phase = ctx.phase
    if to_phase not in PHASE_VOCABULARY:
        to_phase = "exploration"
    if from_phase == to_phase:
        to_phase = "hypothesis" if ctx.phase == "exploration" else "exploration"
        from_phase = ctx.phase

    ctx.phase = to_phase
    return [SubGoalTransition(
        timestamp=event.step,
        from_phase=from_phase,
        to_phase=to_phase,
        trigger=str(trigger)[:50],
    )]


_TRANSLATORS = {
    "bash_call":       _translate_bash_call,
    "file_read":       _translate_file_read,
    "file_edit":       _translate_file_edit,
    "test_run":        _translate_test_run,
    "error_reveal":    _translate_error_reveal,
    "context_update":  _translate_context_update,
    "task_transition": _translate_task_transition,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def translate_event(event: Any, ctx: TranslationContext) -> list[Constraint]:
    """
    Translate a single TrajectoryEvent into zero or more Constraint objects.

    Updates ctx in place to track phase, resource levels, and label assignments.

    Parameters
    ----------
    event : TrajectoryEvent (or any object with .type, .step, .args)
    ctx   : TranslationContext — mutable state

    Returns
    -------
    List of Constraint dataclass instances (empty for unrecognised event types).
    """
    translator = _TRANSLATORS.get(event.type)
    if translator is None:
        return []
    return translator(event, ctx)


def translate_trajectory(
    events: list[Any],
    source: str,
) -> tuple[list[Constraint], list[tuple[str, str]]]:
    """
    Translate a full sequence of TrajectoryEvents into a constraint chain.

    Parameters
    ----------
    events : list of TrajectoryEvent objects (after aggregation)
    source : "tb" | "swe" | "human"

    Returns
    -------
    (constraints, active_pair_by_step) where:
      constraints         — ordered list of Constraint dataclass instances
      active_pair_by_step — list of (phase, last_command_label) tuples,
                            one entry per constraint
    """
    ctx = TranslationContext(source=source)
    constraints: list[Constraint] = []
    active_pairs: list[tuple[str, str]] = []

    for event in events:
        for c in translate_event(event, ctx):
            constraints.append(c)
            active_pairs.append((ctx.phase, ctx._last_command_label))

    return constraints, active_pairs


def constraint_to_dict(c: Constraint) -> dict:
    """Serialise a Constraint dataclass instance to a JSON-compatible dict."""
    d = dataclasses.asdict(c)
    d["type"] = type(c).__name__
    return d


def constraint_from_dict(d: dict) -> Constraint:
    """Deserialise a constraint dict (from JSONL) back to a dataclass instance."""
    _TYPE_MAP: dict[str, type] = {
        "ResourceBudget":         ResourceBudget,
        "ToolAvailability":       ToolAvailability,
        "SubGoalTransition":      SubGoalTransition,
        "InformationState":       InformationState,
        "CoordinationDependency": CoordinationDependency,
        "OptimizationCriterion":  OptimizationCriterion,
    }
    d = dict(d)
    type_name = d.pop("type")
    cls = _TYPE_MAP[type_name]
    return cls(**d)
