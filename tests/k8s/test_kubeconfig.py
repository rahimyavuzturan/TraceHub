"""Kubeconfig parsing tests.

The parser is a security boundary: it decides which credentials we send and
whether TLS is verified, so the refusal cases matter as much as the happy path.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from tracehub_mcp_k8s.kubeconfig import KubeconfigError, load_connection

CA_PEM = b"-----BEGIN CERTIFICATE-----\nZmFrZQ==\n-----END CERTIFICATE-----\n"


def write_kubeconfig(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config"
    path.write_text(body, encoding="utf-8")
    return path


TOKEN_CONFIG = """
clusters:
  - name: test-cluster
    cluster:
      server: https://api.test.local:6443
contexts:
  - name: test-cluster
    context:
      cluster: test-cluster
      user: viewer
users:
  - name: viewer
    user:
      token: sa-token-value
"""


def test_token_context_is_resolved(tmp_path: Path) -> None:
    connection = load_connection(write_kubeconfig(tmp_path, TOKEN_CONFIG), "test-cluster")

    assert connection.server == "https://api.test.local:6443"
    assert connection.headers["Authorization"] == "Bearer sa-token-value"
    assert connection.verify is True


def test_missing_file_is_reported_with_the_setting_name(tmp_path: Path) -> None:
    with pytest.raises(KubeconfigError, match="TRACEHUB_KUBERNETES__KUBECONFIG"):
        load_connection(tmp_path / "yok", "test-cluster")


def test_unknown_context_lists_the_available_ones(tmp_path: Path) -> None:
    with pytest.raises(KubeconfigError, match="test-cluster"):
        load_connection(write_kubeconfig(tmp_path, TOKEN_CONFIG), "prod-cluster")


def test_exec_credential_plugin_is_refused(tmp_path: Path) -> None:
    """Credential plugins launch an arbitrary binary -- out of the question here."""
    body = TOKEN_CONFIG.replace(
        "      token: sa-token-value",
        "      exec:\n        command: aws\n        apiVersion: client.authentication.k8s.io/v1",
    )

    with pytest.raises(KubeconfigError, match="harici program"):
        load_connection(write_kubeconfig(tmp_path, body), "test-cluster")


def test_context_without_credentials_is_refused(tmp_path: Path) -> None:
    body = TOKEN_CONFIG.replace("      token: sa-token-value", "      username: admin")

    with pytest.raises(KubeconfigError, match="kimlik bilgisi yok"):
        load_connection(write_kubeconfig(tmp_path, body), "test-cluster")


def test_token_file_is_read(tmp_path: Path) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("dosyadan-token\n", encoding="utf-8")
    body = TOKEN_CONFIG.replace(
        "      token: sa-token-value", f"      tokenFile: {token_file}"
    )

    connection = load_connection(write_kubeconfig(tmp_path, body), "test-cluster")

    assert connection.headers["Authorization"] == "Bearer dosyadan-token"


def test_inline_ca_is_written_to_a_file(tmp_path: Path) -> None:
    encoded = base64.b64encode(CA_PEM).decode()
    body = TOKEN_CONFIG.replace(
        "      server: https://api.test.local:6443",
        f"      server: https://api.test.local:6443\n      certificate-authority-data: {encoded}",
    )

    connection = load_connection(write_kubeconfig(tmp_path, body), "test-cluster")

    assert isinstance(connection.verify, str)
    assert Path(connection.verify).read_bytes() == CA_PEM


def test_insecure_skip_tls_verify_is_honoured(tmp_path: Path) -> None:
    body = TOKEN_CONFIG.replace(
        "      server: https://api.test.local:6443",
        "      server: https://api.test.local:6443\n      insecure-skip-tls-verify: true",
    )

    connection = load_connection(write_kubeconfig(tmp_path, body), "test-cluster")

    assert connection.verify is False


def test_half_a_client_certificate_is_refused(tmp_path: Path) -> None:
    cert = tmp_path / "client.crt"
    cert.write_bytes(CA_PEM)
    body = TOKEN_CONFIG.replace(
        "      token: sa-token-value", f"      client-certificate: {cert}"
    )

    with pytest.raises(KubeconfigError, match="sertifika ve anahtarın ikisi de"):
        load_connection(write_kubeconfig(tmp_path, body), "test-cluster")


def test_client_certificate_pair_is_resolved(tmp_path: Path) -> None:
    cert = tmp_path / "client.crt"
    key = tmp_path / "client.key"
    cert.write_bytes(CA_PEM)
    key.write_bytes(CA_PEM)
    body = TOKEN_CONFIG.replace(
        "      token: sa-token-value",
        f"      client-certificate: {cert}\n      client-key: {key}",
    )

    connection = load_connection(write_kubeconfig(tmp_path, body), "test-cluster")

    assert connection.cert == (str(cert), str(key))


def test_missing_referenced_file_is_reported(tmp_path: Path) -> None:
    body = TOKEN_CONFIG.replace(
        "      server: https://api.test.local:6443",
        "      server: https://api.test.local:6443\n"
        f"      certificate-authority: {tmp_path / 'olmayan.pem'}",
    )

    with pytest.raises(KubeconfigError, match="bulunamadı"):
        load_connection(write_kubeconfig(tmp_path, body), "test-cluster")
