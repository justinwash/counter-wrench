"""PII redaction for free text, before it reaches the model, the trace or a saved order.

Pattern-based (v0): emails, phone numbers, card numbers (Luhn-checked, so part numbers don't
match) and names in recognizable patterns ("my name is ...", "Mr. ..."). Known limitation:
bare names ("John says it creaks") are not caught; a name-recognition model would also tend to
tag bike names (Marlin, Trance, Hightower) as people. See DECISIONS D-029.
"""

from __future__ import annotations

import re
from collections import Counter

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# 13-19 digits, optionally grouped by spaces or dashes; confirmed with the Luhn checksum.
CARD = re.compile(r"(?<![\w-])\d(?:[ -]?\d){12,18}(?![\w-])")
# North American numbers with optional country code; separators optional.
PHONE = re.compile(
    r"(?<![\w-])(?:\+?1[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-]?)\d{3}[\s.-]?\d{4}(?![\w-])"
)
_NAME = r"([A-Z][a-z]+(?:[ '-][A-Z][a-z]+){0,2})"
NAME_PATTERNS = [
    re.compile(r"\b(?:[Mm]y name is|[Nn]ame is|[Nn]ame:|[Cc]ustomer:|[Cc]ontact:)\s+" + _NAME),
    re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+" + _NAME),
]


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def redact(text: str) -> tuple[str, Counter]:
    """Return the redacted text and counts by type (never the values themselves)."""
    counts: Counter = Counter()

    def card(match: re.Match) -> str:
        digits = re.sub(r"\D", "", match.group())
        if _luhn(digits):
            counts["card"] += 1
            return "[CARD]"
        return match.group()

    def replace(kind: str, placeholder: str):
        def sub(match: re.Match) -> str:
            counts[kind] += 1
            return placeholder

        return sub

    text = EMAIL.sub(replace("email", "[EMAIL]"), text)
    text = CARD.sub(card, text)  # before phones: card digits can look like a phone number
    text = PHONE.sub(replace("phone", "[PHONE]"), text)
    for pattern in NAME_PATTERNS:

        def name(match: re.Match) -> str:
            counts["name"] += 1
            start, end = match.span(1)
            whole = match.group()
            offset = match.start()
            return whole[: start - offset] + "[NAME]" + whole[end - offset :]

        text = pattern.sub(name, text)
    return text, counts
