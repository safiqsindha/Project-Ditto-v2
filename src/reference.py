"""
Reference action distribution lookup table for objective scoring (Layer 1).

Maps (trajectory state signature) -> (empirical action distribution from real trajectories).
Used at evaluation time to score whether a model's proposed action matches what real
agents did in the same state.

One ReferenceDistribution is built per data source (tb, swe, human) — see Session 10.

Backoff levels (same as v1):
  Level 0 (full):   all 5 components
  Level 1:          drop field_conditions
  Level 2:          drop field_conditions + turn_bucket
  Level 3 (max):    drop field_conditions + turn_bucket + status_effects

Chains where >=40% of states require level-3 backoff are flagged (v2 targets >=90%
non-max-backoff coverage, tighter than v1's 80% — spec §6).
"""

from __future__ import annotations

import json
import pickle
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Resource bucketing helper
# ---------------------------------------------------------------------------

def _resource_bracket(amount: float) -> int:
    """
    Convert a normalised resource fraction (0.0–1.0) into a discrete bracket.

    Returns
    -------
    0  exhausted (amount == 0)
    1  <25%      (0 < amount < 0.25)
    2  25–50%    (0.25 <= amount < 0.50)
    3  50–75%    (0.50 <= amount < 0.75)
    4  75–100%   (amount >= 0.75)
    """
    if amount <= 0.0:
        return 0
    if amount < 0.25:
        return 1
    if amount < 0.50:
        return 2
    if amount < 0.75:
        return 3
    return 4


# ---------------------------------------------------------------------------
# StateSignature
# ---------------------------------------------------------------------------

@dataclass
class StateSignature:
    """
    Compact, hashable descriptor of a trajectory state.

    Fields
    ------
    active_pair       : (current_task_phase, last_command_class) — both abstracted
    hp_brackets       : (context_remaining_bracket, patience_bracket) — bucketed 0–4
    status_effects    : frozenset of active status flags, e.g. "file_A_modified"
    field_conditions  : frozenset of active coordination/optimization strings
    turn_bucket       : step index // 10
    """
    active_pair: tuple[str, str]
    hp_brackets: tuple[int, int]
    status_effects: frozenset
    field_conditions: frozenset
    turn_bucket: int

    def to_key(self, level: int = 0) -> tuple:
        """
        Return a hashable key at the requested backoff level.

        Level 0 (full):  all 5 components
        Level 1:         drop field_conditions
        Level 2:         drop field_conditions + turn_bucket
        Level 3 (max):   drop field_conditions + turn_bucket + status_effects
        """
        if level == 0:
            return (
                self.active_pair,
                self.hp_brackets,
                self.status_effects,
                self.field_conditions,
                self.turn_bucket,
            )
        if level == 1:
            return (
                self.active_pair,
                self.hp_brackets,
                self.status_effects,
                self.turn_bucket,
            )
        if level == 2:
            return (
                self.active_pair,
                self.hp_brackets,
                self.status_effects,
            )
        # level 3 — maximum backoff
        return (
            self.active_pair,
            self.hp_brackets,
        )


# ---------------------------------------------------------------------------
# extract_state_signature  (from chain dict format)
# ---------------------------------------------------------------------------

