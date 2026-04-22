#!/usr/bin/env bash
# next_steps.sh — Project Ditto v2 local run guide
# Run this file as a reference; each section is a self-contained step.
# Execute commands manually (or uncomment and run with: bash scripts/next_steps.sh)
set -euo pipefail

PY=python3.11          # must be 3.11+ (translation.py uses A|B union syntax)
REPO=$(git rev-parse --show-toplevel)
cd "$REPO"

echo "=== Project Ditto v2 — Local Session Checklist ==="
echo "Working directory: $REPO"
echo ""

# ──────────────────────────────────────────────────────────────────────────────
# STEP 0 — Sanity checks
# ──────────────────────────────────────────────────────────────────────────────
echo "--- STEP 0: Sanity checks ---"

$PY --version || { echo "ERROR: python3.11 not found. Run: brew install python@3.11"; exit 1; }

$PY -c "from datasets import load_dataset" 2>/dev/null \
    || $PY -m pip install datasets -q

# Confirm HuggingFace is reachable
$PY -c "
import urllib.request
r = urllib.request.urlopen('https://huggingface.co', timeout=10)
print('HuggingFace: OK', r.status)
" || { echo "ERROR: HuggingFace not reachable. Check internet connection."; exit 1; }

echo "Prerequisites OK."
echo ""

# ──────────────────────────────────────────────────────────────────────────────
# STEP 1 — Pull latest from remote (has SPEC.md amendment)
# ──────────────────────────────────────────────────────────────────────────────
echo "--- STEP 1: Pull latest from remote ---"
git pull origin main
echo ""

# ──────────────────────────────────────────────────────────────────────────────
# STEP 2 — Scale SWE-bench (current: 500 traj / 121 chains → target: ~5000 traj / ~900 chains)
# ──────────────────────────────────────────────────────────────────────────────
echo "--- STEP 2: Scale SWE-bench trajectories ---"
echo "Current: $(wc -l < data/swe_bench_verified/trajectories.jsonl) trajectories, $(ls chains/real/swe/ | wc -l) real chains"

$PY scripts/acquire_swe.py \
    --source nebius/SWE-agent-trajectories \
    --target 5000 \
    --out data/swe_bench_verified/ \
    --gate-threshold 400

echo "Acquired. Rebuilding SWE chains..."
rm -f chains/real/swe/*.jsonl chains/shuffled/swe/*.jsonl

$PY scripts/build_chains.py \
    --source swe \
    --data data/swe_bench_verified/ \
    --out-real chains/real/swe/ \
    --out-shuffled chains/shuffled/swe/ \
    --gate3

echo "SWE chains: $(ls chains/real/swe/ | wc -l) real"
echo ""

# ──────────────────────────────────────────────────────────────────────────────
# STEP 3 — Scale Terminal-Bench (current: 890 traj / 61 chains → target: ~150+ chains)
# ──────────────────────────────────────────────────────────────────────────────
echo "--- STEP 3: Scale Terminal-Bench trajectories ---"
echo "Current: $(wc -l < data/terminal_bench/trajectories.jsonl) trajectories, $(ls chains/real/tb/ | wc -l) real chains"

# Try additional DCAgent datasets — skip quietly if they don't exist
for DS in \
    "DCAgent/claude-opus-4-terminal-bench-2" \
    "DCAgent/claude-haiku-terminal-bench-2" \
    "DCAgent/claude-sonnet-4-7-terminal-bench-2"; do

    SLUG=$(echo "$DS" | tr '/' '-')
    OUTDIR="data/tb_extra_${SLUG}"
    echo "  Trying $DS ..."
    $PY scripts/acquire_tb.py \
        --source "$DS" \
        --out "$OUTDIR/" \
        --target 500 \
        --gate-threshold 1 2>&1 \
        | tail -3 \
        || echo "  Skipped (not found or no usable trajectories)"
done

# Merge all TB trajectory files
mkdir -p data/terminal_bench_combined
cat data/terminal_bench/trajectories.jsonl \
    data/tb_extra_*/trajectories.jsonl 2>/dev/null \
    > data/terminal_bench_combined/trajectories.jsonl
echo "Combined TB trajectories: $(wc -l < data/terminal_bench_combined/trajectories.jsonl)"

