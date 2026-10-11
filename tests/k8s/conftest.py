"""Shared fixtures for the Kubernetes MCP server tests.

Nothing here touches a real cluster: a fake resolver answers API paths from
recorded-looking payloads, so the tools run end to end offline.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from tracehub_mcp_common import MemoryAuditSink, Policy, load_policy
from tracehub_mcp_k8s.client import KubernetesReadClient
from tracehub_mcp_k8s.tools import K8sToolContext

POLICY_YAML = """
kubernetes:
  namespaces:
    allow: ["mobile", "payments"]
    deny: ["kube-system"]
  limits:
    max_tail_lines: 500
    max_since_minutes: 120
"""

ENVIRONMENTS_YAML = """
environments:
  prod:
    display_name: "Üretim"
    is_production: true
    k8s_context: prod-cluster
    namespaces: ["mobile", "payments"]
  test:
    display_name: "Test"
    is_production: false
    k8s_context: test-cluster
    namespaces: ["mobile", "payments"]
  eksik:
    display_name: "Context'siz"
    is_production: false
    namespaces: ["mobile"]
"""


def minutes_ago(minutes: float) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


class FakeCluster:
    """Answers API paths from a dictionary and records what was asked."""

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses: dict[str, Any] = responses or {}
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def _lookup(self, path: str) -> Any:
        if path not in self.responses:
            raise AssertionError(f"Beklenmeyen istek: {path}")
        return self.responses[path]

    async def json(self, path: str, **params: Any) -> dict[str, Any]:
        self.requests.append((path, params))
        payload = self._lookup(path)
        assert isinstance(payload, dict)
        return payload

    async def items(self, path: str, **params: Any) -> list[dict[str, Any]]:
        self.requests.append((path, params))
        payload = self._lookup(path)
        if isinstance(payload, dict):
            items = payload.get("items", [])
            return list(items) if isinstance(items, list) else []
        return list(payload)

    async def text(self, path: str, **params: Any) -> str:
        self.requests.append((path, params))
        return str(self._lookup(path))

    async def aclose(self) -> None:
        return None

    async def __aenter__(self) -> FakeCluster:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def params_for(self, path: str) -> dict[str, Any]:
        for requested, params in self.requests:
            if requested == path:
                return params
        raise AssertionError(f"{path} istegi hic yapilmadi. Yapilanlar: {self.requests}")


class FakeResolver:
    """Stands in for :class:`ClusterResolver` without opening a socket."""

    def __init__(self, cluster: FakeCluster) -> None:
        self.cluster = cluster
        self.opened: list[str] = []

    async def open(self, environment: str, policy: Policy) -> KubernetesReadClient:
        policy.environment(environment)
        self.opened.append(environment)
        return self.cluster  # type: ignore[return-value]


@pytest.fixture
def policy(tmp_path: Any) -> Policy:
    policy_file = tmp_path / "policy.yaml"
    environments_file = tmp_path / "environments.yaml"
    policy_file.write_text(POLICY_YAML, encoding="utf-8")
    environments_file.write_text(ENVIRONMENTS_YAML, encoding="utf-8")
    return load_policy(policy_file, environments_file)


@pytest.fixture
def cluster() -> FakeCluster:
    return FakeCluster()


@pytest.fixture
def audit() -> MemoryAuditSink:
    return MemoryAuditSink()


@pytest.fixture
def ctx(policy: Policy, cluster: FakeCluster, audit: MemoryAuditSink) -> K8sToolContext:
    return K8sToolContext(
        session_id="k8s-test",
        actor="tester",
        policy=policy,
        audit=audit,
        clusters=FakeResolver(cluster),  # type: ignore[arg-type]
    )


def crashloop_pod(name: str = "msube-web-7d9") -> dict[str, Any]:
    """A pod stuck in CrashLoopBackOff after a bad ConfigMap change."""
    return {
        "metadata": {
            "name": name,
            "namespace": "mobile",
            "creationTimestamp": minutes_ago(240),
            "labels": {"app": "msube-web"},
            "ownerReferences": [{"kind": "ReplicaSet", "name": "msube-web-7d9f4"}],
        },
        "spec": {
            "nodeName": "worker-03",
            "containers": [
                {
                    "name": "web",
                    "image": "registry.local/msube-web:1.4.2",
                    "envFrom": [{"configMapRef": {"name": "msube-web-config"}}],
                }
            ],
            "volumes": [{"name": "config", "configMap": {"name": "msube-web-config"}}],
        },
        "status": {
            "phase": "Running",
            "podIP": "10.42.3.17",
            "conditions": [
                {
                    "type": "Ready",
                    "status": "False",
                    "reason": "ContainersNotReady",
                    "message": "containers with unready status: [web]",
                }
            ],
            "containerStatuses": [
                {
                    "name": "web",
                    "ready": False,
                    "restartCount": 7,
                    "image": "registry.local/msube-web:1.4.2",
                    "state": {
                        "waiting": {
                            "reason": "CrashLoopBackOff",
                            "message": "back-off 5m0s restarting failed container",
                        }
                    },
                    "lastState": {
                        "terminated": {
                            "reason": "Error",
                            "exitCode": 1,
                            "finishedAt": minutes_ago(3),
                        }
                    },
                }
            ],
        },
    }


def healthy_pod(name: str = "msube-web-abc") -> dict[str, Any]:
    return {
        "metadata": {"name": name, "namespace": "mobile", "creationTimestamp": minutes_ago(600)},
        "spec": {"nodeName": "worker-01", "containers": [{"name": "web"}]},
        "status": {
            "phase": "Running",
            "podIP": "10.42.3.18",
            "conditions": [{"type": "Ready", "status": "True"}],
            "containerStatuses": [
                {"name": "web", "ready": True, "restartCount": 0, "state": {"running": {}}}
            ],
        },
    }
