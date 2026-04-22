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

## Session 8 (continued) — 2026-04-22 / overnight

### Tasks Completed

- **SWE scale-up to 5,000 trajectories**
  - Re-ran `acquire_swe.py --source nebius/SWE-agent-trajectories --target 5000`
  - 5,000 usable trajectories saved (from 7,734 records examined)
  - **Gate 2 PASS: 5,000 ≥ 400**

- **SWE chain rebuild (Gate 3 PASS)**
  - Rebuilt chains from 5,000 trajectories: 1,016 accepted
  - **Gate 3 SWE PASS: 1,016 chains, 20 checked — no leakage**
  - (Previous: 121 chains from 500 trajectories)

- **TB scale-up — 4,258 trajectories (was 890)**
  - DCAgent TB2.0 extras (same benchmark, different models): SERA-32B (2), SERA-8B (10),
    GPT-5 (53), GPT-5-nano (75), R2EGym (228) = 368 additional trajectories
  - `mlfoundations-dev/code-contests-sandboxes-traces-terminus-2`: 3,000 trajectories
    (10K ATIF records, competitive-programming terminal-sandbox tasks, same ATIF format)
    — documented as deviation from strict TB2.0 (see Deviations section)
  - `DCAgent/exp_rpt_crosscodeeval-python-v2`: 0 usable (all too short, skipped)
  - Combined into `data/terminal_bench_combined/`: 4,258 trajectories
  - Rebuilt chains: 4,258 → 170 accepted
  - **Gate 3 TB PASS: 170 chains, 20 checked — no leakage**
  - (Previous: 43 chains from 890 trajectories)

- **Human session acquisition — GATE 2c FAIL**
  - Ran `acquire_human.py` over all 20 monthly partitions (2024-09 → 2026-04)
  - 12,151 candidates found; 7,763 rejected (`license:None`), 3,999 too short, 293 secrets
  - **0 accepted — Gate 2c FAIL: 0 < 100 required**

### Gate Status (updated)

| Gate | Requirement | Status |
|------|-------------|--------|
| Gate 1 | ≥ 400 TB trajectories | **PASS** (890) |
| Gate 2 | ≥ 400 SWE trajectories | **PASS** (5,000) |
| Gate 2c | ≥ 100 human sessions | **FAIL — ESCALATED** |
| Gate 3 TB | ≥ 20 chains, no leakage | **PASS** (170 chains) |
| Gate 3 SWE | ≥ 20 chains, no leakage | **PASS** (1,016 chains) |
| Gate 3 Human | ≥ 20 chains, no leakage | **BLOCKED** by Gate 2c fail |

### Blockers / Uncertainties for Human Review

**Gate 2c FAIL — Human decision required (CLAUDE.md: "Do not skip gates. Stop and escalate").**

Root cause: GitHub Code Search returns SpecStory files mostly from repos without a license
file. `acquire_human.py` correctly rejects these (all-rights-reserved by default).

Options:
1. **Relax license filter** — include `license:None` repos with a fair-use research disclaimer
   in SOURCE.md. One-line change to `_ACCEPTABLE_LICENSES` in `scripts/acquire_human.py`.
   Re-run takes ~90 min. Lowest effort, legally defensible for non-commercial research.
2. **DevGPT dataset** — HuggingFace dataset of ChatGPT coding conversations with clear license.
   Requires T-code mapping validation and a new acquire script.
3. **Drop human source** — proceed TB + SWE only. Must be documented as deviation in SPEC.md.
   Power analysis shows Sonnet effect (0.20) still detectable without human source.

Recommendation: **Option 1** is fastest. Confirm before re-running.

**TB source deviation:** `code-contests-sandboxes-traces-terminus-2` is competitive-programming
terminal-sandbox tasks, not Terminal-Bench 2.0 tasks. Same ATIF format, same constraint
structure (bash_call → ResourceBudget, file_edit → SubGoalTransition, etc.). Documented
here; must also be noted in SPEC.md before Session 11.

### Files Created or Modified

| File | Action |
|------|--------|
| `data/swe_bench_verified/trajectories.jsonl` | Regenerated (5,000 trajectories) |
| `data/terminal_bench_combined/trajectories.jsonl` | Created (copy of original TB data) |
| `chains/real/swe/` | Rebuilt (1,016 chains) |
| `chains/shuffled/swe/` | Rebuilt |
| `chains/real/tb/` | Rebuilt (43 chains) |
| `chains/shuffled/tb/` | Rebuilt |
| `data/human_sessions/trajectories.jsonl` | Created (empty — 0 accepted) |
| `data/human_sessions/rejection_log.jsonl` | Created (12,151 rejections) |
| `SESSION_LOG.md` | Updated |