rm -f chains/real/tb/*.jsonl chains/shuffled/tb/*.jsonl

$PY scripts/build_chains.py \
    --source tb \
    --data data/terminal_bench_combined/ \
    --out-real chains/real/tb/ \
    --out-shuffled chains/shuffled/tb/ \
    --gate3

echo "TB chains: $(ls chains/real/tb/ | wc -l) real"
echo ""

# ──────────────────────────────────────────────────────────────────────────────
# STEP 4 — Human sessions (Gate 2c, needs GITHUB_TOKEN)
# ──────────────────────────────────────────────────────────────────────────────
echo "--- STEP 4: Human session acquisition ---"

if [ -z "${GITHUB_TOKEN:-}" ]; then
    # Try gh CLI token as fallback
    export GITHUB_TOKEN=$(gh auth token 2>/dev/null || true)
fi

if [ -z "${GITHUB_TOKEN:-}" ]; then
    echo "WARNING: GITHUB_TOKEN not set. Skipping human sessions."
    echo "  To run: export GITHUB_TOKEN=\$(gh auth token) && bash scripts/next_steps.sh"
else
    echo "GITHUB_TOKEN found. Running human session acquisition..."
    $PY scripts/acquire_human.py \
        --target 200 \
        --out data/human_sessions/ \
        --start-month 2024-09 \
        --end-month 2026-04

    echo "Human trajectories: $(wc -l < data/human_sessions/trajectories.jsonl 2>/dev/null || echo 0)"

    rm -f chains/real/human/*.jsonl chains/shuffled/human/*.jsonl
    $PY scripts/build_chains.py \
        --source human \
        --data data/human_sessions/ \
        --out-real chains/real/human/ \
        --out-shuffled chains/shuffled/human/ \
        --gate3

    echo "Human chains: $(ls chains/real/human/ | wc -l) real"
fi
echo ""

# ──────────────────────────────────────────────────────────────────────────────
# STEP 5 — Push frozen tag
# ──────────────────────────────────────────────────────────────────────────────
echo "--- STEP 5: Push frozen tag ---"
git push origin T-code-v1.0-frozen 2>/dev/null \
    && echo "T-code-v1.0-frozen tag pushed." \
    || echo "Tag already pushed or push failed — check manually."
echo ""

# ──────────────────────────────────────────────────────────────────────────────
# STEP 6 — Commit and push everything
# ──────────────────────────────────────────────────────────────────────────────
echo "--- STEP 6: Commit and push ---"

SWE_CHAINS=$(ls chains/real/swe/ | wc -l | tr -d ' ')
TB_CHAINS=$(ls chains/real/tb/ | wc -l | tr -d ' ')
HUMAN_CHAINS=$(ls chains/real/human/ 2>/dev/null | wc -l | tr -d ' ')

git add \
    chains/real/swe/ chains/shuffled/swe/ \
    chains/real/tb/  chains/shuffled/tb/ \
    chains/real/human/ chains/shuffled/human/ \
    data/swe_bench_verified/trajectories.jsonl \
    data/terminal_bench_combined/ \
    data/human_sessions/trajectories.jsonl 2>/dev/null || true

git diff --cached --stat

git commit -m "Scale chains: SWE=${SWE_CHAINS}, TB=${TB_CHAINS}, human=${HUMAN_CHAINS}; all Gate 3 checks pass" \
    || echo "Nothing new to commit."

git push origin main
echo ""

# ──────────────────────────────────────────────────────────────────────────────
# STEP 7 — Final summary
# ──────────────────────────────────────────────────────────────────────────────
echo "=== SUMMARY ==="
echo "SWE real chains:   $(ls chains/real/swe/   | wc -l)  (target ≥400)"
echo "TB real chains:    $(ls chains/real/tb/    | wc -l)  (target ≥100)"
echo "Human real chains: $(ls chains/real/human/ 2>/dev/null | wc -l)  (target ≥20)"
echo ""
echo "Gate 3 targets:"
echo "  SWE   >= 400 chains? $([ $(ls chains/real/swe/ | wc -l) -ge 400 ] && echo PASS || echo FAIL)"
echo "  TB    >= 100 chains? $([ $(ls chains/real/tb/  | wc -l) -ge 100 ] && echo PASS || echo FAIL)"
echo "  Human >= 20 chains?  $([ $(ls chains/real/human/ 2>/dev/null | wc -l) -ge 20  ] && echo PASS || echo FAIL)"
echo ""
echo "Next session (Session 9): build reference distributions"
echo "  python3.11 -m src.reference build-raw --source swe --raw data/swe_bench_verified/ --out data/reference_swe.pkl"
echo "  python3.11 -m src.reference build-raw --source tb  --raw data/terminal_bench_combined/ --out data/reference_tb.pkl"
echo "  python3.11 -m src.reference build-raw --source human --raw data/human_sessions/ --out data/reference_human.pkl"
