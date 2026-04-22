# CLAUDE.md — Project Ditto v2

This file provides guidance to Claude Code when working with this repository.

## Project Overview

**Project Ditto v2** is a replication-and-generality test for the Ditto constraint-chain
abstraction, applied to agent trajectories from two programming-task benchmarks:

- **Primary:** Terminal-Bench 2.0 (Harbor framework, ~500 trajectories)
- **Secondary:** SWE-bench Verified (~500 trajectories)
- **Validation:** Human debugging sessions (~100 trajectories)

The experiment tests whether the same real-vs-shuffled detectability effect from Ditto v1
(Pokémon telemetry) reproduces on programming telemetry using the same six constraint types.

**Pre-registration:** `SPEC.md` + `SPEC.pdf` — thresholds and methodology are frozen.

The v1 codebase is at `github.com/safiqsindha/Project-Ditto`.  Do not rewrite modules
that v1 already has unless required by this plan.

## Before Starting ANY Session

Read these in order:
1. `SPEC.md` (pre-registration — thresholds are frozen)
2. This `CLAUDE.md`
3. The previous `SESSION_LOG.md` entry (if any)
4. `BUILD_PLAN.md` (session-by-session plan)

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Terminal-Bench data acquisition (Session 2)
python scripts/acquire_tb.py --source <path-or-url> --out data/terminal_bench/ --target 500

# SWE-bench data acquisition (Session 3)
python scripts/acquire_swe.py --source <path-or-url> --out data/swe_bench_verified/ --target 500

# Build constraint chains (Session 9)
python scripts/build_chains.py --source tb --data data/terminal_bench/ \
  --out-real chains/real/tb/ --out-shuffled chains/shuffled/tb/

# Build reference distributions (Session 10)
python -m src.reference build-raw --source tb --raw data/terminal_bench/ \
  --out data/reference_tb.pkl
python -m src.reference check --dist data/reference_tb.pkl \
  --chains chains/real/tb/ --target 0.9

# Dry-run evaluation (Session 11)
python -m src.runner --model haiku --source tb --chains chains/real/tb/ \
  --seed 42 --dry-run --n 5

# Full evaluation (Session 12)
python scripts/run_evaluation.py

# Score (Session 13 — SEPARATE SESSION, fresh environment)
python -m src.scorer --results results/blinded/ \
  --dist-tb data/reference_tb.pkl \
  --dist-swe data/reference_swe.pkl \
  --dist-human data/reference_human.pkl \
  --chains-real chains/real/ --chains-shuffled chains/shuffled/ \
  --out results/scored.json

# Run all tests
pytest tests/