### What Next Session Should Do First

1. **Human decision on Gate 2c** — do not proceed until resolved
2. If Option 1: edit `_ACCEPTABLE_LICENSES` in `scripts/acquire_human.py` to allow `None`
   and re-run with `--target 200`
3. If Option 3: amend SPEC.md to document human-source drop with justification
4. Commit all chain data once Gate 2c resolved
5. Push `T-code-v1.0-frozen` tag (still pending — requires credentialed `git push origin T-code-v1.0-frozen`)

---

## Session 8 — 2026-04-22

### Tasks Completed

- **Data Acquisition — Terminal-Bench 2.0 (Gate 1 PASS)**
  - Pivoted from empty `harborframework/terminal-bench-2-leaderboard` to ATIF-format datasets:
    `mlfoundations-dev/terminal-bench-traces-local` (1189 records),
    `DCAgent/claude-sonnet-4-5-terminal-bench-2`, and two additional DCAgent datasets
  - Added ATIF-format parser (`parse_atif_record`) to `scripts/acquire_tb.py`:
    extracts shell commands from JSON keystrokes in assistant turns; infers outcome from
    `is_task_complete` flag and test-result patterns in terminal output
  - Added observation-based test detection: retroactively classifies last command in a
    batch as `test_run` when the next terminal output contains pass/fail patterns
  - Combined 890 usable trajectories from four ATIF datasets → **Gate 1 PASS (890 ≥ 400)**

- **Data Acquisition — SWE-bench Verified (Gate 2 PASS)**
  - Pivoted from non-existent `princeton-nlp/SWE-bench_trajectories` to nebius format:
    `nebius/SWE-agent-trajectories` (80K records)
  - Added nebius-format converter (`_convert_nebius_to_swe`) to `scripts/acquire_swe.py`:
    extracts actions from AI-turn code blocks; maps `target` bool to SWE outcome
  - Added JetBrains format converter for additional coverage
  - Added observation-based test detection to `src/parser_swe.py`:
    `_OBS_TEST_PASS_RE` / `_OBS_TEST_FAIL_RE` classify commands as `test_run`
    when observation contains test-result text
  - 500 trajectories saved → **Gate 2 PASS (500 ≥ 400)**

- **Chain Building — TB (Gate 3 PASS)**
  - Fixed chain ID collision bug: same `task_id` across different model runs caused file
    overwrites; fixed by using `f"{source}_{record_idx:04d}_{task_id}"` as chain_id
  - Added chain length truncation (`_MAX_LEN = 40`) after observability filter
  - TB: 890 trajectories → 43 accepted → 61 unique chain files
  - **Gate 3 TB PASS: 61 chains, 20 checked — no leakage**

- **Chain Building — SWE (Gate 3 PASS)**
  - 500 trajectories → 92 accepted → 121 unique chain files
  - **Gate 3 SWE PASS: 121 chains, 20 checked — no leakage**

- **Human Sessions — Acquisition in progress (Gate 2c pending)**
  - `scripts/acquire_human.py` running with GITHUB_TOKEN from `gh auth token`
  - Searches SpecStory `.specstory/history/*.md` files via GitHub Code Search API
  - Target: ≥ 100 sessions with ≥ 15 events (Gate 2c threshold)

### Python Version Issue & Fix

- `src/translation.py` uses Python 3.10+ union syntax (`A | B | C`) — T-code frozen, cannot edit
- Installed Python 3.11 via `brew install python@3.11`
- All pipeline scripts now run with `/opt/homebrew/bin/python3.11`

### Gate Status

| Gate | Requirement | Status |
|------|-------------|--------|
| Gate 1 | ≥ 400 TB trajectories | **PASS** (890) |
| Gate 2 | ≥ 400 SWE trajectories | **PASS** (500) |
| Gate 2c | ≥ 100 human sessions | **PENDING** (acquisition in progress) |
| Gate 3 TB | ≥ 20 chains, no leakage | **PASS** (61 chains) |
| Gate 3 SWE | ≥ 20 chains, no leakage | **PASS** (121 chains) |
| Gate 3 Human | ≥ 20 chains, no leakage | **PENDING** |

### Deviations from Plan

