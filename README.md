# Project Ditto v2

A replication-and-generality test for the **Ditto constraint-chain abstraction**, applied to programming-task agent trajectories from Terminal-Bench 2.0, SWE-bench Verified, and human debugging sessions.

Builds on [Project Ditto v1](https://github.com/safiqsindha/Project-Ditto) (Pokémon telemetry). The experiment tests whether the same real-vs-shuffled detectability effect reproduces on programming telemetry using the same six constraint types.

**Pre-registration:** `SPEC.md` + `SPEC.pdf` — thresholds and methodology are frozen before evaluation.

---

## What It Does

Agent trajectories (shell commands, file edits, test runs) are translated into abstract **constraint chains** via T-code — six constraint types that capture resource budgets, tool availability, sub-goal transitions, information state, coordination dependencies, and optimization criteria. Chains are rendered in domain-blind abstract English (no programming vocabulary), then real chains are compared against shuffled controls. Claude Haiku and Sonnet are asked to predict the next constraint at a mid-chain cutoff; higher accuracy on real vs shuffled chains is the effect of interest.

---

## Status

| Source | Trajectories | Real Chains | Gate 3 | Gate 4 |
|--------|-------------|-------------|--------|--------|
| Terminal-Bench 2.0 + extras | 4,258 | **170** | PASS | PASS (100%) |
| SWE-bench Verified | 5,000 | **1,016** | PASS | PASS (100%) |
| Human sessions (SpecStory) | in progress | pending | pending | pending |

All gates except human: **green**. Gate 5 (live API dry-run): **PASS**.

---

## Pipeline

```
data/<source>/trajectories.jsonl
  → scripts/acquire_<source>.py       # HuggingFace / GitHub acquisition
  → src/parser_<source>.py            # → TrajectoryLog
  → src/aggregation.py                # event compression
  → src/translation.py                # T-code: events → Constraints  [FROZEN]
  → src/observability.py              # asymmetric information reveal
  → src/filter.py                     # is_valid_chain()
  → src/renderer.py                   # abstract English (leakage check)
  → src/shuffler.py                   # seeded shuffled control variants
chains/real/<source>/*.jsonl
chains/shuffled/<source>/*.jsonl
  → src/reference.py                  # StateSignature → action distribution
data/reference_<source>.pkl
  → src/runner.py / scripts/run_evaluation.py   # Batches API evaluation
results/raw/ + results/blinded/
  → src/scorer.py                     # Layer 1/2/3 scoring (Session 13)
results/scored.json
```

**T-code is frozen** at tag `T-code-v1.0-frozen`. `src/translation.py`, `src/aggregation.py`, and `src/renderer.py` must not change after this tag.

---

## Evaluation Models

| Model | ID |
|-------|----|
| Claude Haiku 4.5 | `claude-haiku-4-5-20251001` |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` |

Seeds: 42 (T=0.0), 1337 and 7919 (T=0.5). Evaluation via Anthropic Messages Batches API (50% cost reduction).

---

## Quick Start

```bash
pip install -r requirements.txt

# Build chains (after data acquisition)
python scripts/build_chains.py --source swe --data data/swe_bench_verified/ \
  --out-real chains/real/swe/ --out-shuffled chains/shuffled/swe/ --gate3

# Build reference distributions
python -m src.reference build-raw --source swe --raw chains/real/swe/ --out data/reference_swe.pkl
python -m src.reference check --dist data/reference_swe.pkl --chains chains/real/swe/ --target 0.9

# Dry-run evaluation (5 chains)
python -m src.runner --model haiku --source swe --chains chains/real/swe/ --seed 42 --dry-run --n 5

# Full evaluation (Session 12)
python scripts/run_evaluation.py

# Run tests
pytest tests/
```

---

## Key Files

| File | Purpose |
|------|---------|
| `SPEC.md` | Pre-registered methodology and thresholds (frozen) |
| `SPEC.pdf` | Immutable PDF of pre-registration |
| `CLAUDE.md` | Architecture, session protocol, invariants |
| `SESSION_LOG.md` | Per-session progress log |
| `BUILD_PLAN.md` | Session-by-session plan |
| `src/translation.py` | T-code (frozen at `T-code-v1.0-frozen`) |
| `scripts/run_evaluation.py` | Full evaluation entry point (Session 12) |

---

## Constraint Types (identical to v1)

`ResourceBudget` · `ToolAvailability` · `SubGoalTransition` · `InformationState` · `CoordinationDependency` · `OptimizationCriterion`

---

*Pre-registration v1.1 — 2026-04-22. See [Project Ditto v1](https://github.com/safiqsindha/Project-Ditto) for the original Pokémon telemetry experiment.*
