"""Flags for free text that tries to instruct the model or asks for non-shop work.

Flag, don't block: real customers write odd things, the model already treats free text as
untrusted data, and it can't approve anything anyway. Flags give the reviewing mechanic and
the evals visibility. Pattern-based (v0); an LLM classifier is a possible improvement.
"""

from __future__ import annotations

import re

PATTERNS: dict[str, list[str]] = {
    "instruction_override": [
        r"\b(ignore|disregard|forget)\b.{0,30}\b(previous|prior|above|earlier|your|all)\b"
        r".{0,20}\b(instructions?|rules|prompts?|guidelines)\b",
        r"\byou are now\b",
        r"\bnew instructions\b",
        r"\bact as (an?|the)\b",
    ],
    "role_tag": [
        r"\b(system|assistant|developer)\s*:",
        r"</?\s*(system|instructions?|customer_note|staff_answer|general_notes|description)\b",
    ],
    "approval_pressure": [
        r"\bapprove (it|this|the (order|work order|draft))\b",
        r"\bmark (it|this|the bike)\b.{0,15}\bsafe\b",
        r"\b(skip|no need for|without) (the |an |any )?inspection\b",
        r"\bjust sell me\b",
        r"\b(it'?s|bike is) (totally |perfectly )?(safe|fine) to ride\b",
    ],
    "out_of_scope": [
        r"\bwrite (me )?(a|an) (poem|essay|story|song|program|script)\b",
        r"\btell me a joke\b",
        r"\bwhat'?s the weather\b",
        r"\b(stock|crypto|investment) (tips?|advice|picks?)\b",
    ],
}

_COMPILED = {
    kind: [re.compile(p, re.IGNORECASE) for p in patterns] for kind, patterns in PATTERNS.items()
}


def flag(text: str) -> list[str]:
    """Kinds of suspicious content found in `text`, in a stable order."""
    return [kind for kind, patterns in _COMPILED.items() if any(p.search(text) for p in patterns)]