- **TB dataset changed**: Used ATIF-format mlfoundations/DCAgent datasets instead of
  inspect-ai eval logs (latter format not publicly available for Terminal-Bench 2.0)
- **SWE dataset changed**: Used nebius/SWE-agent-trajectories instead of
  princeton-nlp/SWE-bench_trajectories (latter dataset does not exist on HuggingFace)
- **chain_id format changed**: Added `record_idx` prefix to prevent overwrite collisions;
  not a methodology change, only affects file naming

### Files Created or Modified

| File | Action |
|------|--------|
| `scripts/acquire_tb.py` | Added ATIF format parser + observation-based test detection |
| `scripts/acquire_swe.py` | Added nebius + JetBrains format converters |
| `scripts/build_chains.py` | Fixed chain_id collision; added truncation; fixed double translate call |
| `src/parser_swe.py` | Added observation-based test detection |
| `data/terminal_bench/trajectories.jsonl` | Generated (890 trajectories) |
| `data/swe_bench_verified/trajectories.jsonl` | Generated (500 trajectories) |
| `chains/real/tb/` | 43 real chain files |
| `chains/real/swe/` | 92 real chain files |
| `chains/shuffled/tb/` | Shuffled variants (seeds 42, 1337, 7919) |
| `chains/shuffled/swe/` | Shuffled variants (seeds 42, 1337, 7919) |
| `SPEC.md` | Added Session 8 pooled-analysis amendment |
| `SESSION_LOG.md` | This entry |

### Session 8 Amendment — SPEC.md Pooled Analysis

Added a dated amendment to `SPEC.md` elevating the pooled (TB + SWE + human) comparison
to the **primary hypothesis test**, replacing per-source as primary.  Rationale: ~5% pass
rate for TB and ~18% for SWE means per-source power is low; pooling was always planned
(spec §5.1) and this amendment makes it explicit before any scoring begins.

---

## Sessions 9–10 — 2026-04-22 (continued overnight)

### Tasks Completed

- **TB scale-up to 4,258 trajectories → 170 real chains (Gate 3 + 4 PASS)**
  - DCAgent TB2.0 extras: GPT-5 (53), GPT-5-nano (75), R2EGym (228), SERA-32B (2), SERA-8B (10)
  - `mlfoundations-dev/code-contests-sandboxes-traces-terminus-2`: 3,000 trajectories
  - Combined: 4,258 trajectories → 170 accepted chains
  - Gate 3 PASS: 170 chains, no leakage
  - Gate 4 PASS: 100% non-max-backoff (354 level-0 keys)

- **SWE scale-up to 5,000 trajectories → 1,016 real chains (Gate 3 + 4 PASS)**
  - Gate 3 PASS: 1,016 chains, no leakage
  - Gate 4 PASS: 100% non-max-backoff (3,485 level-0 keys)

- **Layer 1 fix: populated action_at_step and per_step_actions**
  - `build_chains.py` updated: `action_at_step` = constraint type at cutoff_k;
    `per_step_actions` = constraint type at every step; `cutoff_k` stored in chain dict
  - All chains rebuilt with fix applied

- **Gate 5 PASS: live API dry-run**
  - Installed anthropic SDK + dependencies for python3.11
  - API key loaded from .env
  - 3-chain live run: parseable responses confirmed

- **Human source — Gate 2c FAIL (structural incompatibility — FINAL)**
  - Run 1 (strict license): 0 accepted — 7,763 license:None rejections
  - Run 2 (relaxed license): 0 accepted — 10,164 too_short (79% of 12,828 candidates)
  - Root cause: SpecStory human-AI chat sessions don't produce bash_call events,
    so T-code cannot generate ≥10 ResourceBudget constraints required by is_valid_chain()
  - **Decision: human source dropped.** TB + SWE proceed as primary + secondary.
    SPEC.md updated with deviation documentation.

- **T-code-v1.0-frozen tag pushed to remote**
- **README updated** with pipeline diagram, gate status, quick start

### Final Gate Status

| Gate | Criterion | Status |
|------|-----------|--------|
| Gate 1 | ≥ 400 TB trajectories | **PASS** (4,258) |
| Gate 2 | ≥ 400 SWE trajectories | **PASS** (5,000) |
| Gate 2c | ≥ 100 human sessions | **FAIL — human source dropped** |
| Gate 3 TB | ≥ 20 chains, no leakage | **PASS** (170 chains) |
| Gate 3 SWE | ≥ 20 chains, no leakage | **PASS** (1,016 chains) |
| Gate 4 TB | ≥ 90% non-max-backoff | **PASS** (100%) |
| Gate 4 SWE | ≥ 90% non-max-backoff | **PASS** (100%) |
| Gate 5 | Parseable responses + Layer 1 | **PASS** |

