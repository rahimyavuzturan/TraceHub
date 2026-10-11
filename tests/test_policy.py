"""Access policy tests.

Most cases run against a purpose-built configuration so they do not break when
the real allowlists change; two smoke tests assert the shipped configuration
still loads and still refuses production system namespaces.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tracehub_mcp_common.policy import AllowDeny, Policy, PolicyError, load_policy

POLICY_YAML = """
kubernetes:
  namespaces:
    allow: ["mobile", "dmz-*"]
    deny: ["kube-system", "dmz-secret"]
  limits:
    max_tail_lines: 500
    max_since_minutes: 1440

elasticsearch:
  indices:
    allow: ["app-*"]
    deny: ["*-pii-*"]
  limits:
    max_size: 100
    default_window_minutes: 60
    require_time_window: true

winrm:
  hosts:
    allow: ["STL*"]
    deny: ["SPL*"]

budget:
  tool_calls_per_session: 200
"""

ENVIRONMENTS_YAML = """
environments:
  prod:
    display_name: "Üretim"
    is_production: true
    k8s_context: prod-cluster
    namespaces: ["mobile"]
  test:
    display_name: "Test"
    is_production: false
    k8s_context: test-cluster
    namespaces: ["mobile", "dmz-mobile"]
"""


@pytest.fixture
def policy(tmp_path: Path) -> Policy:
    policy_file = tmp_path / "policy.yaml"
    environments_file = tmp_path / "environments.yaml"
    policy_file.write_text(POLICY_YAML, encoding="utf-8")
    environments_file.write_text(ENVIRONMENTS_YAML, encoding="utf-8")
    return load_policy(policy_file, environments_file)


# --- environments -------------------------------------------------------


def test_unknown_environment_is_rejected_in_turkish(policy: Policy) -> None:
    with pytest.raises(PolicyError, match="tanımlı bir ortam yok"):
        policy.assert_allowed(environment="uat")


def test_environment_error_lists_valid_options(policy: Policy) -> None:
    with pytest.raises(PolicyError) as excinfo:
        policy.assert_allowed(environment="uat")
    assert "prod" in str(excinfo.value)
    assert "test" in str(excinfo.value)


def test_environment_name_is_case_insensitive(policy: Policy) -> None:
    assert policy.environment("PROD").name == "prod"


def test_production_flag(policy: Policy) -> None:
    assert policy.is_production("prod") is True
    assert policy.is_production("test") is False


# --- namespaces ---------------------------------------------------------


def test_allowed_namespace_passes(policy: Policy) -> None:
    resolved = policy.assert_allowed(environment="prod", namespace="mobile")
    assert resolved.k8s_context == "prod-cluster"


def test_denied_namespace_is_rejected(policy: Policy) -> None:
    with pytest.raises(PolicyError, match="engellendi"):
        policy.assert_allowed(environment="test", namespace="kube-system")


def test_deny_overrides_allow(policy: Policy) -> None:
    """``dmz-secret`` matches allow pattern ``dmz-*`` but is explicitly denied."""
    with pytest.raises(PolicyError, match="engellendi"):
        policy.assert_allowed(environment="test", namespace="dmz-secret")


def test_namespace_must_belong_to_the_environment(policy: Policy) -> None:
    """``dmz-mobile`` is globally allowed but not mapped to prod."""
    with pytest.raises(PolicyError, match="ortamında tanımlı değil"):
        policy.assert_allowed(environment="prod", namespace="dmz-mobile")


def test_namespace_allowed_in_its_own_environment(policy: Policy) -> None:
    policy.assert_allowed(environment="test", namespace="dmz-mobile")


# --- indices and hosts --------------------------------------------------


def test_allowed_index_passes(policy: Policy) -> None:
    policy.assert_allowed(environment="test", index="app-msube-2026.09.29")


def test_unlisted_index_is_rejected(policy: Policy) -> None:
    with pytest.raises(PolicyError, match="engellendi"):
        policy.assert_allowed(environment="test", index="security-audit-2026")


def test_pii_index_is_denied(policy: Policy) -> None:
    with pytest.raises(PolicyError, match="engellendi"):
        policy.assert_allowed(environment="test", index="app-pii-2026")


def test_winrm_host_allowlist(policy: Policy) -> None:
    policy.assert_allowed(environment="test", host="STLSMART")
    with pytest.raises(PolicyError, match="engellendi"):
        policy.assert_allowed(environment="test", host="SPLSMART")


# --- limits -------------------------------------------------------------


def test_limit_is_clamped_to_policy_maximum(policy: Policy) -> None:
    assert policy.clamp("kubernetes", "max_tail_lines", 100_000, 200) == 500


def test_request_below_limit_is_untouched(policy: Policy) -> None:
    assert policy.clamp("kubernetes", "max_tail_lines", 50, 200) == 50


def test_unknown_limit_falls_back_to_default(policy: Policy) -> None:
    assert policy.clamp("kubernetes", "max_unknown", 999, 10) == 10


def test_time_window_is_required_for_elasticsearch(policy: Policy) -> None:
    assert policy.require_time_window("elasticsearch") is True


# --- allow/deny primitive ----------------------------------------------


def test_empty_allow_list_permits_everything_not_denied() -> None:
    rule = AllowDeny(allow=(), deny=("kube-*",))
    assert rule.permits("mobile") is True
    assert rule.permits("kube-system") is False


# --- shipped configuration ---------------------------------------------


def test_repository_configuration_loads() -> None:
    shipped = load_policy()
    assert "prod" in shipped.environment_names
    assert "dmz-prod" in shipped.environment_names


def test_shipped_policy_blocks_cluster_system_namespaces() -> None:
    shipped = load_policy()
    with pytest.raises(PolicyError):
        shipped.assert_allowed(environment="prod", namespace="kube-system")


def test_shipped_policy_blocks_security_indices() -> None:
    shipped = load_policy()
    with pytest.raises(PolicyError):
        shipped.assert_allowed(environment="prod", index="security-2026.09.29")


def test_shipped_policy_blocks_production_winrm_hosts() -> None:
    shipped = load_policy()
    with pytest.raises(PolicyError):
        shipped.assert_allowed(environment="prod", host="SPLSMART")
