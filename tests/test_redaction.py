"""Redaction tests with realistic payloads.

A false negative here means a credential ends up in a prompt, so the cases are
taken from shapes that actually appear in logs and config dumps.
"""

from __future__ import annotations

import pytest

from tracehub_mcp_common.redaction import MASK, redact, redact_detailed, redact_mapping

# Valid checksum, reserved test value.
VALID_TCKN = "10000000146"
INVALID_TCKN = "12345678901"
VALID_CARD = "4111111111111111"
INVALID_CARD = "4111111111111112"


def test_empty_text_is_untouched() -> None:
    assert redact("") == ""


def test_password_assignment_keeps_the_key() -> None:
    result = redact("DB_PASSWORD=hunter2 baglanti kuruldu")
    assert "hunter2" not in result
    assert "DB_PASSWORD=" in result
    assert MASK in result


@pytest.mark.parametrize(
    "line",
    [
        "DB_PASSWORD=hunter2",
        "spring.datasource.password: hunter2",
        "AZURE_CLIENT_SECRET=hunter2",
        "x-api-key: hunter2",
        "ELASTIC_TOKEN = hunter2",
        "password=hunter2",
    ],
)
def test_prefixed_secret_keys_are_masked(line: str) -> None:
    """Real config dumps prefix the key; a word-boundary anchor would miss them."""
    assert "hunter2" not in redact(line)


def test_quoted_secret_is_masked() -> None:
    assert "s3cr3t" not in redact('client_secret: "s3cr3t"')


def test_authorization_header_is_masked() -> None:
    result = redact("Authorization: Bearer abcdef0123456789abcdef")
    assert "abcdef0123456789" not in result


def test_jwt_is_masked() -> None:
    token = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    result = redact(f"token={token}")
    assert "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c" not in result


def test_connection_string_password_is_masked() -> None:
    result = redact("postgresql://tracehub:GizliParola@db.local:5432/tracehub")
    assert "GizliParola" not in result
    # The host stays readable: it is diagnostic signal, not a secret.
    assert "db.local" in result


def test_private_key_block_is_collapsed() -> None:
    text = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEAxyz...\nmore-base64-here\n"
        "-----END RSA PRIVATE KEY-----"
    )
    result = redact(text)
    assert "MIIEowIBAAKCAQEAxyz" not in result
    assert "more-base64-here" not in result


def test_email_keeps_first_character() -> None:
    result = redact("Talebi acan: ahmet.yilmaz@kuveytturk.com.tr")
    assert "ahmet.yilmaz@kuveytturk.com.tr" not in result
    assert result.startswith("Talebi acan: a")


def test_valid_tckn_is_masked() -> None:
    assert VALID_TCKN not in redact(f"musteri no {VALID_TCKN} bulundu")


def test_invalid_tckn_survives() -> None:
    """Timestamps and ids must not be destroyed by an over-eager digit rule."""
    text = f"correlation id {INVALID_TCKN} kaydedildi"
    assert redact(text) == text


def test_luhn_valid_card_is_masked() -> None:
    assert VALID_CARD not in redact(f"kart {VALID_CARD} islemi")


def test_luhn_invalid_number_survives() -> None:
    text = f"referans {INVALID_CARD} numarasi"
    assert redact(text) == text


def test_iban_is_masked() -> None:
    result = redact("IBAN: TR330006100519786457841326")
    assert "330006100519786457841326" not in result
    assert "TR" in result


def test_plain_log_line_is_not_altered() -> None:
    text = "2026-09-29T10:00:00Z pod msube-web-7d9 CrashLoopBackOff restart count 7"
    assert redact(text) == text


def test_detailed_reports_which_rules_fired() -> None:
    result = redact_detailed("password=abc123 ve TR330006100519786457841326")
    assert result.was_redacted
    assert "key_value_secret" in result.applied
    assert "iban" in result.applied


def test_detailed_on_clean_text_reports_nothing() -> None:
    result = redact_detailed("namespace mobile icinde 3 pod calisiyor")
    assert not result.was_redacted
    assert result.applied == ()


def test_mapping_masks_sensitive_keys_entirely() -> None:
    redacted = redact_mapping({"host": "SDLAPP01", "api_key": "abc", "token": "xyz"})
    assert redacted["host"] == "SDLAPP01"
    assert redacted["api_key"] == MASK
    assert redacted["token"] == MASK


@pytest.mark.parametrize("key", ["path", "patch_level", "compatible", "namespace"])
def test_mapping_does_not_over_mask_diagnostic_keys(key: str) -> None:
    """Masking 'path' would throw away the signal we are investigating."""
    assert redact_mapping({key: "mobile"})[key] == "mobile"


def test_mapping_redacts_nested_values() -> None:
    redacted = redact_mapping(
        {
            "query": {"user": "ahmet.yilmaz@kuveytturk.com.tr"},
            "lines": ["password=gizli", "pod calisiyor"],
            "tail": 200,
        }
    )
    nested = redacted["query"]
    assert isinstance(nested, dict)
    assert "ahmet.yilmaz@kuveytturk.com.tr" not in str(nested["user"])

    lines = redacted["lines"]
    assert isinstance(lines, list)
    assert "gizli" not in lines[0]
    assert lines[1] == "pod calisiyor"

    assert redacted["tail"] == 200
