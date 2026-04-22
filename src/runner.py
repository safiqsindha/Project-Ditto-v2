"""
Evaluation runner for the Ditto v2 constraint-chain study.

Drives model evaluations against chain files, saves raw and blinded results,
and handles rate-limit errors with exponential backoff.

Uses the Anthropic Messages Batches API for 50% cost reduction (spec §7).
Add --source to select Terminal-Bench (tb), SWE-bench (swe), or human chains.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from src.prompt_builder import PROMPT_VERSION, SYSTEM_PROMPT, build_prompt, cutoff_rendered

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODELS: dict[str, str] = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
}

SEEDS: list[int] = [42, 1337, 7919]

# Full evaluation matrix (spec §7)
# Primary:       T=0.0, seed 42
# Variance study: T=0.5, seeds 1337 and 7919
EVAL_CONFIGS: list[dict] = [
    {"temperature": 0.0, "seed": 42},
    {"temperature": 0.5, "seed": 1337},
    {"temperature": 0.5, "seed": 7919},
]

_BACKOFF_DELAYS: list[float] = [2.0, 4.0, 8.0, 16.0]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_chain(chain_path: Path) -> dict:
    with chain_path.open("r", encoding="utf-8") as fh:
        first_line = fh.readline().strip()
    return json.loads(first_line)


def _count_steps(rendered: str) -> int:
    import re
    return len(re.findall(r"Step \d+", rendered))


def _call_api_with_backoff(
    client: anthropic.Anthropic,
    model_id: str,
    user_message: str,
    temperature: float = 0.0,
) -> str:
    """Call the Messages API with exponential backoff on rate-limit / 5xx errors."""
    last_exc: Exception | None = None

    for attempt, delay in enumerate([None] + _BACKOFF_DELAYS):
        if delay is not None:
            time.sleep(delay)

        try:
            response = client.messages.create(
                model=model_id,
                max_tokens=50,
                temperature=temperature,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            for block in response.content:
                if block.type == "text":
                    return block.text.strip()
            return ""

        except anthropic.RateLimitError as exc:
            last_exc = exc
            remaining = len(_BACKOFF_DELAYS) - attempt
            if remaining <= 0:
                raise
            print(
                f"[runner] Rate-limited (attempt {attempt + 1}). "
                f"Backing off {_BACKOFF_DELAYS[attempt]}s …"
            )

        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                last_exc = exc
                remaining = len(_BACKOFF_DELAYS) - attempt
                if remaining <= 0:
                    raise
                print(
                    f"[runner] Server error {exc.status_code} (attempt {attempt + 1}). "
                    f"Backing off {_BACKOFF_DELAYS[attempt]}s …"
                )
            else:
                raise

    assert last_exc is not None
    raise last_exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_evaluation(
    chain_path: Path,
    model_name: str,
    seed: int,
    source: str = "tb",
    cutoff_k: int | None = None,
    output_dir: Path = Path("results/raw"),
    dry_run: bool = False,
    temperature: float = 0.0,
) -> dict:
    """Run one evaluation on one chain with one model + seed."""
    load_dotenv(override=True)

    import os
    if not dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        print("[runner] ERROR: ANTHROPIC_API_KEY is not set.")
        raise SystemExit(1)

    if model_name not in MODELS:
        raise ValueError(f"Unknown model_name {model_name!r}. Choose from: {list(MODELS)}")
    model_id = MODELS[model_name]

    chain = _load_chain(chain_path)
    chain_id: str = chain["chain_id"]
    rendered: str = chain["rendered"]

    total_steps = _count_steps(rendered)
    if cutoff_k is None:
        cutoff_k = max(1, total_steps // 2)

    truncated = cutoff_rendered(rendered, cutoff_k)
    user_message = build_prompt(truncated, cutoff_k)

    if dry_run:
        print("=" * 72)
        print(f"[dry_run] chain_id={chain_id}  model={model_name}  seed={seed}  source={source}")
        print(f"[dry_run] cutoff_k={cutoff_k} / {total_steps} steps")
        print("-" * 72)
        print("SYSTEM:\n", SYSTEM_PROMPT)
        print("-" * 72)
        print("USER:\n", user_message)
        print("=" * 72)
        return {
            "chain_id": chain_id,
            "model": model_name,
            "seed": seed,
            "source": source,
            "cutoff_k": cutoff_k,
            "response": None,
            "prompt_version": PROMPT_VERSION,
        }

    client = anthropic.Anthropic()
    response_text = _call_api_with_backoff(client, model_id, user_message, temperature=temperature)

    result = {
        "chain_id": chain_id,
        "model": model_name,
        "seed": seed,
        "source": source,
        "cutoff_k": cutoff_k,
        "response": response_text,
        "prompt_version": PROMPT_VERSION,
        "temperature": temperature,
    }

    # Persist raw result (includes full metadata)
    source_dir = Path(output_dir) / source
    source_dir.mkdir(parents=True, exist_ok=True)
    raw_path = source_dir / f"{model_name}_{seed}_{chain_id}_T{temperature}.json"
    with raw_path.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)

    # Persist blinded result (scorer-facing; no model/seed/condition metadata)
    blinded_dir = Path(output_dir).parent / "blinded"
    blinded_dir.mkdir(parents=True, exist_ok=True)
    blinded = {
        "chain_id": chain_id,
        "cutoff_k": cutoff_k,
        "response": response_text,
        "prompt_version": PROMPT_VERSION,
    }
    blinded_path = blinded_dir / f"{chain_id}_{cutoff_k}.json"
    with blinded_path.open("w", encoding="utf-8") as fh:
        json.dump(blinded, fh, indent=2)

    return result


def run_all(
    chains_dir: Path,
    model_name: str,
    seed: int,
    source: str = "tb",
    output_dir: Path = Path("results/raw"),
    dry_run: bool = False,
    n: int | None = None,
    temperature: float = 0.0,
) -> list[dict]:
    """Run evaluations for every chain in chains_dir with the given model."""
    random.seed(seed)
    chain_files = sorted(chains_dir.glob("*.jsonl"), key=lambda p: p.stem)
    if n is not None:
        chain_files = chain_files[:n]

    results = []
    for cf in chain_files:
        result = run_evaluation(
            chain_path=cf,
            model_name=model_name,
            seed=seed,
            source=source,
            output_dir=output_dir,
            dry_run=dry_run,
            temperature=temperature,
        )
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run Ditto v2 constraint-chain evaluations."
    )
    parser.add_argument("--model", choices=list(MODELS), default="haiku")
    parser.add_argument("--chains", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--source",
        choices=["tb", "swe", "human"],
        default="tb",
        help="Data source to evaluate (tb=Terminal-Bench, swe=SWE-bench, human).",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--n", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("results/raw"))
    parser.add_argument("--temperature", type=float, default=0.0)

    args = parser.parse_args()

    results = run_all(
        chains_dir=args.chains,
        model_name=args.model,
        seed=args.seed,
        source=args.source,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        n=args.n,
        temperature=args.temperature,
    )

    print(f"\n[runner] Completed {len(results)} evaluations.")
    if results:
        sample = results[0]
        print(
            f"[runner] Sample → chain_id={sample['chain_id']}  "
            f"model={sample['model']}  cutoff_k={sample['cutoff_k']}  "
            f"response={sample['response']!r}"
        )