def extract_state_signature(chain: dict, step_idx: int) -> StateSignature | None:
    """
    Extract a StateSignature from a chain dict at the given step index.

    Chain dict format (chains/real/<source>/*.jsonl):
    {
      "chain_id": "tb_00000",
      "source": "tb",
      "constraints": [
        {"type": "ResourceBudget", "timestamp": 1, "resource": "context_window", "amount": 0.95, ...},
        {"type": "SubGoalTransition", "timestamp": 1, "from_phase": "initial", "to_phase": "exploration", ...},
        ...
      ],
    }

    Extraction rules
    ----------------
    active_pair      : (most recent SubGoalTransition.to_phase, most recent ToolAvailability.tool)
    hp_brackets      : (context_window bracket, patience_budget bracket)
    status_effects   : frozenset of active file/error labels that have been revealed
    field_conditions : all CoordinationDependency and OptimizationCriterion active before K
    turn_bucket      : constraints[step_idx].timestamp // 10
    """
    constraints = chain.get("constraints", [])
    if step_idx >= len(constraints) or step_idx < 0:
        return None
    if not constraints:
        return None

    step_constraint = constraints[step_idx]
    timestamp = step_constraint.get("timestamp", 0)
    turn_bucket = timestamp // 10

    prior = constraints[: step_idx + 1]

    # -----------------------------------------------------------------------
    # active_pair: (current_phase, last_command_label)
    # -----------------------------------------------------------------------
    current_phase = "initial"
    last_command = "command_unknown"

    for c in reversed(prior):
        if c.get("type") == "SubGoalTransition" and current_phase == "initial":
            current_phase = c.get("to_phase", "initial")
        if c.get("type") == "ToolAvailability" and last_command == "command_unknown":
            tool = c.get("tool", "")
            if tool.startswith("command_"):
                last_command = tool
        if current_phase != "initial" and last_command != "command_unknown":
            break

    active_pair = (current_phase, last_command)

    # -----------------------------------------------------------------------
    # hp_brackets: (context_window bracket, patience_budget bracket)
    # -----------------------------------------------------------------------
    context_amount = 1.0
    patience_amount = 1.0

    for c in reversed(prior):
        if c.get("type") != "ResourceBudget":
            continue
        resource = c.get("resource", "")
        if resource == "context_window" and context_amount == 1.0:
            context_amount = c.get("amount", 1.0)
        if resource == "patience_budget" and patience_amount == 1.0:
            patience_amount = c.get("amount", 1.0)

    hp_brackets = (_resource_bracket(context_amount), _resource_bracket(patience_amount))

    # -----------------------------------------------------------------------
    # status_effects: revealed file/error entities
    # -----------------------------------------------------------------------
    revealed: set[str] = set()
    for c in prior:
        if c.get("type") == "InformationState":
            for entity in c.get("observable_added", []):
                revealed.add(entity)

    status_effects: frozenset = frozenset(f"{e}_revealed" for e in revealed)

    # -----------------------------------------------------------------------
    # field_conditions: CoordinationDependency + OptimizationCriterion
    # -----------------------------------------------------------------------
    field_set: set[str] = set()
    seen_objectives: dict[str, str] = {}
    for c in prior:
        ctype = c.get("type", "")
        if ctype == "OptimizationCriterion":
            obj = c.get("objective", "")
            if obj:
                seen_objectives[obj.split("_")[0]] = obj
        elif ctype == "CoordinationDependency":
            dep = c.get("dependency", "")
            role = c.get("role", "")
            if dep:
                field_set.add(f"{dep}_{role}")
    field_set.update(seen_objectives.values())
    field_conditions = frozenset(field_set)

    return StateSignature(
        active_pair=active_pair,
        hp_brackets=hp_brackets,
        status_effects=status_effects,
        field_conditions=field_conditions,
        turn_bucket=turn_bucket,
    )


# ---------------------------------------------------------------------------
# ReferenceDistribution  (copied from v1 with docstring update)
# ---------------------------------------------------------------------------

