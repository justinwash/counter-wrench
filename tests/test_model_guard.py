"""Only config.py may build chat models.

Promised in step 1c: a model built anywhere else would skip provider pinning, temperature 0
and the per-role settings, with no error to show for it.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "counterwrench"
FORBIDDEN = re.compile(
    r"init_chat_model\(|\bChat(OpenAI|Anthropic|OpenRouter|GoogleGenerativeAI)\("
)


def test_only_config_builds_chat_models():
    offenders = [
        f"{path.relative_to(SRC)}:{lineno}"
        for path in SRC.rglob("*.py")
        if path.name != "config.py"
        for lineno, line in enumerate(path.read_text("utf-8").splitlines(), start=1)
        if FORBIDDEN.search(line)
    ]
    assert not offenders, f"Build chat models through config.py, not: {offenders}"


def test_guard_pattern_catches_direct_construction():
    assert FORBIDDEN.search('llm = init_chat_model("openrouter:x")')
    assert FORBIDDEN.search("llm = ChatOpenAI(model='x')")
    assert not FORBIDDEN.search("from counterwrench.config import build_chat_model")
