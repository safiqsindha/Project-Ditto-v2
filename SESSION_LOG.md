# Session Log — Project Ditto v2

---

## Session 1 — 2026-04-22

### Tasks Completed

- Cloned v1 repo (`safiqsindha/Project-Ditto`) to `/tmp/ditto-v1` for reference
- Read v1 source files: `filter.py`, `shuffler.py`, `normalize.py`, `scorer.py`, `renderer.py`, `observability.py`, `reference.py`, `runner.py`, `prompt_builder.py`, `translation.py`
- Established branch `claude/start-v2-build-9K5HG`
- Created full directory scaffold:
  - `data/terminal_bench/`, `data/swe_bench_verified/`, `data/human_sessions/`
  - `chains/real/{tb,swe,human}/`, `chains/shuffled/{tb,swe,human}/`
  - `results/raw/`, `results/blinded/`
  - `.gitkeep` files in all empty directories
- Wrote `src/translation.py` — all six constraint dataclasses + `Constraint` union type; `translate_event` / `translate_trajectory` raise `NotImplementedError` (Session 6)
- Copied unchanged from v1: `src/filter.py`, `src/shuffler.py`, `src/normalize.py`, `src/scorer.py`
- Adapted from v1 (programming-domain changes):
  - `src/renderer.py` — replaced Pokémon leakage check with `check_programming_leakage` using a default programming vocabulary (~50 terms); `render_chain` raises `ValueError` on any leak
  - `src/observability.py` — updated entity labels (file/command/error_class instead of unit/action); suppression/bucketing logic unchanged
  - `src/reference.py` — `active_pair = (current_phase, last_command_label)`; CLI flag `--source {tb,swe,human}`; `check --target 0.9` (vs v1's 0.8)
  - `src/runner.py` — models: Haiku 4.5 + Sonnet 4.6 (no Opus); `--source` flag; `EVAL_CONFIGS` pre-registers T=0.0/seed42, T=0.5/seed1337, T=0.5/seed7919
  - `src/prompt_builder.py` — `PROMPT_VERSION = "v2.0-code"`; prompts reference "pipeline" not "battle"
- Created new stubs: `src/aggregation.py`, `src/parser_tb.py`, `src/parser_swe.py`, `src/parser_human.py`
- Wrote `src/__init__.py`, `tests/__init__.py`
- Wrote `tests/test_shuffler.py` from scratch (no v1 equivalent existed) — 15 tests across 4 classes: `TestChainMetadata`, `TestConstraintPreservation`, `TestTimestamps`, `TestDeterminismAndDiversity`
- Wrote `CLAUDE.md` — architecture doc, pipeline data flow, module status table, abstract label conventions, session handoff protocol
- Wrote `SPEC.md` — pre-registration document with hypothesis, success criteria, model params, data sources, gating decisions, methodology hardening notes
- Copied `SPEC.pdf` (immutable; same content as `ditto_v2_programming_spec_v11.pdf`)
- Wrote `pyproject.toml`, `requirements.txt`, `.env.example`, `.gitignore`
- Pre-registration commit: `7a9ebb8` ("Pre-registration commit — thresholds and methodology frozen")
- Cleanup commit: `ce8b482` ("Add .gitignore, remove cached pycache files") — removed accidentally-committed `__pycache__` artifacts

### Gate 1 Status

**PASSED** — `pytest tests/test_shuffler.py` — 15 passed

### Deviations from Plan

- No deviations from the pre-registration methodology
- `test_shuffler.py` written from scratch (v1 had no equivalent); tests validate dict-format chain JSONL structure to match actual chain file format

### Files Created or Modified

| File | Action |
|------|--------|
| `src/__init__.py` | Created |
| `src/translation.py` | Created (stub) |
| `src/filter.py` | Copied from v1 |
| `src/shuffler.py` | Copied from v1 |
| `src/normalize.py` | Copied from v1 |
| `src/scorer.py` | Copied from v1 |
| `src/renderer.py` | Adapted from v1 |
| `src/observability.py` | Adapted from v1 |
| `src/reference.py` | Adapted from v1 |
| `src/runner.py` | Adapted from v1 |
| `src/prompt_builder.py` | Adapted from v1 |
| `src/aggregation.py` | Created (stub) |
| `src/parser_tb.py` | Created (stub) |
| `src/parser_swe.py` | Created (stub) |
| `src/parser_human.py` | Created (stub) |
| `tests/__init__.py` | Created |
| `tests/test_shuffler.py` | Created |
| `CLAUDE.md` | Created |
| `SPEC.md` | Created |
| `SPEC.pdf` | Copied (immutable) |
| `pyproject.toml` | Created |
| `requirements.txt` | Created |
| `.env.example` | Created |
| `.gitignore` | Created |
| `data/*/` `.gitkeep` files | Created |
| `chains/*/` `.gitkeep` files | Created |
| `results/*/` `.gitkeep` files | Created |

### What Session 2 Should Do First

1. Implement `src/parser_tb.py` — `parse_tb_trajectory(raw)` mapping Terminal-Bench 2.0 JSONL records to `TrajectoryLog`/`TrajectoryEvent` objects
2. Write `scripts/acquire_tb.py` — download Terminal-Bench 2.0 trajectories (≥400 usable, target 500) into `data/terminal_bench/`
3. Run Gate 1 check: count usable trajectories — if < 400, stop and find alternative sources
4. Write `tests/test_parser_tb.py` with ≥ 5 tests on synthetic records

### Blockers / Uncertainties for Human Review

1. **Tag push blocked (HTTP 403)**: `git push origin v2-preregistration` failed. The tag `v2-preregistration` exists locally at commit `ce8b482` but was not pushed to remote. The remote likely requires explicit tag-push permissions or the tag must be created via the GitHub API. **Action needed**: either grant tag-push permissions to the automation user, or manually run `git push origin v2-preregistration` from a credentialed shell.

2. **Terminal-Bench 2.0 availability**: Session 2 requires ≥400 usable trajectories. If the dataset is not yet publicly available or is gated, an `HF_TOKEN` will be needed and a fallback source strategy should be decided before Session 2 starts.

---

## Session 2 — 2026-04-22

### Tasks Completed

- Implemented `src/parser_tb.py` — full `parse_tb_trajectory()` for inspect-ai eval log format
  - Handles tool call messages: classifies bash_call / file_read / file_edit / test_run
  - Retroactively fills test_run outcomes from tool result messages
  - Emits error_reveal events when output matches error/exception patterns
  - Emits context_update event if token usage metadata is present
  - `filter_trajectory()`: ≥15 events AND outcome ∈ {"pass","fail"}
- Wrote `scripts/acquire_tb.py`
  - Accepts `--source` (local path or HuggingFace dataset ID), `--out`, `--target`, `--gate-threshold`
  - Handles inspect-ai eval log format (dict with "samples" key) and plain JSONL
  - Gate 1 check: exits with code 1 if usable count < threshold (default 400)
- Wrote `tests/test_parser_tb.py` — 43 tests across 5 classes:
  `TestBasicParsing`, `TestOutcomeExtraction`, `TestEventExtraction`,
  `TestCommandClassification` (12 parametrized cases), `TestFilterTrajectory`
- Wrote `data/terminal_bench/SOURCE.md` — provenance template, schema, license notes, Gate 1 status

### Gate 1 Status (data gate)

**PENDING** — `scripts/acquire_tb.py` is implemented and tested but data has not been
downloaded.  Gate 1 (≥400 usable trajectories) cannot be checked until Terminal-Bench 2.0
data is available.  See Blockers section.

### Deviations from Plan

- Parser implemented fully (not left as stub); safe because T-code is the freeze point.

### Files Created or Modified

| File | Action |
|------|--------|
| `src/parser_tb.py` | Implemented (replaces stub) |
| `scripts/acquire_tb.py` | Created |
| `tests/test_parser_tb.py` | Created |
| `data/terminal_bench/SOURCE.md` | Created |

### Blockers / Uncertainties for Human Review

1. **Terminal-Bench 2.0 dataset location**: The exact HuggingFace dataset ID is not
   confirmed.  `acquire_tb.py` defaults to `terminal-bench/terminal-bench-2.0`.
   **Action needed**: confirm dataset ID (or local path) before running data acquisition.

---

## Session 3 — 2026-04-22

### Tasks Completed

- Implemented `src/parser_swe.py` — full `parse_swe_trajectory()` for SWE-agent format
  - Supports Format A (action/observation step list — most common SWE-agent output)
  - Supports Format B (chat-style messages — newer SWE-agent / mini-SWE-agent)
  - Supports `"trajectory"` key as alias for `"traj"`
  - SWE-bench-specific: `git diff/apply` and editor commands classified as file_edit
  - Outcome from `info.exit_status` (submitted→pass; early_exit→fail)
  - Context_update from `info.model_stats.tokens_sent + tokens_received`
  - Reuses TB parser helpers for event-type uniformity across sources
- Wrote `scripts/acquire_swe.py` — same structure as `acquire_tb.py`; Gate 2 check at exit
- Wrote `tests/test_parser_swe.py` — 39 tests across 5 classes:
  `TestBasicParsing`, `TestOutcomeExtraction`, `TestEventExtraction`,
  `TestSWECommandClassification` (8 parametrized cases), `TestFilterTrajectory`
- Wrote `data/swe_bench_verified/SOURCE.md`
- All 97 tests pass: 15 shuffler + 43 TB parser + 39 SWE parser

### Gate 2 Status (data gate)

**PENDING** — acquisition script implemented but data not yet downloaded.

### Deviations from Plan

- None from spec methodology.

### Files Created or Modified

| File | Action |
|------|--------|
| `src/parser_swe.py` | Implemented (replaces stub) |
| `scripts/acquire_swe.py` | Created |
| `tests/test_parser_swe.py` | Created |
| `data/swe_bench_verified/SOURCE.md` | Created |

### What Session 4 Should Do First

1. Locate public human debugging session data (no copyrighted/ToS-protected material)
2. Implement `src/parser_human.py` and `scripts/acquire_human.py`
3. Write `tests/test_parser_human.py` and `data/human_sessions/SOURCE.md`
4. Confirm TB and SWE dataset IDs; run data acquisition to clear Gates 1 and 2

### Blockers / Uncertainties for Human Review

1. **Terminal-Bench 2.0 dataset ID**: Not confirmed.  Defaults to
   `terminal-bench/terminal-bench-2.0`.  Gate 1 cannot clear until accessible.

2. **SWE-bench trajectory source**: `princeton-nlp/SWE-bench_Verified` contains task
   descriptions only, not agent trajectories.  Need a dataset of SWE-agent runs on the
   Verified split, or a local SWE-agent run.  **Action needed** before Sessions 4/5.

3. **Human session data source**: ≥100 trajectories required.  Public source with permissive
   license must be identified.  **Human decision needed** on source before Session 4.

---
