"""
Session 7: Scorer — blinded evaluation of model responses.

Runs in a separate context with no knowledge of model identity, real/shuffled
label, or seed. Computes Layer 1, Layer 2, and Layer 3 metrics.

Usage:
    python -m src.scorer \
        --results results/raw/ \
        --dist data/reference_dist.pkl \
        --chains-real chains/real/ \
        --chains-shuffled chains/shuffled/ \
        --out results/scored.json
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

from src.normalize import normalize_action
from src.reference import ReferenceDistribution, extract_state_signature


# ---------------------------------------------------------------------------
# Entity extraction (for Layer 1 entity-match scoring)
# ---------------------------------------------------------------------------
# The reference distribution was built with constraint TYPE names as actions,
# but the model was prompted to output rendered entity labels (e.g. "use file_B").
# This mismatch causes a 0.0 match rate with the original type-name lookup.
# The fix: extract the key entity from the ground-truth constraint at cutoff_k
# and check whether the model's response CONTAINS that entity.

def extract_entity_from_constraint(constraint: dict) -> str | None:
    """Return the key abstract entity label for a constraint dict."""
    ctype = constraint.get("type", "")
    if ctype == "ToolAvailability":
        tool = constraint.get("tool", "")
        return tool.lower() if tool else None
    elif ctype == "InformationState":
        obs = constraint.get("observable_added", [])
        return obs[0].lower() if obs else None
    elif ctype == "SubGoalTransition":
        return constraint.get("to_phase", "").lower()
    elif ctype == "ResourceBudget":
        return constraint.get("resource", "").lower()
    elif ctype == "CoordinationDependency":
        dep = constraint.get("dependency", "")
        return dep.lower() if dep else None
    elif ctype == "OptimizationCriterion":
        obj = constraint.get("objective", "")
        return obj.lower() if obj else None
    return None


# ---------------------------------------------------------------------------
# Layer 1: Objective action-match rate
# ---------------------------------------------------------------------------

TOP_K = 3  # top-3 match rate (spec §7.1)


def score_layer1(
    model_action: str,
    chain: dict,
    cutoff_k: int,
) -> dict[str, Any]:
    """
    Compute entity-match Layer 1 score for one evaluation.

    Extracts the key entity from the ground-truth constraint at cutoff_k
    (the step the model was asked to predict) and checks whether the model's
    response contains that entity label as a substring.

    Returns {"top_k_match": 0|1, "entity": str, "constraint_type": str}
    """
    constraints = chain.get("constraints", [])
    if cutoff_k >= len(constraints):
        return {"top_k_match": None, "entity": None, "constraint_type": None}

    gt_constraint = constraints[cutoff_k]
    entity = extract_entity_from_constraint(gt_constraint)
    constraint_type = gt_constraint.get("type", "")

    if entity is None:
        return {"top_k_match": None, "entity": None, "constraint_type": constraint_type}

    norm_response = normalize_action(model_action)
    norm_entity = normalize_action(entity)
    top_k_match = 1 if (norm_entity and norm_entity in norm_response) else 0

    return {
        "top_k_match": top_k_match,
        "entity": entity,
        "constraint_type": constraint_type,
    }


# ---------------------------------------------------------------------------
# Layer 2: Legality × optimality
# ---------------------------------------------------------------------------

def score_layer2(
    model_action: str,
    chain: dict,
    cutoff_k: int,
    reference_dist: dict[str, float],
) -> dict[str, float]:
    """
    Compute legality × optimality coupled metric using entity-based scoring.

    Legality: did the model propose an action that is permitted by active
    constraints at step K? Mentioning an unavailable tool is illegal (legality = 0).

    Optimality proxy: among legal entities in the reference distribution
    at this state, what fraction of probability mass does the model's response
    cover (via substring containment of any entity label)?

    The reference distribution is entity-keyed (e.g. {"file_a": 0.4, "command_3": 0.6}),
    matching the model's rendered output format.

    Returns {"legality": float, "optimality_proxy": float, "coupled": float}
    """
    constraints = chain.get("constraints", [])[:cutoff_k]

    # Determine which units are currently unavailable
    unavailable_units: set[str] = set()
    for c in constraints:
        if c.get("type") == "ToolAvailability":
            tool = c.get("tool", "").lower()
            state = c.get("state", "")
            if state == "unavailable":
                unavailable_units.add(tool)
            elif state == "available":
                unavailable_units.discard(tool)

    # Legality: model_action must not mention an unavailable unit
    norm_action = normalize_action(model_action)
    legality = 1.0
    for unit in unavailable_units:
        if unit and normalize_action(unit) in norm_action:
            legality = 0.0
            break

    # Optimality: filter reference dist to legal entities, then sum mass of
    # entities the response covers (substring match — same logic as Layer 1).
    legal_dist = {
        entity: p for entity, p in reference_dist.items()
        if entity and not any(u and u in entity.lower() for u in unavailable_units)
    }
    total_legal_mass = sum(legal_dist.values())

    if total_legal_mass > 0:
        captured_mass = sum(
            p for entity, p in legal_dist.items()
            if normalize_action(entity) in norm_action
        )
        optimality_proxy = captured_mass / total_legal_mass
    else:
        optimality_proxy = 0.0

    coupled = legality * optimality_proxy

    return {
        "legality": legality,
        "optimality_proxy": round(optimality_proxy, 4),
        "coupled": round(coupled, 4),
    }


# ---------------------------------------------------------------------------
# Statistical tests
# ---------------------------------------------------------------------------

def two_sample_proportion_test(
    real_matches: list[int],
    shuffled_matches: list[int],
) -> dict[str, float]:
    """
    Two-sample proportion test (z-test) for Layer 1 top-k match rates.

    Parameters
    ----------
    real_matches     : list of 0/1 top-k match outcomes for real chains
    shuffled_matches : list of 0/1 top-k match outcomes for shuffled chains

    Returns {"real_rate", "shuffled_rate", "gap", "z_stat", "p_value", "significant_05"}
    """
    n1, n2 = len(real_matches), len(shuffled_matches)
    if n1 == 0 or n2 == 0:
        return {"error": "empty sample"}

    p1 = sum(real_matches) / n1
    p2 = sum(shuffled_matches) / n2
    gap = p1 - p2

    # Pooled proportion
    p_pool = (sum(real_matches) + sum(shuffled_matches)) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    z = gap / se if se > 0 else 0.0

    p_value = 2 * (1 - stats.norm.cdf(abs(z)))

    return {
        "real_rate": round(p1, 4),
        "shuffled_rate": round(p2, 4),
        "gap": round(gap, 4),
        "z_stat": round(z, 4),
        "p_value": round(p_value, 4),
        "significant_05": bool(p_value < 0.05),
        "n_real": n1,
        "n_shuffled": n2,
    }


def welch_ttest(real_scores: list[float], shuffled_scores: list[float]) -> dict[str, float]:
    """Welch's t-test for Layer 2 coupled metric."""
    if len(real_scores) < 2 or len(shuffled_scores) < 2:
        return {"error": "insufficient data"}
    t, p = stats.ttest_ind(real_scores, shuffled_scores, equal_var=False)
    ci_real = stats.t.interval(0.95, len(real_scores) - 1,
                               loc=np.mean(real_scores), scale=stats.sem(real_scores))
    return {
        "real_mean": round(float(np.mean(real_scores)), 4),
        "shuffled_mean": round(float(np.mean(shuffled_scores)), 4),
        "gap": round(float(np.mean(real_scores)) - float(np.mean(shuffled_scores)), 4),
        "t_stat": round(float(t), 4),
        "p_value": round(float(p), 4),
        "significant_05": bool(p < 0.05),
        "ci_real_95": (round(float(ci_real[0]), 4), round(float(ci_real[1]), 4)),
    }