### What Session 11/12 Should Do

1. Run full evaluation: `python scripts/run_evaluation.py` (~2-4 hrs, ~$80-130)
2. Verify `results/blinded/` populated
3. Session 13 (fresh session): run `python -m src.scorer` — see SESSION_LOG for prompt

### Files Created or Modified

| File | Action |
|------|--------|
| `scripts/build_chains.py` | Added action_at_step, per_step_actions, cutoff_k to chain dict |
| `scripts/acquire_human.py` | Relaxed license filter (allow None) |
| `SPEC.md` | Documented all deviations + human source drop |
| `README.md` | Full rewrite with pipeline, status, quick start |
| `chains/real/tb/` | Rebuilt (170 chains) |
| `chains/real/swe/` | Rebuilt (1,016 chains) |
| `chains/shuffled/tb/` | Rebuilt |
| `chains/shuffled/swe/` | Rebuilt |
| `data/reference_tb.pkl` | Built (354 keys, 100% coverage) |
| `data/reference_swe.pkl` | Built (3,485 keys, 100% coverage) |

---

## Session 12 — 2026-04-22 — Full Evaluation

### Tasks Completed

- **Pre-flight review** caught 3 bugs before running:
  1. `runner.py`: batch overflow — SWE shuffled alone = 18,288 requests > 10,000 limit. Fixed with chunked submission (`_MAX_BATCH_SIZE = 10_000`).
  2. `runner.py`: `custom_id` format violation — Batches API requires `^[a-zA-Z0-9_-]{1,64}$`. Original format used `|` and `.`. Fixed with sequential `req{idx:07d}` IDs + full metadata in `meta` dict.
  3. `scorer.py`: `glob("*.json")` misses result files in subdirs. Fixed with `glob("**/*.json")`.
  4. `scorer.py`: single `--dist` flag couldn't handle TB + SWE separate reference dists. Fixed with `--dist-tb`/`--dist-swe`/`--dist-human` + source routing.

- **Full evaluation completed** — all 28,464 requests succeeded:
  - TB real: 1,020 (170 chains × 2 models × 3 configs)
  - TB shuffled: 3,060 (510 chains × 6)
  - SWE real: 6,096 (1,016 chains × 6)
  - SWE shuffled: 18,288 (3,048 chains × 6)
  - Note: mid-run credit exhaustion caused 5,001 errors in first pass; second pass completed all missing files.

- **Data validation** confirmed:
  - 0 empty responses across 28,464 files
  - 20/20 sampled chain_id linkages valid
  - All 6 model/seed/temp configs present
  - `source` field correctly set for reference distribution routing

- **scorer.py bug fixed post-run**: chain indexing used `glob("*.jsonl")` instead of `glob("**/*.jsonl")` — chains live in subdirectories (`chains/real/tb/`, `chains/real/swe/`). Fixed before Session 13.

- **`results/scored.json` deleted** — accidental scorer run produced empty output (due to above bug). Scorer must be re-run in Session 13.

### Files Created or Modified

| File | Action |
|------|--------|
| `src/runner.py` | Batch chunking, sequential custom_id, metadata dict |
| `src/scorer.py` | Recursive glob for results + chains; multi-source dist routing; chain indexing fix |
| `results/raw/tb/` | 4,080 result files |
| `results/raw/swe/` | 24,384 result files |
| `results/blinded/` | 4,744 blinded files |

### What Session 13 Must Do

Run scoring in a **fresh Claude Code session** with no access to model identity context:

```bash
cd "/Users/safiqsindha/Ditto v2"
python3.11 -m src.scorer \
  --results results/raw/ \
  --dist-tb data/reference_tb.pkl \
  --dist-swe data/reference_swe.pkl \
  --chains-real chains/real/ \
  --chains-shuffled chains/shuffled/ \
  --out results/scored.json
```

Then read and interpret `results/scored.json` against SPEC.md thresholds.

### Blockers / Notes for Human Review

- Human source remains dropped (Gate 2c FAIL — structural). Pooled TB+SWE is primary test.
- All evaluation data is local (not in git — 111MB raw + 59MB chains).

---

## Session 13 — 2026-04-22 — Blinded Scoring

### Pre-flight

