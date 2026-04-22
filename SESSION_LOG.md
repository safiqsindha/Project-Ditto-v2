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

## Session 4 — 2026-04-22

### Tasks Completed

- Implemented `src/parser_human.py` — full `parse_human_session()` for SpecStory Markdown format
  - Splits turns by `## User/Assistant/Agent/Human/AI/Copilot/System` headers
  - `_classify_user_turn()`: traceback-containing turns → error_reveal; code block → file_read; else → task_transition
  - `_classify_assistant_turn()`: bash block with test keyword → test_run; bash block → bash_call; code block → file_edit
  - `detect_secrets(content)`: patterns for Anthropic/OpenAI keys, GitHub PATs, AWS keys, bearer tokens, credential assignments
  - `redact_emails(content)`: replaces email addresses with `[REDACTED_EMAIL]`
  - `filter_trajectory(min_events=5)`: lower threshold appropriate for human sessions
  - `parse_human_session(raw)`: raw dict with {session_id, content, repo}
- Wrote `scripts/acquire_human.py` — GitHub Code Search API acquisition of SpecStory files
  - `GitHubClient` class: `search_code()`, `get_blob()`, `get_repo_license()` via urllib
  - Monthly date-prefix partitioned queries: `path:.specstory/history filename:YYYY-MM extension:md`
  - Rate limiting: 2.2s between search requests, 0.5s between blob/repo fetches
  - JSON file caching in `.cache/acquire_human/`
  - `_ACCEPTABLE_LICENSES` frozenset: MIT, Apache-2.0, BSD-2/3-Clause, ISC, Unlicense, CC0-1.0, MPL-2.0, LGPL variants
  - Writes `trajectories.jsonl` AND `rejection_log.jsonl`
  - Gate 2c check: exits code 1 if usable < 100
- Wrote `tests/test_parser_human.py` — 30 tests across 6 classes:
  `TestTurnSplitting`, `TestBasicParsing`, `TestEventTypes`, `TestOutcome`,
  `TestFilterTrajectory`, `TestSecretDetection`
- Wrote `data/human_sessions/SOURCE.md` — SpecStory methodology, acquisition script, license notes, Gate 2c status

### Gate 2c Status

**PENDING** — acquisition script implemented and tested; real GitHub acquisition requires
GITHUB_TOKEN and human action.  Gate 2c (≥100 sessions) cannot clear until acquisition runs.

### Deviations from Plan

- **Revised data source** (user instruction): Human sessions are sourced from SpecStory
  Markdown files in public GitHub repos (arXiv 2604.00436 methodology), NOT general
  debugging session databases.  This matches the revised Session 4 instructions.
- `detect_secrets()` and `redact_emails()` placed in `src/parser_human.py` (not only in
  acquire_human.py) to be testable and importable by any module that processes raw content.

### Files Created or Modified

| File | Action |
|------|--------|
| `src/parser_human.py` | Implemented (replaces stub) |
| `scripts/acquire_human.py` | Created |
| `tests/test_parser_human.py` | Created |
| `data/human_sessions/SOURCE.md` | Created |

### Blockers / Uncertainties for Human Review

1. **GITHUB_TOKEN required**: `scripts/acquire_human.py` requires a GitHub personal access
   token with `public_repo` (read-only) scope.  Set `GITHUB_TOKEN` env var before running.
   Gate 2c cannot clear without this.

---

## Session 5 — 2026-04-22

### Tasks Completed

- Implemented `src/aggregation.py` — source-specific event compression
  - `aggregate_tb_events()`: drops lone no-ops (ls/pwd/echo without useful follow-up);
    collapses consecutive identical bash_calls; collapses consecutive same-path file_reads
  - `aggregate_swe_events()`: collapses file-read bursts (≥3 consecutive → 1 with burst_size);
    compresses retry loops (same bash_call repeated N times → retry_count); truncates
    error_reveal messages to 120 chars
  - `aggregate_human_events()`: collapses consecutive identical task_transitions; merges
    consecutive same-path file_edits; passes all other events through unchanged
  - `aggregate_events(events, source)`: dispatcher to source-specific function
- Wrote `tests/test_aggregation.py` — 29 tests across 4 classes:
  `TestTBAggregation`, `TestSWEAggregation`, `TestHumanAggregation`, `TestDispatcher`
- All 156 tests pass: 15 shuffler + 43 TB parser + 39 SWE parser + 30 human parser + 29 aggregation

### Gate Status

No data gates in Session 5.  Code-quality gate: all 156 tests pass.

### Deviations from Plan

- None.

### Files Created or Modified

| File | Action |
|------|--------|
| `src/aggregation.py` | Implemented (replaces stub) |
| `tests/test_aggregation.py` | Created |

---

## Session 6 — 2026-04-22

### Tasks Completed

