"""T0.2 - user-facing strings live in messages.py and stay Turkish."""

from __future__ import annotations

from tracehub_core import messages

PLACEHOLDER_MESSAGES = {
    "ERR_UNKNOWN_ENVIRONMENT": {"environment", "allowed"},
    "ERR_NOT_ALLOWED": {"reason"},
    "ERR_BUDGET_EXCEEDED": {"limit"},
    "KB_VALIDATION_OK": {"count"},
    "KB_VALIDATION_FAILED": {"count"},
    "KB_INGEST_DONE": {"docs", "chunks"},
}


def test_placeholders_are_formattable() -> None:
    for name, keys in PLACEHOLDER_MESSAGES.items():
        template: str = getattr(messages, name)
        rendered = template.format(**dict.fromkeys(keys, "X"))
        assert "{" not in rendered, f"{name} icinde doldurulmamis alan kaldi"


def test_messages_are_turkish() -> None:
    """Spot check: user-facing constants must contain Turkish characters."""
    turkish_chars = set("çğıöşüÇĞİÖŞÜ")
    sample = [
        messages.ERR_LLM_UNAVAILABLE,
        messages.PLAN_APPROVAL_PROMPT,
        messages.WARN_READ_ONLY,
        messages.WARN_PRODUCTION,
    ]
    for text in sample:
        assert turkish_chars & set(text), f"Turkce olmayan kullanici metni: {text!r}"


def test_read_only_warning_states_the_golden_rule() -> None:
    assert "değişiklik yapmaz" in messages.WARN_READ_ONLY
