"""Turning Kubernetes API objects into short Turkish text.

The model reads these strings, so they carry the diagnostic signal -- phase,
waiting reason, restart count, last exit code -- and drop the rest of the
object. Raw JSON would fill the context window with noise.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tracehub_mcp_common import format_table

#: Waiting/terminated reasons that almost always explain the incident.
PROBLEM_REASONS: frozenset[str] = frozenset(
    {
        "CrashLoopBackOff",
        "ImagePullBackOff",
        "ErrImagePull",
        "CreateContainerConfigError",
        "CreateContainerError",
        "InvalidImageName",
        "OOMKilled",
        "Error",
        "RunContainerError",
    }
)


def pod_state(pod: dict[str, Any]) -> str:
    """Return the state a human would read off ``kubectl get pods``."""
    status = _dict(pod.get("status"))

    if _dict(pod.get("metadata")).get("deletionTimestamp"):
        return "Terminating"

    for container in _containers(status):
        state = _dict(container.get("state"))
        if waiting := _dict(state.get("waiting")).get("reason"):
            return str(waiting)
        terminated = _dict(state.get("terminated"))
        if terminated and terminated.get("reason") not in (None, "Completed"):
            return str(terminated.get("reason"))

    return str(status.get("phase", "Bilinmiyor"))


def pod_is_healthy(pod: dict[str, Any]) -> bool:
    status = _dict(pod.get("status"))
    phase = status.get("phase")
    if phase == "Succeeded":
        return True
    if phase != "Running":
        return False
    return all(container.get("ready") for container in _containers(status))


def restart_count(pod: dict[str, Any]) -> int:
    return sum(
        int(container.get("restartCount", 0)) for container in _containers(_dict(pod.get("status")))
    )


def pod_table(pods: list[dict[str, Any]]) -> str:
    """Render a pod list the way ``kubectl get pods`` would."""
    rows = [
        {
            "POD": _name(pod),
            "DURUM": pod_state(pod),
            "HAZIR": _ready_ratio(pod),
            "YENIDEN BASLATMA": restart_count(pod),
            "YAS": age_of(_dict(pod.get("metadata")).get("creationTimestamp")),
            "NODE": _dict(pod.get("spec")).get("nodeName") or "-",
        }
        for pod in pods
    ]
    return format_table(
        rows, columns=["POD", "DURUM", "HAZIR", "YENIDEN BASLATMA", "YAS", "NODE"]
    )


def pod_detail(pod: dict[str, Any]) -> str:
    """A focused replacement for ``kubectl describe pod``."""
    metadata = _dict(pod.get("metadata"))
    status = _dict(pod.get("status"))
    spec = _dict(pod.get("spec"))

    lines = [
        f"Pod: {_name(pod)}",
        f"Namespace: {metadata.get('namespace', '-')}",
        f"Durum: {pod_state(pod)} (phase={status.get('phase', '-')})",
        f"Node: {spec.get('nodeName') or '-'}",
        f"Pod IP: {status.get('podIP') or '-'}",
        f"Olusturulma: {age_of(metadata.get('creationTimestamp'))} once",
    ]

    if owner := _owner(metadata):
        lines.append(f"Sahip: {owner}")
    if labels := _dict(metadata.get("labels")):
        lines.append("Etiketler: " + ", ".join(f"{k}={v}" for k, v in sorted(labels.items())))

    lines.append("")
    lines.append("Kapsayicilar:")
    for container in _containers(status):
        lines.extend(_container_lines(container))

    if conditions := _failing_conditions(status):
        lines.append("")
        lines.append("Saglanmayan kosullar:")
        lines.extend(f"  - {condition}" for condition in conditions)

    if volumes := _configmap_and_secret_volumes(spec):
        lines.append("")
        lines.append("Bagli yapilandirma kaynaklari:")
        lines.extend(f"  - {volume}" for volume in volumes)

    return "\n".join(lines)


def event_table(events: list[dict[str, Any]]) -> str:
    """Render events newest last, the order a reader scans for a cause."""
    ordered = sorted(events, key=_event_timestamp)
    rows = [
        {
            "ZAMAN": age_of(_event_timestamp_text(event)),
            "TUR": event.get("type", "-"),
            "SEBEP": event.get("reason", "-"),
            "NESNE": _involved_object(event),
            "ADET": event.get("count", 1),
            "MESAJ": _shorten(str(event.get("message", "")), 120),
        }
        for event in ordered
    ]
    return format_table(rows, columns=["ZAMAN", "TUR", "SEBEP", "NESNE", "ADET", "MESAJ"])


def deployment_table(deployments: list[dict[str, Any]]) -> str:
    rows = []
    for deployment in deployments:
        status = _dict(deployment.get("status"))
        spec = _dict(deployment.get("spec"))
        desired = int(spec.get("replicas", 0))
        ready = int(status.get("readyReplicas", 0))
        rows.append(
            {
                "DEPLOYMENT": _name(deployment),
                "HAZIR": f"{ready}/{desired}",
                "GUNCEL": status.get("updatedReplicas", 0),
                "KULLANILABILIR": status.get("availableReplicas", 0),
                "YAS": age_of(_dict(deployment.get("metadata")).get("creationTimestamp")),
                "IMAJ": _shorten(_first_image(spec), 60),
            }
        )
    return format_table(
        rows,
        columns=["DEPLOYMENT", "HAZIR", "GUNCEL", "KULLANILABILIR", "YAS", "IMAJ"],
    )


def deployment_conditions(deployment: dict[str, Any]) -> list[str]:
    """Return the deployment conditions that are not satisfied."""
    conditions = _dict(deployment.get("status")).get("conditions")
    if not isinstance(conditions, list):
        return []
    return [
        f"{condition.get('type')}={condition.get('status')} "
        f"({condition.get('reason', '-')}: {condition.get('message', '-')})"
        for condition in conditions
        if isinstance(condition, dict) and condition.get("status") != "True"
    ]


def usage_table(metrics: list[dict[str, Any]]) -> str:
    rows = []
    for entry in metrics:
        for container in _list(entry.get("containers")):
            usage = _dict(container.get("usage"))
            rows.append(
                {
                    "POD": _name(entry),
                    "KAPSAYICI": container.get("name", "-"),
                    "CPU": _cpu(str(usage.get("cpu", "0"))),
                    "BELLEK": _memory(str(usage.get("memory", "0"))),
                }
            )
    return format_table(rows, columns=["POD", "KAPSAYICI", "CPU", "BELLEK"])


def seconds_since(timestamp: object) -> float | None:
    """Seconds elapsed since an ISO-8601 timestamp, or ``None`` if unparsable."""
    if not isinstance(timestamp, str) or not timestamp:
        return None
    try:
        moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(UTC) - moment).total_seconds()


def age_of(timestamp: object) -> str:
    """Format an ISO-8601 timestamp as an age such as ``3g 4sa``."""
    elapsed = seconds_since(timestamp)
    if elapsed is None:
        return "-"

    seconds = int(elapsed)
    if seconds < 0:
        return "0sn"
    if seconds < 60:
        return f"{seconds}sn"
    if seconds < 3600:
        return f"{seconds // 60}dk"
    if seconds < 86400:
        return f"{seconds // 3600}sa {(seconds % 3600) // 60}dk"
    return f"{seconds // 86400}g {(seconds % 86400) // 3600}sa"


def event_timestamp(event: dict[str, Any]) -> str:
    """The most recent timestamp an event carries.

    Core v1 events use ``lastTimestamp``; the newer events.k8s.io shape uses
    ``eventTime``, and one-shot events may only have ``firstTimestamp``.
    """
    for key in ("lastTimestamp", "eventTime", "firstTimestamp"):
        if value := event.get(key):
            return str(value)
    return str(_dict(event.get("metadata")).get("creationTimestamp", ""))


# --- internals ----------------------------------------------------------


def _container_lines(container: dict[str, Any]) -> list[str]:
    name = container.get("name", "-")
    ready = "hazir" if container.get("ready") else "HAZIR DEGIL"
    restarts = container.get("restartCount", 0)
    lines = [f"  - {name}: {ready}, {restarts} yeniden baslatma"]
    lines.append(f"      imaj: {container.get('image', '-')}")

    state = _dict(container.get("state"))
    if waiting := _dict(state.get("waiting")):
        lines.append(
            f"      bekliyor: {waiting.get('reason', '-')} "
            f"({_shorten(str(waiting.get('message', '-')), 160)})"
        )
    if terminated := _dict(state.get("terminated")):
        lines.append(
            f"      sonlandi: {terminated.get('reason', '-')}, "
            f"cikis kodu {terminated.get('exitCode', '-')}"
        )

    last = _dict(_dict(container.get("lastState")).get("terminated"))
    if last:
        lines.append(
            f"      onceki calisma: {last.get('reason', '-')}, "
            f"cikis kodu {last.get('exitCode', '-')}, "
            f"{age_of(last.get('finishedAt'))} once bitti"
        )
        if last.get("reason") == "OOMKilled":
            lines.append("      NOT: bellek limiti asildigi icin oldurulmus.")
    return lines


def _failing_conditions(status: dict[str, Any]) -> list[str]:
    conditions = status.get("conditions")
    if not isinstance(conditions, list):
        return []
    return [
        f"{condition.get('type')}: {condition.get('reason', '-')} "
        f"({_shorten(str(condition.get('message', '-')), 140)})"
        for condition in conditions
        if isinstance(condition, dict) and condition.get("status") != "True"
    ]


def _configmap_and_secret_volumes(spec: dict[str, Any]) -> list[str]:
    """Config sources are a frequent root cause, so they are called out."""
    found: list[str] = []
    for volume in _list(spec.get("volumes")):
        if config_map := _dict(volume.get("configMap")).get("name"):
            found.append(f"configMap/{config_map} (volume: {volume.get('name')})")
        if secret := _dict(volume.get("secret")).get("secretName"):
            found.append(f"secret/{secret} (volume: {volume.get('name')})")

    for container in _list(spec.get("containers")):
        for source in _list(container.get("envFrom")):
            if config_map := _dict(source.get("configMapRef")).get("name"):
                found.append(f"configMap/{config_map} (envFrom)")
            if secret := _dict(source.get("secretRef")).get("name"):
                found.append(f"secret/{secret} (envFrom)")
    return found


def _owner(metadata: dict[str, Any]) -> str:
    owners = _list(metadata.get("ownerReferences"))
    return ", ".join(f"{owner.get('kind')}/{owner.get('name')}" for owner in owners)


def _involved_object(event: dict[str, Any]) -> str:
    involved = _dict(event.get("involvedObject"))
    return f"{involved.get('kind', '-')}/{involved.get('name', '-')}"


def _event_timestamp_text(event: dict[str, Any]) -> str:
    return event_timestamp(event)


def _event_timestamp(event: dict[str, Any]) -> str:
    return event_timestamp(event)


def _first_image(spec: dict[str, Any]) -> str:
    containers = _list(_dict(_dict(spec.get("template")).get("spec")).get("containers"))
    return str(containers[0].get("image", "-")) if containers else "-"


def _ready_ratio(pod: dict[str, Any]) -> str:
    containers = _containers(_dict(pod.get("status")))
    ready = sum(1 for container in containers if container.get("ready"))
    return f"{ready}/{len(containers)}"


def _containers(status: dict[str, Any]) -> list[dict[str, Any]]:
    return _list(status.get("initContainerStatuses")) + _list(status.get("containerStatuses"))


def _cpu(value: str) -> str:
    if value.endswith("n"):
        return f"{int(value[:-1]) // 1_000_000}m"
    if value.endswith("u"):
        return f"{int(value[:-1]) // 1_000}m"
    return value


def _memory(value: str) -> str:
    if value.endswith("Ki"):
        return f"{int(value[:-2]) // 1024}Mi"
    return value


def _name(obj: dict[str, Any]) -> str:
    return str(_dict(obj.get("metadata")).get("name", "-"))


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _shorten(text: str, limit: int) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"