- Implemented `src/translation.py` — T-code: trajectory events → Constraint objects
  - All six Constraint dataclasses: `ResourceBudget`, `ToolAvailability`, `SubGoalTransition`,
    `InformationState`, `CoordinationDependency`, `OptimizationCriterion`
  - `TranslationContext`: mutable state across events — phase, label maps, resource levels,
    uncertainty, flags
  - Per-event translators (all in `_TRANSLATORS` dict):
    - `bash_call` → `ResourceBudget(context_window)` + optional `ToolAvailability(context_window, unavailable)` at <20% remaining
    - `file_read` → `InformationState(observable_added=[file_label])`
    - `file_edit` → `SubGoalTransition(→implementation)` first time; `ToolAvailability(file_label, available)` subsequently
    - `test_run pass` → `SubGoalTransition(→validation)` + `OptimizationCriterion`
    - `test_run fail` → `SubGoalTransition(→debugging)` + `ResourceBudget(patience)` + `ToolAvailability(test_suite, unavailable, recover_in=3)`
    - `error_reveal` → alternates `InformationState` (even) / `CoordinationDependency` (odd)
    - `context_update` → `ResourceBudget(context_window)` + optional `ToolAvailability(context_window, unavailable)` if >80% used
    - `task_transition` → `SubGoalTransition`
  - `translate_trajectory(events, source) → (list[Constraint], list[tuple[str, str]])`
    returns constraints AND active_pair_by_step (phase, last_command_label)
  - `constraint_to_dict()` / `constraint_from_dict()`: JSON serialization
- Wrote `tests/test_translation.py` — 40 tests across 4 classes:
  `TestEventTranslation` (22), `TestTranslateTrajectory` (5), `TestFilterInvariants` (6),
  `TestSerialisation` (7)
  - Key test: `test_valid_trajectory_passes_filter` — synthetic trajectory satisfies all
    `is_valid_chain()` invariants (≥10 RB, ≥2 SGT, ≥1 TA unavailable, length 20–40)
- All 196 tests pass

### T-code Freeze

T-code (`src/translation.py`, `src/aggregation.py`) is frozen as of this session under
pre-registration tag `T-code-v1.0-frozen`.  The tag exists locally; push requires human
action (see blockers from Session 1).

### Deviations from Plan

- None from methodology.

### Files Created or Modified

| File | Action |
|------|--------|
| `src/translation.py` | Implemented (replaces stub) |
| `tests/test_translation.py` | Created |

---

## Session 7 — 2026-04-22

### Tasks Completed

- Expanded `src/renderer.py` programming-domain leakage vocabulary
  - From ~50 seed terms to ~140 terms across: Python keywords, Python exception types,
    common packages (Django, Flask, NumPy, PyTorch, etc.), shell commands (git, make,
    pip, npm, docker, etc.), programming jargon, file/path vocabulary
  - Fixed false positive: `_render_information_state` changed from "none" to "(empty)"
    for empty observable lists — previously matched `None` in vocab case-insensitively
- Wrote `scripts/build_chains.py` — full pipeline script
  - Steps: load trajectories.jsonl → reconstruct TrajectoryEvent objects → aggregate →
    translate (T-code) → asymmetric observability → `is_valid_chain()` filter → render
    (leakage check) → shuffle (seeds 42, 1337, 7919) → save JSONL to chains/real/ and
    chains/shuffled/
  - `--gate3` flag: verifies ≥20 real chains pass leakage check; exits code 1 on failure
  - Per-trajectory error categorisation: no_events / filter_fail / leakage / other_error
- Wrote `tests/test_pipeline_e2e.py` — 32 end-to-end integration tests
  - `TestFullPipelineTB/SWE/Human`: pipeline produces valid, filter-passing, leak-free chains
  - `TestShuffler`: ordering changes, type counts preserved, timestamps non-decreasing, seeds differ
  - `TestSerialisation`: round-trip through constraint_to_dict/from_dict and JSONL file
  - `TestGate3Synthetic`: 20 chains/source (60 chains + 40 TB = 100 chains total) pass
    leakage check — Gate 3 validated on synthetic data
  - `TestBuildChainsModule`: unit tests for `build_chains.py` helpers
- Gate 3 (synthetic) — **PASSED**: 40+ TB, 20 SWE, 20 human synthetic chains all pass
  `render_chain()` without programming vocabulary leakage

### Gate 3 Status

**PASSED (synthetic)** — Gate 3 validated on synthetic trajectories.  Real-data Gate 3
(≥20 chains/source from actual trajectories.jsonl) cannot run until data acquisition
(Sessions 2c, 3c, 4c) completes with human action.

### Deviations from Plan

- None from methodology.

### Files Created or Modified

| File | Action |
|------|--------|
| `src/renderer.py` | Expanded vocab (~50→~140 terms); fixed false positive in IS rendering |
| `scripts/build_chains.py` | Created |
| `tests/test_pipeline_e2e.py` | Created |

### What Session 8 Should Do First

All code is implemented and tested.  Session 8 is the human-action session:
1. Confirm Terminal-Bench 2.0 dataset ID and run `scripts/acquire_tb.py` → Gate 1
2. Provide SWE-bench trajectory source and run `scripts/acquire_swe.py` → Gate 2
3. Set `GITHUB_TOKEN` and run `scripts/acquire_human.py` → Gate 2c
4. Run `scripts/build_chains.py` for each source → Gate 3 on real data
5. Push the `T-code-v1.0-frozen` tag to remote

### Blockers / Uncertainties for Human Review

1. **Data acquisition requires human action**: All three data gates (Gate 1, 2, 2c) require
   human-supplied credentials or dataset paths.  The pipeline is ready but cannot run without
   real data.

2. **T-code-v1.0-frozen tag not pushed**: Local tag exists; push requires `git push origin
   T-code-v1.0-frozen` from a credentialed shell.

---