# Gate 1 check (after Session 1)
pytest tests/test_shuffler.py
```

## Architecture

### Pipeline (in order)

```
data/<source>/*.jsonl          (raw trajectory records)
  → scripts/acquire_<source>.py
  → src/parser_<source>.py    parse_<source>_trajectory() → TrajectoryLog
  → src/aggregation.py        aggregate_<source>_events() → compressed events
  → src/translation.py        translate_trajectory()      → list[Constraint]
  → src/observability.py      apply_asymmetric_observability()
  → src/filter.py             is_valid_chain()
  → src/shuffler.py           shuffle_chain()
  → src/renderer.py           render_chain()
chains/real/<source>/*.jsonl   (one chain per trajectory)
chains/shuffled/<source>/*.jsonl
  → scripts/build_reference.py
data/reference_<source>.pkl    (StateSignature → action distribution)
  → src/runner.py
results/raw/<source>/*.json    (model responses, full metadata)
results/blinded/*.json         (stripped for scorer)
  → src/scorer.py
results/scored.json            (Layer 1/2/3 metrics + outcome tiers)
```

### Module roles

| Module | Status | Role |
|--------|--------|------|
| `src/translation.py` | **IN PROGRESS (Session 6)** | T-code: trajectory events → Constraint objects |
| `src/aggregation.py` | **STUB (Session 5)** | Source-specific event compression |
| `src/parser_tb.py` | **STUB (Session 2)** | Terminal-Bench trajectory parser |
| `src/parser_swe.py` | **STUB (Session 3)** | SWE-bench trajectory parser |
| `src/parser_human.py` | **STUB (Session 4)** | Human session parser |
| `src/filter.py` | **COPIED from v1 (unchanged)** | Chain validity check |
| `src/shuffler.py` | **COPIED from v1 (unchanged)** | Produces shuffled control chains |
| `src/normalize.py` | **COPIED from v1 (unchanged)** | Action string normalization |
| `src/scorer.py` | **COPIED from v1 (unchanged)** | Layer 1/2/3 scoring |
| `src/renderer.py` | **ADAPTED from v1** | Constraint → abstract English |
| `src/observability.py` | **ADAPTED from v1** | Asymmetric information reveal |
| `src/reference.py` | **ADAPTED from v1** | StateSignature → action distribution |
| `src/runner.py` | **ADAPTED from v1** | Model evaluation driver |
| `src/prompt_builder.py` | **ADAPTED from v1** | Prompt template v2.0-code |

### Key invariants

- **T-code is frozen after Session 8.** `src/translation.py`, `src/aggregation.py`,
  `src/renderer.py`, and the leakage vocabulary list must not change after the
  `T-code-v1.0-frozen` git tag.  Any modification is a pre-registration violation.
- **Scorer is blinded.** Session 13 runs in a fresh environment that reads only
  `results/blinded/`.  The scorer never sees model identity, condition, or seed.
- **No programming vocabulary in rendered chains.** The leakage check in `renderer.py`
  runs automatically on every chain.  Callers cannot bypass it.
- **Cutoff K = len(constraints) // 2**
- **Evaluation models:** `claude-haiku-4-5-20251001` and `claude-sonnet-4-6`
- **Seeds:** 42 (primary, T=0), 1337 and 7919 (variance study, T=0.5)

### Constraint types (identical to v1)

Six types: `ResourceBudget`, `ToolAvailability`, `SubGoalTransition`,
`InformationState`, `CoordinationDependency`, `OptimizationCriterion`.
All defined in `src/translation.py`.

### Abstract label conventions (T-code)

| Domain entity | Abstract label |
|---------------|----------------|
| File paths | `file_A` … `file_Z` (overflow: `file_OVERFLOW_N`) |
| Command names | `command_1` … `command_26` |
| Error types | `error_class_A` … `error_class_Z` |
| Sub-task phases | `exploration`, `hypothesis`, `implementation`, `validation`, `debugging` |

### Session handoff protocol

At the end of each session, write a `SESSION_LOG.md` entry with:
- Session number and date
- Tasks completed
- Gate status (if applicable)
- Deviations from plan (with justification)
- Files created or modified
- What the next session should do first
- Any blockers or uncertainties for human review

Do not start a new session without reading the previous log entry.

## Things to NOT do

- **Do not modify T-code after the `T-code-v1.0-frozen` tag.** This is a pre-registration violation.
- **Do not skip gates.** Stop and escalate to human review if a gate fails.
- **Do not run scoring in Session 12.** Scoring must happen in Session 13's fresh session.
- **Do not use synthetic data.** v2 has no synthetic fallback; stop and escalate if real data unavailable.
- **Do not scrape copyrighted or ToS-protected material** (especially Session 4 human sessions).
- **Do not modify v1's frozen code** (filter, shuffler, normalize, scorer) without explicit human approval.
- **Do not skip the pre-registration commit in Session 1.**
- **Do not modify pre-registered thresholds** to match observed results.

## Data provenance

Each data source must have a `SOURCE.md` in its data directory documenting:
- Source URL
- Date accessed
- Schema description
- Any consent/license considerations

## Budget reference

- Total API budget: ~$130–160 (Batches API)
- Expected evaluations: ~21,000 API calls (Session 12)
- Cost breakdown: ~$80–130 on Batches API
