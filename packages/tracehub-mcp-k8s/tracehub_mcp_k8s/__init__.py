"""Read-only Kubernetes MCP server for TraceHub."""

from __future__ import annotations

from .client import ClusterResolver, KubernetesApiError, KubernetesReadClient
from .kubeconfig import ClusterConnection, KubeconfigError, load_connection
from .tools import (
    K8sToolContext,
    describe_pod,
    deployment_status,
    list_events,
    list_namespaces,
    list_pods,
    pod_logs,
    previous_pod_logs,
    resource_usage,
)

__all__ = [
    "ClusterConnection",
    "ClusterResolver",
    "K8sToolContext",
    "KubeconfigError",
    "KubernetesApiError",
    "KubernetesReadClient",
    "deployment_status",
    "describe_pod",
    "list_events",
    "list_namespaces",
    "list_pods",
    "load_connection",
    "pod_logs",
    "previous_pod_logs",
    "resource_usage",
]