class ReferenceDistribution:
    """
    Lookup table mapping state signature keys to action count dicts.

    One instance is built per data source (tb, swe, human).  The v2 target
    is ≥90% non-max-backoff coverage at evaluation time (tighter than v1's 80%).
    """

    _MAX_BACKOFF_FRACTION = 0.40

    def __init__(self) -> None:
        self._counts: list[dict[tuple, dict[str, int]]] = [
            defaultdict(lambda: defaultdict(int)) for _ in range(4)
        ]

    def build_from_chains(self, chain_files: list[Path]) -> None:
        """Populate the distribution from a list of chain JSONL files."""
        for path in chain_files:
            self._ingest_chain_file(path)

    def _ingest_chain_file(self, path: Path) -> None:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    chain = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                self._ingest_chain(chain)

    def _ingest_chain(self, chain: dict) -> None:
        constraints = chain.get("constraints", [])
        if not constraints:
            return

        per_step_actions = chain.get("per_step_actions")
        pairs: list[tuple[StateSignature, str]] = []

        if per_step_actions:
            for entry in per_step_actions:
                step_idx = entry.get("step_idx", 0)
                action = entry.get("action", "")
                if action:
                    sig = extract_state_signature(chain, step_idx)
                    if sig is not None:
                        pairs.append((sig, action))
        else:
            action = chain.get("action_at_step", "")
            if action:
                step_idx = chain.get("cutoff_k", len(constraints) - 1)
                sig = extract_state_signature(chain, step_idx)
                if sig is not None:
                    pairs.append((sig, action))

        for sig, action in pairs:
            for level in range(4):
                key = sig.to_key(level)
                self._counts[level][key][action] += 1

    def add_observation(self, sig: StateSignature, action: str) -> None:
        for level in range(4):
            key = sig.to_key(level)
            self._counts[level][key][action] += 1

    def lookup(
        self,
        sig: StateSignature,
        k: int = 3,
    ) -> tuple[list[str], dict[str, float], int]:
        """Return top-k actions and probabilities; tries backoff levels 0→3."""
        for level in range(4):
            key = sig.to_key(level)
            counts = self._counts[level].get(key)
            if counts:
                total = sum(counts.values())
                dist = {a: c / total for a, c in counts.items()}
                top_k = sorted(dist, key=dist.__getitem__, reverse=True)[:k]
                return top_k, dist, level
        return [], {}, 3

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"counts": [dict(level) for level in self._counts]}
        with open(path, "wb") as fh:
            pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path: Path) -> "ReferenceDistribution":
        with open(path, "rb") as fh:
            payload = pickle.load(fh)
        obj = cls()
        raw_counts = payload.get("counts", [{}, {}, {}, {}])
        for level, level_data in enumerate(raw_counts):
            d: dict[tuple, dict[str, int]] = defaultdict(lambda: defaultdict(int))
            for k, v in level_data.items():
                d[k] = defaultdict(int, v)
            obj._counts[level] = d
        return obj

    def stats(self) -> dict[str, Any]:
        return {
            f"level_{i}_keys": len(self._counts[i]) for i in range(4)
        } | {
            f"level_{i}_total_obs": sum(
                sum(v.values()) for v in self._counts[i].values()
            )
            for i in range(4)
        }


# ---------------------------------------------------------------------------
# CLI  (adapted from v1 — adds --source flag and 90% coverage target)
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m src.reference",
        description="Reference action distribution builder and checker.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build_p = sub.add_parser("build-raw", help="Build distribution from chain files.")
    build_p.add_argument("--source", choices=["tb", "swe", "human"], required=True)
    build_p.add_argument("--raw", type=Path, required=True)
    build_p.add_argument("--out", type=Path, required=True)

    check_p = sub.add_parser("check", help="Check distribution coverage.")
    check_p.add_argument("--dist", type=Path, required=True)
    check_p.add_argument("--chains", type=Path, required=True)
    check_p.add_argument("--target", type=float, default=0.9)

    ns = parser.parse_args()

    if ns.command == "build-raw":
        chain_files = sorted(Path(ns.raw).glob("*.jsonl"))
        print(f"[reference] Building {ns.source} distribution from {len(chain_files)} files…")
        dist = ReferenceDistribution()
        dist.build_from_chains(chain_files)
        s = dist.stats()
        print(f"[reference] Level-0 keys: {s['level_0_keys']}")
        dist.save(ns.out)
        print(f"[reference] Saved to {ns.out}")

    elif ns.command == "check":
        dist = ReferenceDistribution.load(ns.dist)
        chain_files = sorted(Path(ns.chains).glob("*.jsonl"))
        samples: list[tuple[dict, int]] = []
        for path in chain_files:
            with open(path, encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        chain = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    n = len(chain.get("constraints", []))
                    for step_idx in range(n):
                        samples.append((chain, step_idx))

        chosen = random.sample(samples, min(50, len(samples)))
        non_max = sum(
            1 for chain, step_idx in chosen
            if (sig := extract_state_signature(chain, step_idx)) is not None
            and dist.lookup(sig)[2] < 3
        )
        fraction = non_max / len(chosen) if chosen else 0.0
        print(
            f"[reference] {non_max}/{len(chosen)} non-max-backoff "
            f"({fraction:.1%}) — target ≥{ns.target:.0%}"
        )
        print("[reference] PASS" if fraction >= ns.target else "[reference] WARN: below target")


if __name__ == "__main__":
    main()
