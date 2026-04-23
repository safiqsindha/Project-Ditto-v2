"""
Supplementary Analysis 2: Stratified breakdowns of existing Layer 1 results.

Data sources (no new evaluations):
  - results/scored.json  → per_subset vectors (length/archetype/composition, pooled)
  - results/scored.json  → layer1_by_gt_constraint_type (model × source × type)
  - chains/real/         → chain metadata for cutoff-fraction distribution

Note: length/archetype/composition strata are pooled over TB+SWE (raw per-chain
responses were not committed to the repo).  Constraint-type and cutoff-fraction
strata are source-separated where data permits.

Writes supplementary/stratified_results.json.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

SCORED = Path("results/scored.json")
CHAINS_REAL_TB = Path("chains/real/tb")
CHAINS_REAL_SWE = Path("chains/real/swe")
OUT = Path("supplementary/stratified_results.json")

MODELS = ["haiku", "sonnet"]
SOURCES = ["tb", "swe"]
ALPHA = 0.05

CT_LABELS = [
    "ResourceBudget", "ToolAvailability", "InformationState",
    "SubGoalTransition", "CoordinationDependency", "OptimizationCriterion",
]

CUTOFF_BINS = [(0.3, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7)]


# ── helpers ─────────────────────────────────────────────────────────────────

def ci95_gap(real: list[int], shuf: list[int]) -> tuple[float, float]:
    """95% CI on the gap (real_rate - shuffled_rate) via normal approximation."""
    n1, n2 = len(real), len(shuf)
    if n1 == 0 or n2 == 0:
        return (float("nan"), float("nan"))
    p1 = sum(real) / n1
    p2 = sum(shuf) / n2
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    gap = p1 - p2
    z = 1.96
    return (round(gap - z * se, 4), round(gap + z * se, 4))


def summarise(real: list[int], shuf: list[int]) -> dict:
    if not real or not shuf:
        return {"n_real": len(real), "n_shuffled": len(shuf), "note": "insufficient data"}
    p1 = sum(real) / len(real)
    p2 = sum(shuf) / len(shuf)
    gap = p1 - p2
    lo, hi = ci95_gap(real, shuf)
    return {
        "n_real": len(real),
        "n_shuffled": len(shuf),
        "real_rate": round(p1, 4),
        "shuffled_rate": round(p2, 4),
        "gap": round(gap, 4),
        "ci95_gap": [lo, hi],
    }


# ── Stratum 1: length bucket (pooled over sources, from per_subset) ──────────

def length_strata(scored: dict) -> dict:
    """
    Extract length-bucket rates from per_subset binary vectors.
    These are pooled over TB+SWE (source-separated data requires results/raw/).
    """
    bins = ["short_20_25", "medium_26_32", "long_33_40"]
    out = {}
    for model in MODELS:
        ps = scored["per_subset"].get(model, {})
        out[model] = {}
        for b in bins:
            real = ps.get(f"length_bucket:{b}_real_l1", [])
            shuf = ps.get(f"length_bucket:{b}_shuffled_l1", [])
            out[model][b] = summarise(real, shuf)
    return out


# ── Stratum 2: constraint type at cutoff (model × source, from layer1_by_gt) ─

def constraint_type_strata(scored: dict) -> dict:
    """Source-separated constraint-type breakdown from layer1_by_gt_constraint_type."""
    raw = scored["layer1_by_gt_constraint_type"]
    out = {}
    for model in MODELS:
        out[model] = {}
        for source in SOURCES:
            out[model][source] = {}
            for ct in CT_LABELS:
                key = f"{model}::{source}::{ct}"
                cell = raw.get(key, {})
                if "error" in cell:
                    out[model][source][ct] = {"note": cell["error"]}
                else:
                    out[model][source][ct] = {
                        "n_real": cell.get("n_real", 0),
                        "n_shuffled": cell.get("n_shuffled", 0),
                        "real_rate": cell.get("real_rate", 0.0),
                        "shuffled_rate": cell.get("shuffled_rate", 0.0),
                        "gap": cell.get("gap", 0.0),
                        "p_value": cell.get("p_value", 1.0),
                        "significant": cell.get("significant_05", False),
                        # ci95 not directly available; approximate from z-stat
                        "ci95_gap": _approx_ci95(
                            cell.get("gap", 0),
                            cell.get("n_real", 0),
                            cell.get("n_shuffled", 0),
                            cell.get("real_rate", 0),
                            cell.get("shuffled_rate", 0),
                        ),
                    }
    return out


def _approx_ci95(gap, n1, n2, p1, p2):
    if n1 == 0 or n2 == 0:
        return [float("nan"), float("nan")]
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2) if p1 + p2 > 0 else 0
    return [round(gap - 1.96 * se, 4), round(gap + 1.96 * se, 4)]


# ── Stratum 3: cutoff position as fraction of chain length ───────────────────

def _load_chains(path: Path) -> list[dict]:
    chains = []
    for f in sorted(path.glob("*.jsonl")):
        try:
            line = f.read_text().strip().split("\n")[0]
            chains.append(json.loads(line))
        except Exception:
            pass
    return chains


def cutoff_fraction_strata(scored: dict) -> dict:
    """
    Distribution of chains across cutoff-fraction bins per source.
    Match rates require results/raw/ (unavailable); only chain counts reported.
    """
    out = {}
    for source, chains_dir in [("tb", CHAINS_REAL_TB), ("swe", CHAINS_REAL_SWE)]:
        chains = _load_chains(chains_dir)
        bin_counts: dict[str, int] = defaultdict(int)
        for c in chains:
            n = len(c.get("constraints", []))
            k = c.get("cutoff_k", 0)
            if n == 0:
                continue
            frac = k / n
            for lo, hi in CUTOFF_BINS:
                if lo <= frac < hi:
                    bin_counts[f"{lo:.1f}-{hi:.1f}"] = bin_counts[f"{lo:.1f}-{hi:.1f}"] + 1
                    break
        out[source] = {
            "n_chains": len(chains),
            "bin_counts": dict(bin_counts),
            "note": "match rates require results/raw/ (not committed); counts only",
        }
    return out


# ── Stratum 4: chain archetype (pooled, from per_subset) ─────────────────────

def archetype_strata(scored: dict) -> dict:
    """
    Chain archetype breakdown. Only 'stall' archetype is in per_subset;
    'aggressive' and 'setup' require results/raw/ for matched match rates.
    """
    out = {}
    for model in MODELS:
        ps = scored["per_subset"].get(model, {})
        # Only stall is stored in per_subset (aggressive and setup are rare in practice)
        real_stall = ps.get("archetype:stall_real_l1", [])
        shuf_stall = ps.get("archetype:stall_shuffled_l1", [])
        out[model] = {
            "stall": summarise(real_stall, shuf_stall),
            "note": "aggressive/setup archetypes have <1% prevalence and are not stored separately",
        }
    return out


# ── Composition (pooled, from per_subset) ────────────────────────────────────

def composition_strata(scored: dict) -> dict:
    bins = ["resource_dominated", "subgoal_dominated"]
    out = {}
    for model in MODELS:
        ps = scored["per_subset"].get(model, {})
        out[model] = {}
        for b in bins:
            real = ps.get(f"composition:{b}_real_l1", [])
            shuf = ps.get(f"composition:{b}_shuffled_l1", [])
            out[model][b] = summarise(real, shuf)
    return out


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    scored = json.loads(SCORED.read_text())

    results = {
        "stratum_length_bucket": length_strata(scored),
        "stratum_constraint_type": constraint_type_strata(scored),
        "stratum_cutoff_fraction": cutoff_fraction_strata(scored),
        "stratum_archetype": archetype_strata(scored),
        "stratum_composition": composition_strata(scored),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2))

    # ── print constraint-type table (most informative) ────────────────────
    print("=== Constraint-type stratification (Layer 1 gap by model × source × type) ===\n")
    ct_data = results["stratum_constraint_type"]
    print(f"{'Cell':<35} {'n_real':>7} {'real_rate':>10} {'shuf_rate':>10} "
          f"{'gap':>7} {'p':>7} {'sig':>5}")
    print("-" * 85)
    for model in MODELS:
        for source in SOURCES:
            for ct in CT_LABELS:
                d = ct_data[model][source].get(ct, {})
                if "note" in d and "n_real" not in d:
                    continue
                n = d.get("n_real", 0)
                if n == 0:
                    continue
                label = f"{model}::{source}::{ct}"
                print(f"{label:<35} {n:>7} {d.get('real_rate',0):>10.4f} "
                      f"{d.get('shuffled_rate',0):>10.4f} {d.get('gap',0):>7.4f} "
                      f"{d.get('p_value',1):>7.4f} {'*' if d.get('significant') else ' ':>5}")

    print("\n=== Length-bucket stratification (pooled TB+SWE) ===\n")
    lb_data = results["stratum_length_bucket"]
    print(f"{'Cell':<28} {'n_real':>7} {'real_rate':>10} {'shuf_rate':>10} "
          f"{'gap':>7} {'CI95 gap':>18}")
    print("-" * 82)
    for model in MODELS:
        for b in ["short_20_25", "medium_26_32", "long_33_40"]:
            d = lb_data[model].get(b, {})
            label = f"{model}::{b}"
            print(f"{label:<28} {d.get('n_real',0):>7} {d.get('real_rate',0):>10.4f} "
                  f"{d.get('shuffled_rate',0):>10.4f} {d.get('gap',0):>7.4f} "
                  f"[{d.get('ci95_gap',[0,0])[0]:>6.4f}, {d.get('ci95_gap',[0,0])[1]:>6.4f}]")

    print(f"\nOutput written to {OUT}")


if __name__ == "__main__":
    main()
