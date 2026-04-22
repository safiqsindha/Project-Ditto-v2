"""
Prompt builder for the Ditto v2 constraint-chain evaluation.

PROMPT_VERSION = "v2.0-code"  — versioned separately from v1's v1.0.
The prompt is deliberately generic: no programming-domain vocabulary.
Must work identically on Terminal-Bench and SWE-bench chains with no
source-specific branching.
"""

PROMPT_VERSION = "v2.0-code"

SYSTEM_PROMPT = """You are reasoning about an adaptive pipeline that operates under
a sequence of changing constraints. At each step, new constraints
may appear, existing constraints may change, and resources may
be depleted. Your job is to propose the correct adaptation at
each step, given the full prior history.

At each step you receive a partially-observable state: you see
the constraints and resource levels that have been revealed, but
some entities remain hidden until they are explicitly surfaced
through an action or information event.

Constraints carry forward unless explicitly superseded. Treat
"tool UNAVAILABLE" as persistent unless a later event makes it
available again."""


def cutoff_rendered(rendered: str, k: int) -> str:
    """Return only the first k steps of a rendered chain string.

    Steps in the rendered format start with "Step N" (where N is a positive
    integer).  The function splits on those boundaries and returns the
    re-joined prefix for the first *k* steps.
    """
    import re

    if k <= 0:
        return ""

    parts = re.split(r"(Step \d+)", rendered)

    steps: list[tuple[str, str]] = []
    i = 0
    while i < len(parts) and not re.fullmatch(r"Step \d+", parts[i]):
        i += 1

    while i + 1 < len(parts):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        if re.fullmatch(r"Step \d+", header):
            steps.append((header, body))
            i += 2
        else:
            i += 1

    if not steps:
        return ""

    selected = steps[:k]
    return "".join(header + body for header, body in selected)


def build_prompt(rendered_steps: str, cutoff_k: int) -> str:
    """Build the user-facing prompt given a rendered chain up to step K.

    The system prompt is kept separate; this function returns only the
    *user* message.
    """
    return (
        f"{rendered_steps.rstrip()}\n"
        "\n"
        "---\n"
        "\n"
        f"Given the state above, propose the next action for your pipeline at\n"
        f"step {cutoff_k + 1}. Output only the action label (e.g., "
        '"use command_2" or "switch to file_C"). No explanation.'
    )
