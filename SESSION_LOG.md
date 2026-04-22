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
