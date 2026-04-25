"""
Corrected scorer v2 — paired tests with original actionable filter rule.

Addresses the methodological issues in src/scorer.py while preserving the
original estimand for the actionable-subset Layer 1 analysis:

  Issue fixed (from scorer.py):
    1. Unpaired test for Layer 1: two-sample z-test → McNemar's test
    2. Unpaired test for Layer 2: Welch's t-test → paired t-test
    3. No (chain_id, eval_seed) alignment enforced → aligned pairs

  Filter rule (RESTORED to original scorer.py semantics):
    A pair enters the actionable Layer 1 analysis IFF:
      - real chain's constraint at cutoff_k is actionable, AND
      - shuffled chain's constraint at cutoff_k is actionable.
    Both conditions must hold. This matches src/scorer.py which filtered
    each condition independently by its own chain's constraint type.

  Issue NOT present in this version (present in scorer_corrected.py):
    scorer_corrected.py changed the actionable filter to require only that
    the REAL chain is actionable, inflating the actionable gap from ~0.066
    to 0.115 for haiku::tb. This inflation is documented in
    VERIFICATION_REPORT.md Check 3. This file restores the original filter.

  Bonferroni correction (preserved from scorer_corrected.py):
    Applied across the 4 primary cells (haiku::tb, haiku::swe,
    sonnet::tb, sonnet::swe) using layer1_actionable as primary metric.
    Corrected α = 0.05 / 4 = 0.0125.

Original src/scorer.py and src/scorer_corrected.py are NOT modified.
This file is additive; all three scorers coexist.

Usage:
    python -m src.scorer_corrected_v2 \\
        --results results/raw/ \\
        --dist-tb data/reference_tb.pkl \\
        --dist-swe data/reference_swe.pkl \\
        --chains-real chains/real/ \\
        --chains-shuffled chains/shuffled/ \\
        --out results/scored_corrected_v2.json
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

from src.normalize import normalize_action
from src.reference import ReferenceDistribution, extract_state_signature

# ---------------------------------------------------------------------------
# Re-use per-evaluation scoring helpers from original scorer (unchanged logic)
# ---------------------------------------------------------------------------

from src.scorer import (
    TOP_K,
    classify_chain,
    classify_outcome_tier,
    extract_entity_from_constraint,
    score_layer1,
    score_layer2,
)

ACTIONABLE_TYPES = {"ToolAvailability", "InformationState", "SubGoalTransition"}


# ---------------------------------------------------------------------------
# Statistical tests (identical to scorer_corrected.py)
# ---------------------------------------------------------------------------

def mcnemar_test(
    real_matches: list[int],
    shuffled_matches: list[int],
) -> dict[str, Any]:
    """
    McNemar's test for paired binary Layer 1 outcomes.

    Contingency table cells:
      b (n_10): real matched, shuffled did not  — "discordant real-match"
      c (n_01): shuffled matched, real did not  — "discordant shuffled-match"

    Uses continuity correction: statistic = (|b-c| - 1)^2 / (b+c)
    Gap is computed over all pairs (not just discordant), matching the
    match-rate-difference estimand used by the original scorer.
    """
    n = len(real_matches)
    if n == 0:
        return {"error": "empty sample"}
    if n != len(shuffled_matches):
        return {"error": "list length mismatch"}

    n11 = sum(r == 1 and s == 1 for r, s in zip(real_matches, shuffled_matches))
    b   = sum(r == 1 and s == 0 for r, s in zip(real_matches, shuffled_matches))
    c   = sum(r == 0 and s == 1 for r, s in zip(real_matches, shuffled_matches))
    n00 = sum(r == 0 and s == 0 for r, s in zip(real_matches, shuffled_matches))

    if b + c == 0:
        chi2_stat = 0.0
        p_value = 1.0
    else:
        chi2_stat = float((abs(b - c) - 1) ** 2) / float(b + c)
        p_value = float(1.0 - stats.chi2.cdf(chi2_stat, df=1))

    real_rate = sum(real_matches) / n
    shuf_rate = sum(shuffled_matches) / n

    return {
        "n_pairs": n,
        "n11_concordant_both_match": n11,
        "b_discordant_real_match": b,
        "c_discordant_shuffled_match": c,
        "n00_concordant_neither": n00,
        "real_rate": round(real_rate, 4),
        "shuffled_rate": round(shuf_rate, 4),
        "gap": round(real_rate - shuf_rate, 4),
        "chi2_stat": round(chi2_stat, 4),
        "p_value": round(p_value, 4),
        "significant_05": bool(p_value < 0.05),
        "test": "mcnemar_continuity_corrected",
    }


def paired_ttest(
    real_scores: list[float],
    shuffled_scores: list[float],
) -> dict[str, Any]:
    """Paired t-test (scipy.stats.ttest_rel) for Layer 2 coupled scores."""
    n = len(real_scores)
    if n < 2:
        return {"error": "insufficient data (need ≥2 pairs)"}
    if n != len(shuffled_scores):
        return {"error": "list length mismatch"}

    t, p = stats.ttest_rel(real_scores, shuffled_scores)
    diffs = [r - s for r, s in zip(real_scores, shuffled_scores)]

    return {
        "n_pairs": n,
        "real_mean": round(float(np.mean(real_scores)), 4),
        "shuffled_mean": round(float(np.mean(shuffled_scores)), 4),
        "gap": round(float(np.mean(real_scores)) - float(np.mean(shuffled_scores)), 4),
        "mean_diff": round(float(np.mean(diffs)), 4),
        "t_stat": round(float(t), 4),
        "p_value": round(float(p), 4),
        "significant_05": bool(p < 0.05),
        "test": "paired_ttest",
    }


def apply_bonferroni(p_value: float, n_tests: int) -> float:
    """Return Bonferroni-corrected p-value (clamped to [0, 1])."""
    return min(1.0, p_value * n_tests)


# ---------------------------------------------------------------------------
# Pair alignment helpers (identical to scorer_corrected.py)
# ---------------------------------------------------------------------------

def base_chain_id(chain_id: str) -> str:
    """Extract the base (real) chain_id from a possibly-shuffled chain_id."""
    if "_shuffled_" in chain_id:
        return chain_id.split("_shuffled_")[0]
    return chain_id


def shuffle_seed_from_chain_id(chain_id: str) -> int | None:
    """Return the shuffle seed embedded in a shuffled chain_id, or None."""
    if "_shuffled_" not in chain_id:
        return None
    try:
        return int(chain_id.split("_shuffled_")[1])
    except (IndexError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Main corrected-v2 scoring pipeline
# ---------------------------------------------------------------------------

def score_all_corrected_v2(
    results_dir: Path,
    dist_paths: dict[str, Path],
    chains_real_dir: Path,
    chains_shuffled_dir: Path,
) -> dict[str, Any]:
    """
    Load all raw results, build aligned pairs, and compute corrected-v2 statistics.

    Key difference from score_all_corrected() in scorer_corrected.py:
    The actionable Layer 1 subset requires BOTH real and shuffled chains to have
    an actionable constraint type at cutoff_k. This restores the original
    scorer.py estimand while using paired statistical tests.

    Alignment key: (base_chain_id, model, eval_seed)
    """
    # --- Reference distributions ---
    ref_dists: dict[str, ReferenceDistribution] = {}
    for src, path in dist_paths.items():
        ref_dists[src] = ReferenceDistribution.load(path)

    # --- Load raw results ---
    all_results: list[dict] = []
    for rfile in sorted(results_dir.glob("**/*.json")):
        with open(rfile) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                continue
        if not isinstance(data, dict) or "chain_id" not in data:
            continue
        all_results.append(data)

    print(f"Loaded {len(all_results)} raw results")

    # --- Index chains ---
    chain_index: dict[str, dict] = {}
    for cfile in chains_real_dir.glob("**/*.jsonl"):
        with open(cfile) as f:
            chain = json.loads(f.readline())
            chain_index[chain["chain_id"]] = chain
    for cfile in chains_shuffled_dir.glob("**/*.jsonl"):
        with open(cfile) as f:
            chain = json.loads(f.readline())
            chain_index[chain["chain_id"]] = chain

    # --- Per-evaluation scoring ---
    eval_key = lambda r: (r.get("model", "?"), r.get("seed", 0))

    scored_by_chain: dict[str, dict] = defaultdict(dict)
    skipped_no_chain = 0

    for r in all_results:
        cid = r.get("chain_id", "")
        chain = chain_index.get(cid, {})
        if not chain:
            skipped_no_chain += 1
            continue

        model = r.get("model", "unknown")
        seed = r.get("seed", 0)
        source = r.get("source", chain.get("source", "")) or "unknown"
        temperature = r.get("temperature", 0.0)
        model_action = r.get("response", "").strip()
        cutoff_k = r.get("cutoff_k", 15)

        dist: dict[str, float] = {}
        ref_dist = ref_dists.get(source) or (
            next(iter(ref_dists.values())) if ref_dists else None
        )
        if ref_dist is not None:
            try:
                sig = extract_state_signature(chain, cutoff_k)
                if sig is not None:
                    _, dist, _ = ref_dist.lookup(sig)
            except (KeyError, AttributeError, TypeError):
                pass

        l1 = score_layer1(model_action, chain, cutoff_k)
        l2 = score_layer2(model_action, chain, cutoff_k, dist)

        gt_type = l1.get("constraint_type", "") or ""
        is_actionable = gt_type in ACTIONABLE_TYPES

        key = (model, seed)
        scored_by_chain[cid][key] = {
            "l1": l1.get("top_k_match"),
            "l1_is_actionable": is_actionable,
            "gt_type": gt_type,
            "l2": l2.get("coupled", 0.0),
            "source": source,
            "temperature": temperature,
            "model": model,
            "seed": seed,
        }

    if skipped_no_chain:
        print(f"[scorer_corrected_v2] WARN: skipped {skipped_no_chain} results with no chain")

    # --- Build aligned pairs ---
    all_chain_ids = set(scored_by_chain.keys())
    real_chain_ids = {cid for cid in all_chain_ids if "_shuffled_" not in cid}
    shuffled_chain_ids = {cid for cid in all_chain_ids if "_shuffled_" in cid}

    shuffled_by_base: dict[str, list[str]] = defaultdict(list)
    for cid in shuffled_chain_ids:
        shuffled_by_base[base_chain_id(cid)].append(cid)

    @dataclass
    class Pair:
        base_cid: str
        model: str
        eval_seed: int
        shuffle_seed: int
        source: str
        temperature: float
        real_l1: int | None
        real_l1_actionable: bool
        real_gt_type: str
        real_l2: float
        shuffled_l1: int | None
        shuffled_l1_actionable: bool
        shuffled_gt_type: str
        shuffled_l2: float

    pairs: list[Pair] = []
    n_excluded_no_real = 0
    n_excluded_no_shuffled = 0

    for base_cid in sorted(real_chain_ids):
        real_scored = scored_by_chain.get(base_cid, {})
        shuf_cids = shuffled_by_base.get(base_cid, [])

        real_eval_keys = set(real_scored.keys())

        for shuf_cid in shuf_cids:
            shuf_scored = scored_by_chain.get(shuf_cid, {})
            sh_seed = shuffle_seed_from_chain_id(shuf_cid)

            all_eval_keys = real_eval_keys | set(shuf_scored.keys())
            for ek in sorted(all_eval_keys):
                real_entry = real_scored.get(ek)
                shuf_entry = shuf_scored.get(ek)

                if real_entry is None:
                    n_excluded_no_real += 1
                    continue
                if shuf_entry is None:
                    n_excluded_no_shuffled += 1
                    continue

                pairs.append(Pair(
                    base_cid=base_cid,
                    model=ek[0],
                    eval_seed=ek[1],
                    shuffle_seed=sh_seed,
                    source=real_entry["source"],
                    temperature=real_entry["temperature"],
                    real_l1=real_entry["l1"],
                    real_l1_actionable=real_entry["l1_is_actionable"],
                    real_gt_type=real_entry["gt_type"],
                    real_l2=real_entry["l2"],
                    shuffled_l1=shuf_entry["l1"],
                    shuffled_l1_actionable=shuf_entry["l1_is_actionable"],
                    shuffled_gt_type=shuf_entry["gt_type"],
                    shuffled_l2=shuf_entry["l2"],
                ))

    no_shuffled_bases = len(real_chain_ids - set(shuffled_by_base.keys()))

    print(f"Built {len(pairs)} pairs from {len(real_chain_ids)} real chains")
    print(f"Excluded: {n_excluded_no_real} (missing real eval), "
          f"{n_excluded_no_shuffled} (missing shuffled eval), "
          f"{no_shuffled_bases} base chains had no shuffled variants")

    # --- Bucket structure ---
    def _new_bucket() -> dict[str, list]:
        return {
            "real_l1": [], "shuf_l1": [],
            "real_l1_act": [], "shuf_l1_act": [],
            "real_l2": [], "shuf_l2": [],
        }

    per_model: dict[str, dict[str, list]] = defaultdict(_new_bucket)
    per_model_per_source: dict[tuple, dict[str, list]] = defaultdict(_new_bucket)
    per_model_per_config: dict[tuple, dict[str, list]] = defaultdict(_new_bucket)
    per_model_per_config_per_source: dict[tuple, dict[str, list]] = defaultdict(_new_bucket)
    per_gt_type: dict[tuple, dict[str, list]] = defaultdict(
        lambda: {"real": [], "shuf": []}
    )

    for p in pairs:
        model = p.model
        src = p.source
        config_key = f"T{p.temperature}_seed{p.eval_seed}"

        # Layer 1 (all cutoffs)
        if p.real_l1 is not None and p.shuffled_l1 is not None:
            for bkt in [
                per_model[model],
                per_model_per_source[(model, src)],
                per_model_per_config[(model, config_key)],
                per_model_per_config_per_source[(model, config_key, src)],
            ]:
                bkt["real_l1"].append(p.real_l1)
                bkt["shuf_l1"].append(p.shuffled_l1)

            if p.real_gt_type:
                per_gt_type[(model, src, p.real_gt_type)]["real"].append(p.real_l1)
                per_gt_type[(model, src, p.real_gt_type)]["shuf"].append(p.shuffled_l1)

            # Actionable-only Layer 1 — ORIGINAL FILTER RULE (restored):
            # Both real AND shuffled chains must have an actionable constraint
            # type at cutoff_k. Mirrors src/scorer.py which applied the
            # actionability check independently per condition.
            if p.real_l1_actionable and p.shuffled_l1_actionable:
                for bkt in [
                    per_model[model],
                    per_model_per_source[(model, src)],
                    per_model_per_config[(model, config_key)],
                    per_model_per_config_per_source[(model, config_key, src)],
                ]:
                    bkt["real_l1_act"].append(p.real_l1)
                    bkt["shuf_l1_act"].append(p.shuffled_l1)

        # Layer 2 (always defined)
        for bkt in [
            per_model[model],
            per_model_per_source[(model, src)],
            per_model_per_config[(model, config_key)],
            per_model_per_config_per_source[(model, config_key, src)],
        ]:
            bkt["real_l2"].append(p.real_l2)
            bkt["shuf_l2"].append(p.shuffled_l2)

    # --- Summarise each bucket ---
    def _summarise(bucket: dict[str, list]) -> dict[str, Any]:
        l1  = mcnemar_test(bucket["real_l1"], bucket["shuf_l1"])
        l1a = mcnemar_test(bucket["real_l1_act"], bucket["shuf_l1_act"])
        l2  = paired_ttest(bucket["real_l2"], bucket["shuf_l2"])
        gap  = l1a.get("gap", 0.0) if "error" not in l1a else 0.0
        pval = l1a.get("p_value", 1.0) if "error" not in l1a else 1.0
        return {
            "layer1": l1,
            "layer1_actionable": l1a,
            "layer2": l2,
            "outcome_tier_uncorrected": classify_outcome_tier(gap, pval),
        }

    model_stats        = {m: _summarise(b) for m, b in per_model.items()}
    source_stats       = {f"{m}::{s}": _summarise(b) for (m, s), b in per_model_per_source.items()}
    config_stats       = {f"{m}::{c}": _summarise(b) for (m, c), b in per_model_per_config.items()}
    config_source_stats = {
        f"{m}::{c}::{s}": _summarise(b)
        for (m, c, s), b in per_model_per_config_per_source.items()
    }

    gt_type_stats: dict[str, Any] = {}
    for (model_name, src, gt_type), data in per_gt_type.items():
        test = mcnemar_test(data["real"], data["shuf"])
        gt_type_stats[f"{model_name}::{src}::{gt_type}"] = test

    # --- Bonferroni correction across 4 primary cells ---
    PRIMARY_CELLS = ["haiku::tb", "haiku::swe", "sonnet::tb", "sonnet::swe"]
    N_PRIMARY = len(PRIMARY_CELLS)

    primary_p_values: dict[str, float] = {}
    for cell_key in PRIMARY_CELLS:
        cell_stats = source_stats.get(cell_key, {})
        l1a = cell_stats.get("layer1_actionable", {})
        primary_p_values[cell_key] = l1a.get("p_value", 1.0)

    bonferroni_primary: dict[str, Any] = {}
    for cell_key in PRIMARY_CELLS:
        raw_p  = primary_p_values[cell_key]
        corr_p = apply_bonferroni(raw_p, N_PRIMARY)
        cell_stats = source_stats.get(cell_key, {})
        l1a = cell_stats.get("layer1_actionable", {})
        gap = l1a.get("gap", float("nan"))
        bonferroni_primary[cell_key] = {
            "gap": gap,
            "uncorrected_p": round(raw_p, 4),
            "bonferroni_corrected_p": round(corr_p, 4),
            "n_primary_tests": N_PRIMARY,
            "meets_preregistered_threshold": bool(gap >= 0.05 and corr_p < 0.05),
            "meets_uncorrected_threshold": bool(gap >= 0.05 and raw_p < 0.05),
        }

    # Full breakdown Bonferroni
    all_cell_keys = (
        list(model_stats.keys())
        + list(source_stats.keys())
        + list(config_stats.keys())
        + list(config_source_stats.keys())
    )
    N_FULL = len(all_cell_keys)

    full_p_values: dict[str, float] = {}
    for d, key_prefix in [
        (model_stats, "model::"),
        (source_stats, "src::"),
        (config_stats, "cfg::"),
        (config_source_stats, "cfg_src::"),
    ]:
        for k, v in d.items():
            l1a = v.get("layer1_actionable", {})
            full_p_values[key_prefix + k] = l1a.get("p_value", 1.0)

    bonferroni_full_summary: dict[str, Any] = {}
    for fk, fp in full_p_values.items():
        bonferroni_full_summary[fk] = {
            "uncorrected_p": round(fp, 4),
            "bonferroni_corrected_p": round(apply_bonferroni(fp, N_FULL), 4),
            "n_full_tests": N_FULL,
        }

    preregistered_min_met = any(
        v["meets_preregistered_threshold"] for v in bonferroni_primary.values()
    )
    preregistered_min_met_uncorrected = any(
        v["meets_uncorrected_threshold"] for v in bonferroni_primary.values()
    )

    # Add Bonferroni-adjusted outcome tier for primary cells
    for cell_key in PRIMARY_CELLS:
        if cell_key in source_stats:
            l1a = source_stats[cell_key].get("layer1_actionable", {})
            gap    = l1a.get("gap", 0.0) if "error" not in l1a else 0.0
            corr_p = bonferroni_primary.get(cell_key, {}).get("bonferroni_corrected_p", 1.0)
            source_stats[cell_key]["outcome_tier_bonferroni"] = classify_outcome_tier(gap, corr_p)

    return {
        "scorer_version": "corrected_v2",
        "filter_rule": "both_real_and_shuffled_actionable",
        "test_layer1": "mcnemar_continuity_corrected",
        "test_layer2": "paired_ttest",
        "n_results": len(all_results),
        "n_pairs_built": len(pairs),
        "n_real_chains": len(real_chain_ids),
        "n_excluded_no_real_eval": n_excluded_no_real,
        "n_excluded_no_shuffled_eval": n_excluded_no_shuffled,
        "n_base_chains_no_shuffled_variant": no_shuffled_bases,
        "correction_method": "bonferroni",
        "n_primary_cells": N_PRIMARY,
        "n_full_breakdown_cells": N_FULL,
        "preregistered_min_criterion_met_bonferroni": preregistered_min_met,
        "preregistered_min_criterion_met_uncorrected": preregistered_min_met_uncorrected,
        "per_model": model_stats,
        "per_model_per_source": source_stats,
        "per_model_per_config": config_stats,
        "per_model_per_config_per_source": config_source_stats,
        "layer1_by_gt_constraint_type": gt_type_stats,
        "bonferroni_primary_4_cells": bonferroni_primary,
        "bonferroni_full_breakdown": bonferroni_full_summary,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Corrected scorer v2 (paired tests + original actionable filter)"
    )
    parser.add_argument("--results",         type=Path, default=Path("results/raw"))
    parser.add_argument("--dist-tb",         type=Path, default=None)
    parser.add_argument("--dist-swe",        type=Path, default=None)
    parser.add_argument("--dist-human",      type=Path, default=None)
    parser.add_argument("--chains-real",     type=Path, default=Path("chains/real"))
    parser.add_argument("--chains-shuffled", type=Path, default=Path("chains/shuffled"))
    parser.add_argument("--out",             type=Path, default=Path("results/scored_corrected_v2.json"))
    args = parser.parse_args()

    dist_paths: dict[str, Path] = {}
    if args.dist_tb:
        dist_paths["tb"] = args.dist_tb
    if args.dist_swe:
        dist_paths["swe"] = args.dist_swe
    if args.dist_human:
        dist_paths["human"] = args.dist_human
    if not dist_paths:
        parser.error("At least one of --dist-tb, --dist-swe, --dist-human is required")

    scored = score_all_corrected_v2(
        args.results, dist_paths, args.chains_real, args.chains_shuffled
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(scored, f, indent=2)

    print(f"\nResults written to {args.out}")

    # Validation check: haiku::tb actionable gap should be ≈ 0.066
    haikutb = scored.get("per_model_per_source", {}).get("haiku::tb", {})
    l1a = haikutb.get("layer1_actionable", {})
    observed_gap = l1a.get("gap", float("nan"))
    print(f"\n[VALIDATION] haiku::tb actionable gap = {observed_gap:.4f} (expected ≈ 0.066)")
    if not math.isnan(observed_gap) and not (0.055 <= observed_gap <= 0.075):
        print("WARNING: gap outside expected range [0.055, 0.075] — investigate filter rule")

    # Summary table
    print("\n=== Corrected-v2 scoring — primary 4 cells (layer1_actionable, McNemar) ===")
    print(f"  Filter rule: BOTH real AND shuffled chains must be actionable at cutoff_k")
    print(f"{'Cell':20s}  {'n_pairs':>7}  {'gap':>7}  {'uncorr_p':>9}  {'bonf_p(×4)':>11}  {'gap≥0.05 & bonf<0.05':>22}")
    for cell in scored["bonferroni_primary_4_cells"]:
        v   = scored["bonferroni_primary_4_cells"][cell]
        src = scored["per_model_per_source"].get(cell, {})
        l1a = src.get("layer1_actionable", {})
        n   = l1a.get("n_pairs", "?")
        print(
            f"  {cell:20s}  {str(n):>7}  {v['gap']:>7.4f}  {v['uncorrected_p']:>9.4f}"
            f"  {v['bonferroni_corrected_p']:>11.4f}  {str(v['meets_preregistered_threshold']):>22}"
        )

    print(f"\nPre-registered minimum (gap≥0.05, Bonferroni p<0.05): "
          f"{'MET' if scored['preregistered_min_criterion_met_bonferroni'] else 'NOT MET'}")
    print(f"Pre-registered minimum (gap≥0.05, uncorrected p<0.05): "
          f"{'MET' if scored['preregistered_min_criterion_met_uncorrected'] else 'NOT MET'}")

    print("\n=== Layer 2 (paired t-test) — per model × source ===")
    for label in ["haiku::tb", "haiku::swe", "sonnet::tb", "sonnet::swe"]:
        s  = scored["per_model_per_source"].get(label, {})
        l2 = s.get("layer2", {})
        print(f"  {label:20s}  gap={l2.get('gap','N/A'):>7}  t={l2.get('t_stat','N/A'):>7}  "
              f"p={l2.get('p_value','N/A'):>7}  n_pairs={l2.get('n_pairs','N/A')}")
