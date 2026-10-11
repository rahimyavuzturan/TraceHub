"""Secret and PII redaction.

Every tool output passes through :func:`redact` before it reaches the model,
the database or the audit log. Getting this wrong means leaking credentials
into a prompt, so the patterns err on the side of over-masking.

Scope: docs/06-SECURITY.md section 3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

MASK: Final = "***"


@dataclass(frozen=True)
class RedactionRule:
    """One pattern to mask.

    ``replacement`` keeps any leading context captured in group 1 so that
    ``password=hunter2`` becomes ``password=***`` rather than losing the key.
    """

    name: str
    pattern: re.Pattern[str]
    replacement: str = rf"\1{MASK}"


# Order matters: private key blocks are matched before generic long strings.
RULES: Final[tuple[RedactionRule, ...]] = (
    RedactionRule(
        name="private_key",
        pattern=re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        replacement=f"-----BEGIN PRIVATE KEY-----{MASK}-----END PRIVATE KEY-----",
    ),
    RedactionRule(
        name="authorization_header",
        pattern=re.compile(
            r"\b(Authorization\s*[:=]\s*)(?:Bearer|Basic|Negotiate)?\s*\S+",
            re.IGNORECASE,
        ),
    ),
    RedactionRule(
        name="bearer_token",
        pattern=re.compile(r"\b(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
    ),
    RedactionRule(
        name="jwt",
        pattern=re.compile(r"\b(ey)[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+"),
        replacement=f"\\1{MASK}",
    ),
    RedactionRule(
        name="azure_devops_pat",
        pattern=re.compile(r"\b(pat_|ghp_|gho_|github_pat_)[A-Za-z0-9_]{16,}"),
        replacement=f"\\1{MASK}",
    ),
    RedactionRule(
        name="key_value_secret",
        pattern=re.compile(
            # The key is often prefixed: DB_PASSWORD, spring.datasource.password,
            # AZURE_CLIENT_SECRET. A plain \b would not match after '_' or '.',
            # so the prefix is consumed into group 1 and kept in the output.
            r"([A-Za-z0-9]*(?:[_.-][A-Za-z0-9]+)*[_.-]?"
            r"(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|client[_-]?secret"
            r"|access[_-]?key|private[_-]?key|connection[_-]?string|conn[_-]?str)"
            r"\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|\S+)",
            re.IGNORECASE,
        ),
    ),
    RedactionRule(
        name="connection_string_credentials",
        pattern=re.compile(r"\b([a-z][a-z0-9+.-]*://[^\s:/@]+:)[^\s@]+(?=@)", re.IGNORECASE),
    ),
    RedactionRule(
        name="iban",
        pattern=re.compile(r"\b(TR)\d{24}\b"),
        replacement=f"\\1{MASK}",
    ),
    RedactionRule(
        name="email",
        pattern=re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ),
)

# Handled separately because they need a checksum/length check rather than a
# plain pattern match - masking every 11-digit number would destroy log data.
_TCKN_PATTERN: Final = re.compile(r"\b[1-9]\d{10}\b")
_CARD_PATTERN: Final = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")


@dataclass(frozen=True)
class RedactionResult:
    """Redacted text plus which rules fired, for audit purposes."""

    text: str
    applied: tuple[str, ...]

    @property
    def was_redacted(self) -> bool:
        return bool(self.applied)


def redact(text: str) -> str:
    """Mask secrets and personal data in ``text``."""
    return redact_detailed(text).text


def redact_detailed(text: str) -> RedactionResult:
    """Like :func:`redact` but also reports which rules matched."""
    if not text:
        return RedactionResult(text=text, applied=())

    applied: list[str] = []
    result = text

    for rule in RULES:
        result, count = rule.pattern.subn(rule.replacement, result)
        if count:
            applied.append(rule.name)

    result, tckn_hits = _redact_tckn(result)
    if tckn_hits:
        applied.append("tckn")

    result, card_hits = _redact_card_numbers(result)
    if card_hits:
        applied.append("card_number")

    return RedactionResult(text=result, applied=tuple(applied))


def redact_mapping(data: dict[str, object]) -> dict[str, object]:
    """Redact a parameter dictionary before it is logged or audited.

    Keys whose name suggests a secret are masked entirely; other values are
    redacted by content.
    """
    # 'pat' is anchored: an unanchored match would also swallow 'path',
    # 'patch' and 'compatible', destroying diagnostic parameters.
    sensitive_key = re.compile(
        r"password|passwd|pwd|secret|token|api[_-]?key|apikey"
        r"|credential|authorization|\bpat\b",
        re.IGNORECASE,
    )

    redacted: dict[str, object] = {}
    for key, value in data.items():
        if sensitive_key.search(key):
            redacted[key] = MASK
        elif isinstance(value, str):
            redacted[key] = redact(value)
        elif isinstance(value, dict):
            redacted[key] = redact_mapping(value)
        elif isinstance(value, list):
            redacted[key] = [redact(item) if isinstance(item, str) else item for item in value]
        else:
            redacted[key] = value
    return redacted


def _redact_tckn(text: str) -> tuple[str, int]:
    """Mask Turkish national ID numbers, verified by their checksum.

    Without the checksum test any 11-digit number - timestamps, correlation
    ids, byte counts - would be destroyed.
    """
    hits = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal hits
        if not _is_valid_tckn(match.group(0)):
            return match.group(0)
        hits += 1
        return MASK

    return _TCKN_PATTERN.sub(replace, text), hits


def _is_valid_tckn(value: str) -> bool:
    digits = [int(char) for char in value]
    odd_sum = sum(digits[0:9:2])
    even_sum = sum(digits[1:8:2])
    tenth = (odd_sum * 7 - even_sum) % 10
    eleventh = (sum(digits[:10])) % 10
    return digits[9] == tenth and digits[10] == eleventh


def _redact_card_numbers(text: str) -> tuple[str, int]:
    """Mask card numbers that pass the Luhn check."""
    hits = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal hits
        digits = re.sub(r"\D", "", match.group(0))
        if not 13 <= len(digits) <= 19 or not _passes_luhn(digits):
            return match.group(0)
        hits += 1
        return MASK

    return _CARD_PATTERN.sub(replace, text), hits


def _passes_luhn(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0
