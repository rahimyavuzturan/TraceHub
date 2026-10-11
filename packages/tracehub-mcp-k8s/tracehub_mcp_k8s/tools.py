"""Read-only Kubernetes tools.

Docstrings are Turkish on purpose: the model picks a tool by reading them, so
each one says what it answers and when to reach for something else instead.

Every tool starts with ``ctx.policy.assert_allowed(...)`` and receives its
cluster client from the context, never from module-level state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tracehub_mcp_common import PolicyError, ToolBudget, ToolContext, readonly_tool

from .client import ClusterResolver, safe_name
from .formatting import (
    PROBLEM_REASONS,
    deployment_conditions,
    deployment_table,
    event_table,
    event_timestamp,
    pod_detail,
    pod_is_healthy,
    pod_state,
    pod_table,
    seconds_since,
    usage_table,
)

CATEGORY = "k8s"

DEFAULT_TAIL_LINES = 200
DEFAULT_LOG_MINUTES = 30
DEFAULT_EVENT_MINUTES = 60


@dataclass
class K8sToolContext(ToolContext):
    """Tool context carrying the cluster resolver."""

    clusters: ClusterResolver = field(default_factory=ClusterResolver)


@readonly_tool(category=CATEGORY, cost=ToolBudget.CHEAP)
async def list_namespaces(ctx: K8sToolContext, environment: str) -> str:
    """Bir ortamdaki Kubernetes namespace'lerini listeler (salt okunur).

    Hangi namespace'in incelenecegi bilinmiyorsa ilk adim olarak kullanin.
    Politika tarafindan erisime kapatilmis namespace'ler listede gorunmez.

    Args:
        environment: Hedef ortam adi (ornek: prod, test, dmz-prod).
    """
    ctx.policy.assert_allowed(environment=environment)

    async with await ctx.clusters.open(environment, ctx.policy) as client:
        items = await client.items("/api/v1/namespaces")

    names = sorted(str(item.get("metadata", {}).get("name", "")) for item in items)
    allowed = [name for name in names if _is_allowed(ctx, environment, name)]

    if not allowed:
        return f"'{environment}' ortaminda erisilebilir namespace bulunamadi."

    hidden = len(names) - len(allowed)
    lines = [f"'{environment}' ortaminda {len(allowed)} erisilebilir namespace:"]
    lines.extend(f"  - {name}" for name in allowed)
    if hidden:
        lines.append(f"({hidden} namespace politika geregi listelenmedi.)")
    return "\n".join(lines)


@readonly_tool(category=CATEGORY, cost=ToolBudget.CHEAP)
async def list_pods(
    ctx: K8sToolContext,
    environment: str,
    namespace: str,
    label_selector: str | None = None,
    only_unhealthy: bool = False,
) -> str:
    """Bir namespace'teki pod'lari durumlariyla birlikte listeler (salt okunur).

    Ariza arastirmasina genellikle buradan baslanir: hangi pod'un
    CrashLoopBackOff, ImagePullBackOff veya Pending oldugunu gosterir.

    Args:
        environment: Hedef ortam adi.
        namespace: Kubernetes namespace'i.
        label_selector: Etiket filtresi (ornek: "app=msube-web").
        only_unhealthy: True ise yalnizca sagliksiz pod'lari dondurur.
    """
    ctx.policy.assert_allowed(environment=environment, namespace=namespace)

    async with await ctx.clusters.open(environment, ctx.policy) as client:
        pods = await client.items(
            f"/api/v1/namespaces/{safe_name(namespace, kind='namespace')}/pods",
            labelSelector=label_selector,
        )

    total = len(pods)
    if only_unhealthy:
        pods = [pod for pod in pods if not pod_is_healthy(pod)]

    if not pods:
        scope = "sagliksiz pod" if only_unhealthy else "pod"
        return f"{environment}/{namespace}: {scope} bulunamadi (toplam {total} pod)."

    header = f"{environment}/{namespace}: {len(pods)}/{total} pod gosteriliyor"
    problems = [pod for pod in pods if pod_state(pod) in PROBLEM_REASONS]
    footer = ""
    if problems:
        names = ", ".join(str(pod.get("metadata", {}).get("name")) for pod in problems[:5])
        footer = f"\n\nDikkat: {len(problems)} pod sorunlu durumda ({names}). "
        footer += "Detay icin describe_pod, neden icin previous_pod_logs kullanin."

    return f"{header}\n\n{pod_table(pods)}{footer}"


@readonly_tool(category=CATEGORY, cost=ToolBudget.CHEAP)
async def describe_pod(
    ctx: K8sToolContext,
    environment: str,
    namespace: str,
    pod: str,
) -> str:
    """Bir pod'un ayrintilarini ve ona ait son olaylari getirir (salt okunur).

    Kapsayici durumlari, yeniden baslatma sayilari, cikis kodlari, saglanmayan
    kosullar ve bagli configMap/secret kaynaklari ozetlenir.

    Args:
        environment: Hedef ortam adi.
        namespace: Kubernetes namespace'i.
        pod: Pod adi.
    """
    ctx.policy.assert_allowed(environment=environment, namespace=namespace)

    namespace_path = safe_name(namespace, kind="namespace")
    pod_path = safe_name(pod, kind="pod")

    async with await ctx.clusters.open(environment, ctx.policy) as client:
        detail = await client.json(f"/api/v1/namespaces/{namespace_path}/pods/{pod_path}")
        events = await client.items(
            f"/api/v1/namespaces/{namespace_path}/events",
            fieldSelector=f"involvedObject.name={pod}",
            limit=30,
        )

    text = pod_detail(detail)
    if events:
        text += "\n\nSon olaylar:\n" + event_table(events)
    return text


@readonly_tool(category=CATEGORY, cost=ToolBudget.MODERATE)
async def pod_logs(
    ctx: K8sToolContext,
    environment: str,
    namespace: str,
    pod: str,
    container: str | None = None,
    tail_lines: int = DEFAULT_TAIL_LINES,
    since_minutes: int = DEFAULT_LOG_MINUTES,
) -> str:
    """Calisan bir kapsayicinin gunluklerini getirir (salt okunur).

    Pod surekli yeniden basliyorsa (CrashLoopBackOff) bu arac cogu zaman bos
    doner; o durumda previous_pod_logs kullanin.

    Args:
        environment: Hedef ortam adi.
        namespace: Kubernetes namespace'i.
        pod: Pod adi.
        container: Cok kapsayicili pod'larda kapsayici adi.
        tail_lines: Sondan kac satir okunacagi. Ust sinir politikadan gelir.
        since_minutes: Kac dakika geriye bakilacagi. Dar tutun.
    """
    ctx.policy.assert_allowed(environment=environment, namespace=namespace)

    tail = ctx.policy.clamp(CATEGORY, "max_tail_lines", tail_lines, DEFAULT_TAIL_LINES)
    minutes = ctx.policy.clamp(CATEGORY, "max_since_minutes", since_minutes, DEFAULT_LOG_MINUTES)

    text = await _read_logs(
        ctx,
        environment=environment,
        namespace=namespace,
        pod=pod,
        container=container,
        tail_lines=tail,
        since_seconds=minutes * 60,
        previous=False,
    )

    header = f"{environment}/{namespace}/{pod} son {minutes} dakika, son {tail} satir"
    if container:
        header += f" (kapsayici: {container})"
    if not text.strip():
        return (
            f"{header}\n\n(gunluk bos). Pod yeniden basliyorsa previous_pod_logs ile "
            "onceki calismanin gunlugune bakin."
        )
    return f"{header}\n\n{text}"


@readonly_tool(category=CATEGORY, cost=ToolBudget.MODERATE)
async def previous_pod_logs(
    ctx: K8sToolContext,
    environment: str,
    namespace: str,
    pod: str,
    container: str | None = None,
    tail_lines: int = DEFAULT_TAIL_LINES,
) -> str:
    """Kapsayicinin ONCEKI calismasinin gunluklerini getirir (salt okunur).

    CrashLoopBackOff durumunda cokme sebebi burada gorunur: mevcut kapsayici
    henuz ayaga kalkmadigi icin pod_logs bos doner.

    Args:
        environment: Hedef ortam adi.
        namespace: Kubernetes namespace'i.
        pod: Pod adi.
        container: Cok kapsayicili pod'larda kapsayici adi.
        tail_lines: Sondan kac satir okunacagi.
    """
    ctx.policy.assert_allowed(environment=environment, namespace=namespace)

    tail = ctx.policy.clamp(CATEGORY, "max_tail_lines", tail_lines, DEFAULT_TAIL_LINES)

    text = await _read_logs(
        ctx,
        environment=environment,
        namespace=namespace,
        pod=pod,
        container=container,
        tail_lines=tail,
        # 'previous' and a time window are mutually exclusive in the API.
        since_seconds=None,
        previous=True,
    )

    header = f"{environment}/{namespace}/{pod} ONCEKI calisma, son {tail} satir"
    if not text.strip():
        return f"{header}\n\n(onceki calismaya ait gunluk yok; pod hic yeniden baslamamis olabilir)"
    return f"{header}\n\n{text}"


@readonly_tool(category=CATEGORY, cost=ToolBudget.CHEAP)
async def list_events(
    ctx: K8sToolContext,
    environment: str,
    namespace: str,
    since_minutes: int = DEFAULT_EVENT_MINUTES,
    only_warnings: bool = True,
) -> str:
    """Bir namespace'teki son Kubernetes olaylarini listeler (salt okunur).

    Zamanlama, imaj cekme, saglik kontrolu ve kaynak yetersizligi sorunlari
    genellikle once burada gorunur.

    Args:
        environment: Hedef ortam adi.
        namespace: Kubernetes namespace'i.
        since_minutes: Kac dakika geriye bakilacagi.
        only_warnings: True ise yalnizca Warning turundeki olaylar dondurulur.
    """
    ctx.policy.assert_allowed(environment=environment, namespace=namespace)

    minutes = ctx.policy.clamp(CATEGORY, "max_since_minutes", since_minutes, DEFAULT_EVENT_MINUTES)

    async with await ctx.clusters.open(environment, ctx.policy) as client:
        events = await client.items(
            f"/api/v1/namespaces/{safe_name(namespace, kind='namespace')}/events",
            fieldSelector="type=Warning" if only_warnings else None,
            limit=100,
        )

    recent = [event for event in events if _within(event, minutes)]
    if not recent:
        scope = "uyari" if only_warnings else "olay"
        return f"{environment}/{namespace}: son {minutes} dakikada {scope} yok."

    return (
        f"{environment}/{namespace}: son {minutes} dakikada {len(recent)} olay\n\n"
        + event_table(recent)
    )


@readonly_tool(category=CATEGORY, cost=ToolBudget.CHEAP)
async def deployment_status(
    ctx: K8sToolContext,
    environment: str,
    namespace: str,
    deployment: str | None = None,
) -> str:
    """Deployment'larin replika ve kullanilabilirlik durumunu getirir (salt okunur).

    Istenen replika sayisina ulasilamadiginda sebebi (kosullar) da yazilir.

    Args:
        environment: Hedef ortam adi.
        namespace: Kubernetes namespace'i.
        deployment: Tek bir deployment adi. Bos birakilirsa hepsi listelenir.
    """
    ctx.policy.assert_allowed(environment=environment, namespace=namespace)

    base = f"/apis/apps/v1/namespaces/{safe_name(namespace, kind='namespace')}/deployments"

    async with await ctx.clusters.open(environment, ctx.policy) as client:
        if deployment:
            deployments = [await client.json(f"{base}/{safe_name(deployment, kind='deployment')}")]
        else:
            deployments = await client.items(base)

    if not deployments:
        return f"{environment}/{namespace}: deployment bulunamadi."

    text = f"{environment}/{namespace}: {len(deployments)} deployment\n\n"
    text += deployment_table(deployments)

    for item in deployments:
        if conditions := deployment_conditions(item):
            name = item.get("metadata", {}).get("name", "-")
            text += f"\n\n{name} saglanmayan kosullar:\n"
            text += "\n".join(f"  - {condition}" for condition in conditions)

    return text


@readonly_tool(category=CATEGORY, cost=ToolBudget.CHEAP)
async def resource_usage(
    ctx: K8sToolContext,
    environment: str,
    namespace: str,
    pod: str | None = None,
) -> str:
    """Pod'larin anlik CPU ve bellek kullanimini getirir (salt okunur).

    metrics-server gerektirir. OOMKilled suphesinde bellek limitiyle birlikte
    degerlendirin; anlik deger cokme anini yansitmayabilir.

    Args:
        environment: Hedef ortam adi.
        namespace: Kubernetes namespace'i.
        pod: Tek bir pod adi. Bos birakilirsa namespace'teki tum pod'lar.
    """
    ctx.policy.assert_allowed(environment=environment, namespace=namespace)

    base = (
        "/apis/metrics.k8s.io/v1beta1/namespaces/"
        f"{safe_name(namespace, kind='namespace')}/pods"
    )

    async with await ctx.clusters.open(environment, ctx.policy) as client:
        if pod:
            metrics = [await client.json(f"{base}/{safe_name(pod, kind='pod')}")]
        else:
            metrics = await client.items(base)

    if not metrics:
        return f"{environment}/{namespace}: kullanim metrigi yok (metrics-server kurulu mu?)."

    return f"{environment}/{namespace} anlik kullanim\n\n{usage_table(metrics)}"


# --- internals ----------------------------------------------------------


async def _read_logs(
    ctx: K8sToolContext,
    *,
    environment: str,
    namespace: str,
    pod: str,
    container: str | None,
    tail_lines: int,
    since_seconds: int | None,
    previous: bool,
) -> str:
    path = (
        f"/api/v1/namespaces/{safe_name(namespace, kind='namespace')}"
        f"/pods/{safe_name(pod, kind='pod')}/log"
    )
    async with await ctx.clusters.open(environment, ctx.policy) as client:
        return await client.text(
            path,
            container=container,
            tailLines=tail_lines,
            sinceSeconds=since_seconds,
            previous="true" if previous else None,
            timestamps="true",
        )


def _is_allowed(ctx: K8sToolContext, environment: str, namespace: str) -> bool:
    try:
        ctx.policy.assert_allowed(environment=environment, namespace=namespace)
    except PolicyError:
        return False
    return True


def _within(event: dict[str, Any], minutes: int) -> bool:
    """Keep events inside the window; undatable events are kept, not hidden."""
    elapsed = seconds_since(event_timestamp(event))
    if elapsed is None:
        return True
    return elapsed <= minutes * 60
