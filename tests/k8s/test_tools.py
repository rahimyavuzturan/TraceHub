"""Tests for the read-only Kubernetes tools.

Every tool is exercised against a fake cluster, so the suite runs without a
kubeconfig, a network or Docker.
"""

from __future__ import annotations

import pytest

from tracehub_mcp_common import MemoryAuditSink
from tracehub_mcp_k8s.client import KubernetesApiError
from tracehub_mcp_k8s.tools import (
    deployment_status,
    describe_pod,
    list_events,
    list_namespaces,
    list_pods,
    pod_logs,
    previous_pod_logs,
    resource_usage,
)

from .conftest import FakeCluster, K8sToolContext, crashloop_pod, healthy_pod, minutes_ago

PODS_PATH = "/api/v1/namespaces/mobile/pods"
EVENTS_PATH = "/api/v1/namespaces/mobile/events"
LOG_PATH = "/api/v1/namespaces/mobile/pods/msube-web-7d9/log"
DEPLOYMENTS_PATH = "/apis/apps/v1/namespaces/mobile/deployments"
METRICS_PATH = "/apis/metrics.k8s.io/v1beta1/namespaces/mobile/pods"


# --- list_namespaces ----------------------------------------------------


async def test_list_namespaces_hides_denied_entries(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    cluster.responses["/api/v1/namespaces"] = {
        "items": [
            {"metadata": {"name": "mobile"}},
            {"metadata": {"name": "payments"}},
            {"metadata": {"name": "kube-system"}},
        ]
    }

    result = await list_namespaces(ctx, environment="test")

    assert "mobile" in result
    assert "payments" in result
    assert "kube-system" not in result
    assert "1 namespace politika geregi listelenmedi" in result


# --- list_pods ----------------------------------------------------------


async def test_list_pods_renders_a_table(ctx: K8sToolContext, cluster: FakeCluster) -> None:
    cluster.responses[PODS_PATH] = {"items": [crashloop_pod(), healthy_pod()]}

    result = await list_pods(ctx, environment="test", namespace="mobile")

    assert "msube-web-7d9" in result
    assert "CrashLoopBackOff" in result
    assert "2/2 pod" in result


async def test_list_pods_only_unhealthy_filters(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    cluster.responses[PODS_PATH] = {"items": [crashloop_pod(), healthy_pod()]}

    result = await list_pods(
        ctx, environment="test", namespace="mobile", only_unhealthy=True
    )

    assert "msube-web-7d9" in result
    assert "msube-web-abc" not in result


async def test_list_pods_points_to_the_next_tool(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    """A problem pod should nudge the model towards the log of the crash."""
    cluster.responses[PODS_PATH] = {"items": [crashloop_pod()]}

    result = await list_pods(ctx, environment="test", namespace="mobile")

    assert "previous_pod_logs" in result


async def test_list_pods_passes_label_selector(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    cluster.responses[PODS_PATH] = {"items": []}

    await list_pods(
        ctx, environment="test", namespace="mobile", label_selector="app=msube-web"
    )

    assert cluster.params_for(PODS_PATH)["labelSelector"] == "app=msube-web"


async def test_list_pods_reports_empty_namespace(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    cluster.responses[PODS_PATH] = {"items": []}

    result = await list_pods(ctx, environment="test", namespace="mobile")

    assert "pod bulunamadi" in result


# --- describe_pod -------------------------------------------------------


async def test_describe_pod_surfaces_the_crash_evidence(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    cluster.responses[f"{PODS_PATH}/msube-web-7d9"] = crashloop_pod()
    cluster.responses[EVENTS_PATH] = {
        "items": [
            {
                "type": "Warning",
                "reason": "BackOff",
                "message": "Back-off restarting failed container",
                "count": 12,
                "lastTimestamp": minutes_ago(2),
                "involvedObject": {"kind": "Pod", "name": "msube-web-7d9"},
            }
        ]
    }

    result = await describe_pod(
        ctx, environment="test", namespace="mobile", pod="msube-web-7d9"
    )

    assert "CrashLoopBackOff" in result
    assert "7 yeniden baslatma" in result
    assert "cikis kodu 1" in result
    assert "configMap/msube-web-config" in result
    assert "ContainersNotReady" in result
    assert "BackOff" in result


async def test_describe_pod_scopes_events_to_the_pod(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    cluster.responses[f"{PODS_PATH}/msube-web-7d9"] = crashloop_pod()
    cluster.responses[EVENTS_PATH] = {"items": []}

    await describe_pod(ctx, environment="test", namespace="mobile", pod="msube-web-7d9")

    selector = cluster.params_for(EVENTS_PATH)["fieldSelector"]
    assert selector == "involvedObject.name=msube-web-7d9"


# --- logs ---------------------------------------------------------------


async def test_pod_logs_applies_the_time_window(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    cluster.responses[LOG_PATH] = "2026-09-30T10:00:00Z uygulama basladi"

    await pod_logs(
        ctx,
        environment="test",
        namespace="mobile",
        pod="msube-web-7d9",
        since_minutes=15,
    )

    params = cluster.params_for(LOG_PATH)
    assert params["sinceSeconds"] == 900
    assert params["previous"] is None


async def test_pod_logs_clamps_to_the_policy_ceiling(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    """A model asking for a million lines must not be able to get them."""
    cluster.responses[LOG_PATH] = "satir"

    await pod_logs(
        ctx,
        environment="test",
        namespace="mobile",
        pod="msube-web-7d9",
        tail_lines=1_000_000,
        since_minutes=100_000,
    )

    params = cluster.params_for(LOG_PATH)
    assert params["tailLines"] == 500
    assert params["sinceSeconds"] == 120 * 60


async def test_empty_log_suggests_previous_logs(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    cluster.responses[LOG_PATH] = "   \n"

    result = await pod_logs(
        ctx, environment="test", namespace="mobile", pod="msube-web-7d9"
    )

    assert "previous_pod_logs" in result


async def test_previous_pod_logs_requests_the_previous_container(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    cluster.responses[LOG_PATH] = "java.lang.IllegalStateException: config eksik"

    result = await previous_pod_logs(
        ctx, environment="test", namespace="mobile", pod="msube-web-7d9"
    )

    params = cluster.params_for(LOG_PATH)
    assert params["previous"] == "true"
    # The API rejects a time window together with previous=true.
    assert params["sinceSeconds"] is None
    assert "IllegalStateException" in result


async def test_previous_pod_logs_explains_an_empty_result(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    cluster.responses[LOG_PATH] = ""

    result = await previous_pod_logs(
        ctx, environment="test", namespace="mobile", pod="msube-web-7d9"
    )

    assert "hic yeniden baslamamis" in result


async def test_log_secrets_are_redacted(ctx: K8sToolContext, cluster: FakeCluster) -> None:
    cluster.responses[LOG_PATH] = "FATAL: cannot connect, DB_PASSWORD=CokGizli123"

    result = await pod_logs(
        ctx, environment="test", namespace="mobile", pod="msube-web-7d9"
    )

    assert "CokGizli123" not in result


# --- list_events --------------------------------------------------------


async def test_list_events_drops_entries_outside_the_window(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    cluster.responses[EVENTS_PATH] = {
        "items": [
            {
                "type": "Warning",
                "reason": "BackOff",
                "message": "yeni",
                "lastTimestamp": minutes_ago(5),
                "involvedObject": {"kind": "Pod", "name": "msube-web-7d9"},
            },
            {
                "type": "Warning",
                "reason": "FailedMount",
                "message": "eski",
                "lastTimestamp": minutes_ago(600),
                "involvedObject": {"kind": "Pod", "name": "eski-pod"},
            },
        ]
    }

    result = await list_events(
        ctx, environment="test", namespace="mobile", since_minutes=30
    )

    assert "BackOff" in result
    assert "FailedMount" not in result


async def test_list_events_defaults_to_warnings(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    cluster.responses[EVENTS_PATH] = {"items": []}

    await list_events(ctx, environment="test", namespace="mobile")

    assert cluster.params_for(EVENTS_PATH)["fieldSelector"] == "type=Warning"


# --- deployment_status --------------------------------------------------


async def test_deployment_status_reports_unmet_conditions(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    cluster.responses[DEPLOYMENTS_PATH] = {
        "items": [
            {
                "metadata": {"name": "msube-web", "creationTimestamp": minutes_ago(5000)},
                "spec": {
                    "replicas": 3,
                    "template": {
                        "spec": {"containers": [{"image": "registry.local/msube-web:1.4.2"}]}
                    },
                },
                "status": {
                    "readyReplicas": 1,
                    "updatedReplicas": 3,
                    "availableReplicas": 1,
                    "conditions": [
                        {
                            "type": "Available",
                            "status": "False",
                            "reason": "MinimumReplicasUnavailable",
                            "message": "Deployment does not have minimum availability.",
                        }
                    ],
                },
            }
        ]
    }

    result = await deployment_status(ctx, environment="test", namespace="mobile")

    assert "1/3" in result
    assert "MinimumReplicasUnavailable" in result


async def test_deployment_status_can_target_one_deployment(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    cluster.responses[f"{DEPLOYMENTS_PATH}/msube-web"] = {
        "metadata": {"name": "msube-web"},
        "spec": {"replicas": 1},
        "status": {"readyReplicas": 1},
    }

    result = await deployment_status(
        ctx, environment="test", namespace="mobile", deployment="msube-web"
    )

    assert "msube-web" in result


# --- resource_usage -----------------------------------------------------


async def test_resource_usage_converts_units(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    cluster.responses[METRICS_PATH] = {
        "items": [
            {
                "metadata": {"name": "msube-web-7d9"},
                "containers": [{"name": "web", "usage": {"cpu": "250000000n", "memory": "524288Ki"}}],
            }
        ]
    }

    result = await resource_usage(ctx, environment="test", namespace="mobile")

    assert "250m" in result
    assert "512Mi" in result


async def test_resource_usage_explains_a_missing_metrics_server(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    cluster.responses[METRICS_PATH] = {"items": []}

    result = await resource_usage(ctx, environment="test", namespace="mobile")

    assert "metrics-server" in result


# --- policy and safety --------------------------------------------------


async def test_denied_namespace_never_reaches_the_cluster(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    result = await list_pods(ctx, environment="test", namespace="kube-system")

    assert "Erişim reddedildi" in result
    assert cluster.requests == []


async def test_unknown_environment_is_refused(
    ctx: K8sToolContext, cluster: FakeCluster
) -> None:
    result = await list_pods(ctx, environment="uat", namespace="mobile")

    assert "Erişim reddedildi" in result
    assert cluster.requests == []


async def test_environment_without_context_is_reported(ctx: K8sToolContext) -> None:
    """A half-configured environment must fail loudly, not silently pick a cluster."""
    with pytest.raises(KubernetesApiError, match="kubeconfig context"):
        await list_pods(ctx, environment="eksik", namespace="mobile")


@pytest.mark.parametrize(
    "malicious",
    ["../../secrets", "mobile/pods/x", "Mobile", "pod name", "-leading"],
)
async def test_injected_names_are_rejected(
    ctx: K8sToolContext, cluster: FakeCluster, malicious: str
) -> None:
    """Names come from the model, so they are untrusted path input."""
    with pytest.raises(KubernetesApiError, match="geçerli bir Kubernetes"):
        await describe_pod(
            ctx, environment="test", namespace="mobile", pod=malicious
        )
    assert cluster.requests == []


async def test_production_call_is_marked_in_the_audit_trail(
    ctx: K8sToolContext, cluster: FakeCluster, audit: MemoryAuditSink
) -> None:
    cluster.responses[PODS_PATH] = {"items": []}

    await list_pods(ctx, environment="prod", namespace="mobile")

    event = audit.events[0]
    assert event.is_production is True
    assert event.tool == "list_pods"
    assert event.category == "k8s"