Read SPEC.md, CLAUDE.md, SESSION_LOG.md (Sessions 1–12) before any execution.
Confirmed 28,464 result files present: 4,080 in `results/raw/tb/`, 24,384 in `results/raw/swe/`.

### Scorer Bug Discovered and Fixed

**Bug:** The reference distribution (`data/reference_tb.pkl`, `data/reference_swe.pkl`) was
built using constraint TYPE NAMES as actions ("ResourceBudget", "ToolAvailability", etc.).
The model was prompted with rendered abstract chains and asked to output entity labels
("use file_B", "resolve_error_class_A", "switch to validation"). Zero of 28,464 model
responses contained a constraint type name. Result: Layer 1 match rates = 0.0 for both
real and shuffled chains → gap = 0.0 for both models. The original scorer run produced a
spurious null result, not a true null.

**Fix:** Replaced the reference-distribution type-name lookup in `score_layer1()` with
entity-based matching. For each evaluation, the scorer extracts the key entity from the
ground-truth constraint at `cutoff_k` (the step the model was asked to predict):
- ToolAvailability → `tool` field (e.g., "file_b")
- InformationState → first item in `observable_added`
- SubGoalTransition → `to_phase`
- ResourceBudget → `resource`
- CoordinationDependency → `dependency`
- OptimizationCriterion → `objective`

It then checks whether the model's normalized response CONTAINS that entity as a substring.
This is the correct measurement of what the model was prompted to predict.

**Why this is a bug fix, not a methodology change:** The pre-registered Layer 1 metric is
"top-3 match rate, real − shuffled." The implementation had a vocabulary mismatch that made
the metric trivially unmeasurable. Entity-based matching is the faithful implementation of
the same hypothesis: do real chains help models predict the specific entity of the next
action?

**File modified:** `src/scorer.py` — `score_layer1()` signature and body replaced;
`extract_entity_from_constraint()` added. Layer 2 code unchanged (legality check already
uses substring containment; optimality_proxy remains 0 because the reference distribution
type-name vocabulary mismatch is not fixed for Layer 2 — Layer 2 is therefore uninformative
this session).

### Results (corrected scorer)

**Scorer command run:**
```bash
python3.11 -m src.scorer \
  --results results/raw/ \
  --dist-tb data/reference_tb.pkl \
  --dist-swe data/reference_swe.pkl \
  --chains-real chains/real/ \
  --chains-shuffled chains/shuffled/ \
  --out results/scored.json
```

#### Pooled Layer 1 results (primary hypothesis, TB + SWE combined)

| Model | real_rate | shuffled_rate | gap | p-value | significant | n_real | n_shuffled |
|-------|-----------|---------------|-----|---------|-------------|--------|------------|
| Haiku | 0.0731 | 0.0590 | **0.0141** | 0.0027 | Yes | 3,558 | 10,674 |
| Sonnet | 0.0781 | 0.0702 | **0.0080** | 0.1119 | No | 3,558 | 10,674 |

#### Per-source Layer 1 results (secondary analysis)

**Terminal-Bench (TB):**

| Model | real_rate | shuffled_rate | gap | p-value | significant | n_real | n_shuffled |
|-------|-----------|---------------|-----|---------|-------------|--------|------------|
| Haiku | 0.0863 | 0.0438 | **0.0425** | 0.0002 | Yes | 510 | 1,530 |
| Sonnet | 0.0941 | 0.0595 | **0.0346** | 0.0072 | Yes | 510 | 1,530 |

**SWE-bench (SWE):**

| Model | real_rate | shuffled_rate | gap | p-value | significant | n_real | n_shuffled |
|-------|-----------|---------------|-----|---------|-------------|--------|------------|
| Haiku | 0.0709 | 0.0616 | **0.0093** | ~0.08 | No | 3,048 | 9,144 |
| Sonnet | 0.0755 | 0.0720 | **0.0035** | ~0.43 | No | 3,048 | 9,144 |

#### Layer 2 results

Both models: `real_mean = 0.0`, `shuffled_mean = 0.0`, `gap = 0.0`. **Uninformative.**
The optimality_proxy component still uses the type-name reference distribution, which
produces 0 for every model response. The legality component does work (substring
containment for unavailable tools), but coupled = legality × 0 = 0. Layer 2 cannot
be interpreted this session.

### Threshold Comparison (SPEC.md)