# ---------------------------------------------------------------------------
# Layer 3: Subset breakdown
# ---------------------------------------------------------------------------

def classify_chain(chain: dict) -> dict[str, str]:
    """Classify a chain into Layer 3 subsets."""
    constraints = chain.get("constraints", [])
    n = len(constraints)

    # Length bucket
    if n <= 25:
        length_bucket = "short_20_25"
    elif n <= 32:
        length_bucket = "medium_26_32"
    else:
        length_bucket = "long_33_40"

    # Constraint-type composition
    n_resource = sum(1 for c in constraints if c.get("type") == "ResourceBudget")
    n_subgoal = sum(1 for c in constraints if c.get("type") == "SubGoalTransition")
    if n_resource > n_subgoal:
        composition = "resource_dominated"
    elif n_subgoal > n_resource:
        composition = "subgoal_dominated"
    else:
        composition = "balanced"

    # Archetype heuristic
    n_faint_tool = sum(
        1 for c in constraints
        if c.get("type") == "ToolAvailability" and c.get("state") == "unavailable" and c.get("recover_in") is None
    )
    n_boost = sum(
        1 for c in constraints
        if c.get("type") == "ResourceBudget" and "boost" in c.get("resource", "")
    )
    if n_faint_tool >= 4:
        archetype = "aggressive"
    elif n_boost >= 3:
        archetype = "setup"
    else:
        archetype = "stall"

    return {
        "length_bucket": length_bucket,
        "composition": composition,
        "archetype": archetype,
    }


# ---------------------------------------------------------------------------
# Outcome tier classification
# ---------------------------------------------------------------------------

def classify_outcome_tier(gap: float, p_value: float) -> str:
    """Classify the Layer 1 result into an outcome tier (§7.4)."""
    if gap < -0.01:
        return "reversed"
    if abs(gap) < 0.02 and p_value > 0.1:
        return "null"
    if gap >= 0.08 and p_value < 0.01:
        return "strong_positive"
    if gap >= 0.05 and p_value < 0.05:
        return "moderate_positive"
    return "weak_mixed"


# ---------------------------------------------------------------------------
# Main scoring pipeline
# ---------------------------------------------------------------------------

def score_all(
    results_dir: Path,
    dist_paths: dict[str, Path],
    chains_real_dir: Path,
    chains_shuffled_dir: Path,
) -> dict[str, Any]:
    """
    Load all raw results and compute Layer 1, 2, 3 metrics.

    Parameters
    ----------
    results_dir    : root directory for raw results (searched recursively)
    dist_paths     : {source: path} mapping to source-specific reference
                     distribution pickle files, e.g. {"tb": ..., "swe": ...}
    chains_real_dir: root of real chain files (searched recursively)
    chains_shuffled_dir: root of shuffled chain files (searched recursively)

    Returns a comprehensive results dict suitable for JSON serialisation.
    """
    # Load reference distributions (one per source)
    ref_dists: dict[str, ReferenceDistribution] = {}
    for src, path in dist_paths.items():
        ref_dists[src] = ReferenceDistribution.load(path)

    # Load all raw results (recursive search; skip non-result files like manifests)
    results: list[dict] = []
    for rfile in sorted(results_dir.glob("**/*.json")):
        with open(rfile) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                continue
        if not isinstance(data, dict) or "chain_id" not in data:
            continue
        results.append(data)

    print(f"Loaded {len(results)} raw results")

    # Index chains for fast lookup
    chain_index: dict[str, dict] = {}
    for cfile in chains_real_dir.glob("**/*.jsonl"):
        with open(cfile) as f:
            chain = json.loads(f.readline())
            chain_index[chain["chain_id"]] = chain
    for cfile in chains_shuffled_dir.glob("**/*.jsonl"):
        with open(cfile) as f:
            chain = json.loads(f.readline())
            chain_index[chain["chain_id"]] = chain

    # The prompt asks the model to propose an "action label" (e.g. "use command_2"),
    # so Layer 1 entity-match is only well-defined when the ground-truth constraint
    # at cutoff_k corresponds to an agent-action event. ResourceBudget,
    # CoordinationDependency, and OptimizationCriterion are passive observations
    # the model cannot meaningfully predict in action format.
    ACTIONABLE_TYPES = {"ToolAvailability", "InformationState", "SubGoalTransition"}

    # Buckets for breakdowns. Each bucket maps a key → {real_l1, shuffled_l1,
    # real_l1_actionable, shuffled_l1_actionable, real_l2, shuffled_l2}
    def _new_bucket() -> dict[str, list]:
        return {
            "real_l1": [], "shuffled_l1": [],
            "real_l1_actionable": [], "shuffled_l1_actionable": [],
            "real_l2": [], "shuffled_l2": [],
        }

    per_model: dict[str, dict[str, list]] = defaultdict(_new_bucket)
    per_model_per_source: dict[tuple[str, str], dict[str, list]] = defaultdict(_new_bucket)
    per_model_per_config: dict[tuple[str, str], dict[str, list]] = defaultdict(_new_bucket)
    per_model_per_config_per_source: dict[tuple[str, str, str], dict[str, list]] = defaultdict(_new_bucket)

    # Stratified Layer 1 by ground-truth constraint type (per model × source)
    per_gt_type: dict[tuple[str, str, str], dict[str, list]] = defaultdict(
        lambda: {"real": [], "shuffled": []}
    )

    per_subset: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    skipped_no_chain = 0

    for r in results:
        chain_id = r.get("chain_id", "")
        model = r.get("model", "unknown")
        seed = r.get("seed", 0)
        temperature = r.get("temperature", 0.0)
        is_real = "_shuffled_" not in chain_id
        condition = "real" if is_real else "shuffled"
        model_action = r.get("response", "").strip()
        cutoff_k = r.get("cutoff_k", 15)

        chain = chain_index.get(chain_id, {})
        if not chain:
            skipped_no_chain += 1
            continue

        # Reference distribution for Layer 2 (source-specific)
        dist: dict[str, float] = {}
        chain_source = r.get("source", chain.get("source", "")) or "unknown"
        ref_dist = ref_dists.get(chain_source) or (next(iter(ref_dists.values())) if ref_dists else None)
        if ref_dist is not None:
            try:
                sig = extract_state_signature(chain, cutoff_k)
                if sig is not None:
                    _top_k, dist, _backoff = ref_dist.lookup(sig)
            except (KeyError, AttributeError, TypeError) as exc:
                print(f"[scorer] lookup failed for chain_id={chain_id}: {exc}")

        l1 = score_layer1(model_action, chain, cutoff_k)
        l2 = score_layer2(model_action, chain, cutoff_k, dist)

        # Config key — distinguishes T=0 primary from T=0.5 variance-study seeds
        config_key = f"T{temperature}_seed{seed}"

        gt_type = l1.get("constraint_type", "")
        is_actionable = gt_type in ACTIONABLE_TYPES

        # Bucket all four breakdowns
        if l1["top_k_match"] is not None:
            match = l1["top_k_match"]
            per_model[model][f"{condition}_l1"].append(match)
            per_model_per_source[(model, chain_source)][f"{condition}_l1"].append(match)
            per_model_per_config[(model, config_key)][f"{condition}_l1"].append(match)
            per_model_per_config_per_source[(model, config_key, chain_source)][f"{condition}_l1"].append(match)

            # Stratified by ground-truth constraint type
            if gt_type:
                per_gt_type[(model, chain_source, gt_type)][condition].append(match)

            # Actionable-only Layer 1 (excludes ResourceBudget / Coord / Opt cutoffs
            # which are passive observations the model cannot predict in action format)
            if is_actionable:
                per_model[model][f"{condition}_l1_actionable"].append(match)
                per_model_per_source[(model, chain_source)][f"{condition}_l1_actionable"].append(match)
                per_model_per_config[(model, config_key)][f"{condition}_l1_actionable"].append(match)
                per_model_per_config_per_source[(model, config_key, chain_source)][f"{condition}_l1_actionable"].append(match)

        per_model[model][f"{condition}_l2"].append(l2["coupled"])
        per_model_per_source[(model, chain_source)][f"{condition}_l2"].append(l2["coupled"])
        per_model_per_config[(model, config_key)][f"{condition}_l2"].append(l2["coupled"])
        per_model_per_config_per_source[(model, config_key, chain_source)][f"{condition}_l2"].append(l2["coupled"])

        # Layer 3 subsets (pooled over configs/sources)
        subsets = classify_chain(chain)
        for subset_name, subset_val in subsets.items():
            key = f"{subset_name}:{subset_val}"
            per_subset[model][f"{key}_{condition}_l1"].append(l1.get("top_k_match", 0) or 0)

    if skipped_no_chain:
        print(f"[scorer] WARN: skipped {skipped_no_chain} results with no matching chain")

    def _summarise(bucket: dict[str, list]) -> dict[str, Any]:
        l1_test = two_sample_proportion_test(bucket["real_l1"], bucket["shuffled_l1"])
        l1_act_test = two_sample_proportion_test(
            bucket["real_l1_actionable"], bucket["shuffled_l1_actionable"]
        )
        l2_test = welch_ttest(bucket["real_l2"], bucket["shuffled_l2"])
        # Outcome tier uses the actionable Layer 1 (since it's the cleaner primary)
        gap = l1_act_test.get("gap", 0.0) if "error" not in l1_act_test else 0.0
        pval = l1_act_test.get("p_value", 1.0) if "error" not in l1_act_test else 1.0
        return {
            "layer1": l1_test,
            "layer1_actionable": l1_act_test,
            "layer2": l2_test,
            "outcome_tier": classify_outcome_tier(gap, pval),
        }

    model_stats = {m: _summarise(b) for m, b in per_model.items()}
    source_stats = {f"{m}::{s}": _summarise(b) for (m, s), b in per_model_per_source.items()}
    config_stats = {f"{m}::{c}": _summarise(b) for (m, c), b in per_model_per_config.items()}
    config_source_stats = {
        f"{m}::{c}::{s}": _summarise(b)
        for (m, c, s), b in per_model_per_config_per_source.items()
    }

    # Stratified Layer 1 by ground-truth constraint type
    gt_type_stats: dict[str, dict[str, Any]] = {}
    for (model_name, src, gt_type), data in per_gt_type.items():
        test = two_sample_proportion_test(data["real"], data["shuffled"])
        gt_type_stats[f"{model_name}::{src}::{gt_type}"] = test

    return {
        "n_results": len(results),
        "per_model": model_stats,
        "per_model_per_source": source_stats,
        "per_model_per_config": config_stats,
        "per_model_per_config_per_source": config_source_stats,
        "layer1_by_gt_constraint_type": gt_type_stats,
        "per_subset": {m: dict(d) for m, d in per_subset.items()},
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=Path("results/raw"))
    parser.add_argument("--dist-tb", type=Path, default=None,
                        help="Reference distribution for TB chains")
    parser.add_argument("--dist-swe", type=Path, default=None,
                        help="Reference distribution for SWE chains")
    parser.add_argument("--dist-human", type=Path, default=None,
                        help="Reference distribution for human chains")
    parser.add_argument("--chains-real", type=Path, default=Path("chains/real"))
    parser.add_argument("--chains-shuffled", type=Path, default=Path("chains/shuffled"))
    parser.add_argument("--out", type=Path, default=Path("results/scored.json"))
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

    scored = score_all(args.results, dist_paths, args.chains_real, args.chains_shuffled)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(scored, f, indent=2)

    print(f"\nResults written to {args.out}")

    def _row(label: str, s: dict) -> str:
        l1 = s.get("layer1", {})
        l1a = s.get("layer1_actionable", {})
        l2 = s.get("layer2", {})
        gap1 = l1.get("gap", "N/A")
        p1 = l1.get("p_value", "N/A")
        gap1a = l1a.get("gap", "N/A")
        p1a = l1a.get("p_value", "N/A")
        gap2 = l2.get("gap", "N/A")
        p2 = l2.get("p_value", "N/A")
        tier = s.get("outcome_tier", "?")
        return (
            f"  {label:35s} L1={gap1:>7}(p={p1:>6}) | "
            f"L1act={gap1a:>7}(p={p1a:>6}) | "
            f"L2={gap2:>7}(p={p2:>6}) | {tier}"
        )

    print("\n=== Pooled (per model, all sources × configs) ===")
    print(f"  {'(label)':35s} L1={'(all)':>7}          | L1act={'(actionable cutoffs)':>20} | L2={'(legality×optimality)':>22}")
    for model, s in scored["per_model"].items():
        print(_row(model, s))

    print("\n=== Per-source (model :: source) ===")
    for label, s in sorted(scored["per_model_per_source"].items()):
        print(_row(label, s))

    print("\n=== Per-config (model :: T_seed) ===")
    for label, s in sorted(scored["per_model_per_config"].items()):
        print(_row(label, s))

    print("\n=== Per-config × per-source (model :: T_seed :: source) ===")
    for label, s in sorted(scored["per_model_per_config_per_source"].items()):
        print(_row(label, s))

    print("\n=== Layer 1 stratified by ground-truth constraint type ===")
    for label, s in sorted(scored["layer1_by_gt_constraint_type"].items()):
        if "error" in s:
            continue
        n_real = s.get("n_real", 0)
        n_shuf = s.get("n_shuffled", 0)
        gap = s.get("gap", "N/A")
        p = s.get("p_value", "N/A")
        rr = s.get("real_rate", "N/A")
        sr = s.get("shuffled_rate", "N/A")
        print(f"  {label:50s} real={rr:>7} shuf={sr:>7} gap={gap:>7} p={p:>6} (n_r={n_real}, n_s={n_shuf})")