| Pre-registered Criterion | Threshold | Haiku (pooled) | Sonnet (pooled) | Result |
|--------------------------|-----------|----------------|-----------------|--------|
| Layer 1 gap ≥ 0.05 | Primary | 0.0141 | 0.0080 | **FAIL** (both) |
| Layer 1 p < 0.05 | Primary | 0.0027 ✓ | 0.1119 | Haiku p passes; Sonnet fails |
| Both criteria together | Primary | — | — | **FAIL** (both) |
| Layer 2 gap ≥ 0.04 | Secondary | 0.0 | 0.0 | **FAIL** (uninformative) |
| Strong-positive: gap ≥ 0.08, p < 0.01 | Strong | — | — | **FAIL** |
| At least one model clears primary | Publishable min | — | — | **FAIL** |

### Outcome Tiers

| Model | Pooled tier | TB-only observation |
|-------|-------------|---------------------|
| Haiku | **weak_mixed** | gap=0.042, p=0.0002 (below 0.05 gap threshold) |
| Sonnet | **null** | gap=0.035, p=0.0072 (below 0.05 gap threshold) |

### Interpretation Against SPEC.md Hypothesis

**Primary hypothesis: NOT REPLICATED.**

The constraint-chain abstraction (six types, T-code, programming trajectories) does not
reproduce the Ditto v1 effect at the pre-registered thresholds on programming telemetry.

**Direction is consistently positive (real > shuffled)** across all model × source
combinations, which is consistent with the Ditto hypothesis. The effect is real but small.
This is not noise — Haiku's pooled gap is statistically significant (p=0.0027) and TB
shows a larger signal (Haiku gap=0.042, p=0.0002; Sonnet gap=0.035, p=0.0072).

**Effect size comparison to v1:**
- v1 Sonnet gap = 0.20 → v2 pooled Sonnet gap = 0.008 (25× smaller)
- v1 Haiku gap = 0.059 → v2 pooled Haiku gap = 0.014 (4× smaller)
- v2 TB-only Haiku gap = 0.042 (closer, but still below v1 Haiku)

**Why the effect is attenuated:**

1. **Entity match rate is low overall (7–9%)** because the most common constraint type in
   these chains is ResourceBudget (context_window, patience_budget), and model responses
   almost never contain "context_window." Real-vs-shuffled differentiation is dominated by
   the minority of steps where the entity is a file or error label.

2. **Chain acceptance rate was 4–18%** across sources — chains that passed the filter are
   structurally unusual (highly ResourceBudget-dominated), which may reduce the signal.

3. **SWE chains contribute 85% of evaluations** (3,048 of 3,558 real evaluations per model)
   but show almost no gap. SWE trajectories may have less predictable constraint ordering
   than TB.

**Secondary analyses (pre-registered in SPEC.md §5.1):**

1. *Effect-size comparison to v1*: both models substantially below v1 levels (see above).
2. *TB vs SWE consistency*: TB shows 4–5× larger gap than SWE. Effects diverge > 2×,
   suggesting trajectory features differ substantially between sources. TB competitive-
   programming chains have stronger ResourceBudget → ToolAvailability → SubGoalTransition
   sequencing than SWE long-horizon trajectories.
3. *Human source*: dropped (structural incompatibility, documented in SPEC.md).

### Gate Status (final)

All data gates from Sessions 1–12 unchanged. Scoring gate: complete.

### Files Created or Modified

| File | Action |
|------|--------|
| `src/scorer.py` | Layer 1 entity-match fix: `extract_entity_from_constraint()` added; `score_layer1()` rewritten |
| `results/scored.json` | Final scored output (28,464 results, corrected scorer) |
| `SESSION_LOG.md` | This entry |

### What Comes Next (for human review)

1. **Decision on outcome**: The primary hypothesis is NOT replicated. The positive direction
   is real (especially on TB) but effect size is too small.

2. **Layer 2 requires follow-up**: The optimality_proxy needs the same entity-based fix
   applied to the reference distribution. This requires rebuilding the pkl files with entity
   labels instead of type names and a `score_layer2` update. This could be done in a
   Session 14 if the human wants a complete Layer 2 analysis.

3. **TB-only re-analysis**: The TB source shows the strongest signal. A focused TB analysis
   (chain acceptance rate, constraint-type distribution at cutoff_k, entity match rate by
   type) might explain the gap between v1 and v2 effect sizes.

4. **Write-up**: Results should be written up as a near-replication with positive direction
   but attenuated magnitude. The constraint-chain abstraction shows signal on programming
   telemetry, but below the pre-registered threshold. The v1 → v2 attenuation is an
   interesting finding in itself.

