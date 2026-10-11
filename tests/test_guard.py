"""Tests for the read-only guard, HTTP client and output shaping."""

from __future__ import annotations

import httpx
import pytest

from tracehub_mcp_common import (
    MemoryAuditSink,
    PolicyError,
    ReadOnlyHttpClient,
    ReadOnlyToolError,
    ReadOnlyViolationError,
    ToolBudget,
    ToolBudgetState,
    ToolContext,
    format_table,
    readonly_tool,
    summarize_output,
)


@pytest.fixture
def audit() -> MemoryAuditSink:
    return MemoryAuditSink()


@pytest.fixture
def ctx(audit: MemoryAuditSink) -> ToolContext:
    return ToolContext(session_id="oturum-1", actor="tester", audit=audit)


# --- the decorator ------------------------------------------------------


async def test_tool_returns_output_and_writes_audit(
    ctx: ToolContext, audit: MemoryAuditSink
) -> None:
    @readonly_tool(category="k8s", cost=ToolBudget.CHEAP)
    async def pod_durumu(ctx: ToolContext, environment: str, namespace: str) -> str:
        """Pod durumunu getirir (salt okunur)."""
        return f"{environment}/{namespace}: 3 pod calisiyor"

    result = await pod_durumu(ctx, environment="test", namespace="mobile")

    assert "3 pod calisiyor" in result
    assert len(audit.events) == 1
    event = audit.events[0]
    assert event.tool == "pod_durumu"
    assert event.category == "k8s"
    assert event.environment == "test"
    assert event.ok is True
    assert event.actor == "tester"
    assert event.session_id == "oturum-1"


async def test_production_calls_are_flagged_in_audit(
    ctx: ToolContext, audit: MemoryAuditSink
) -> None:
    @readonly_tool(category="k8s")
    async def pod_listesi(ctx: ToolContext, environment: str) -> str:
        """Pod listesini getirir (salt okunur)."""
        return "ok"

    await pod_listesi(ctx, environment="prod")
    assert audit.events[0].is_production is True

    await pod_listesi(ctx, environment="test")
    assert audit.events[1].is_production is False


async def test_tool_output_is_redacted_before_returning(ctx: ToolContext) -> None:
    @readonly_tool(category="k8s")
    async def pod_gunlukleri(ctx: ToolContext, environment: str) -> str:
        """Pod gunluklerini getirir (salt okunur)."""
        return "baglanti hatasi: password=CokGizli123"

    result = await pod_gunlukleri(ctx, environment="test")
    assert "CokGizli123" not in result


async def test_audit_parameters_are_redacted(ctx: ToolContext, audit: MemoryAuditSink) -> None:
    @readonly_tool(category="grafana")
    async def panel_getir(ctx: ToolContext, environment: str, api_key: str) -> str:
        """Panel bilgisini getirir (salt okunur)."""
        return "panel"

    await panel_getir(ctx, environment="test", api_key="gizli-anahtar")
    assert "gizli-anahtar" not in str(audit.events[0].parameters)


async def test_policy_refusal_becomes_a_readable_observation(
    ctx: ToolContext, audit: MemoryAuditSink
) -> None:
    """A refusal is an answer, not a crash: the model should read and reroute."""

    @readonly_tool(category="k8s")
    async def pod_gunlukleri(ctx: ToolContext, environment: str, namespace: str) -> str:
        """Pod gunluklerini getirir (salt okunur)."""
        ctx.policy.assert_allowed(environment=environment, namespace=namespace)
        return "gunlukler"

    result = await pod_gunlukleri(ctx, environment="test", namespace="kube-system")

    assert "Erişim reddedildi" in result
    assert audit.events[0].ok is False
    assert audit.events[0].error is not None


async def test_unexpected_error_is_audited_and_reraised(
    ctx: ToolContext, audit: MemoryAuditSink
) -> None:
    @readonly_tool(category="k8s")
    async def bozuk_arac(ctx: ToolContext, environment: str) -> str:
        """Kasitli olarak hata firlatir (test)."""
        raise RuntimeError("baglanti koptu")

    with pytest.raises(RuntimeError, match="baglanti koptu"):
        await bozuk_arac(ctx, environment="test")

    assert audit.events[0].ok is False
    assert "baglanti koptu" in str(audit.events[0].error)


async def test_long_output_is_trimmed(ctx: ToolContext) -> None:
    @readonly_tool(category="elastic", max_chars=200)
    async def log_ara(ctx: ToolContext, environment: str) -> str:
        """Log arar (salt okunur)."""
        return "satir\n" * 500

    result = await log_ara(ctx, environment="test")
    assert "çıktı kırpıldı" in result


# --- definition-time contract ------------------------------------------


def test_state_changing_name_is_rejected_at_definition() -> None:
    with pytest.raises(ReadOnlyToolError, match="salt okunur"):

        @readonly_tool(category="k8s")
        async def delete_pod(ctx: ToolContext, environment: str) -> str:
            """Pod siler."""
            return ""


def test_missing_ctx_parameter_is_rejected() -> None:
    with pytest.raises(ReadOnlyToolError, match="ctx"):

        @readonly_tool(category="k8s")
        async def pod_listesi(environment: str) -> str:
            """Pod listesini getirir."""
            return ""


def test_missing_docstring_is_rejected() -> None:
    """The model picks tools by their Turkish docstring, so it is mandatory."""
    with pytest.raises(ReadOnlyToolError, match="docstring"):

        @readonly_tool(category="k8s")
        async def pod_listesi(ctx: ToolContext, environment: str) -> str:
            return ""


def test_sync_function_is_rejected() -> None:
    with pytest.raises(ReadOnlyToolError, match="async"):

        @readonly_tool(category="k8s")  # type: ignore[arg-type]
        def pod_listesi(ctx: ToolContext, environment: str) -> str:
            """Pod listesini getirir."""
            return ""


# --- budget -------------------------------------------------------------


async def test_budget_stops_runaway_investigation(audit: MemoryAuditSink) -> None:
    ctx = ToolContext(audit=audit, budget=ToolBudgetState(max_calls=2, max_cost=99))

    @readonly_tool(category="k8s")
    async def pod_listesi(ctx: ToolContext, environment: str) -> str:
        """Pod listesini getirir (salt okunur)."""
        return "ok"

    await pod_listesi(ctx, environment="test")
    await pod_listesi(ctx, environment="test")
    result = await pod_listesi(ctx, environment="test")

    assert "bütçesi doldu" in result


def test_budget_charges_by_cost() -> None:
    budget = ToolBudgetState(max_calls=10, max_cost=5)
    budget.charge(int(ToolBudget.MODERATE))
    with pytest.raises(PolicyError, match="maliyeti"):
        budget.charge(int(ToolBudget.EXPENSIVE))


# --- read-only HTTP client ---------------------------------------------


async def test_post_always_raises() -> None:
    client = ReadOnlyHttpClient("https://elastic.local")
    with pytest.raises(ReadOnlyViolationError, match="salt okunur"):
        await client.post("/anything")
    await client.aclose()


async def test_search_rejects_non_search_paths() -> None:
    client = ReadOnlyHttpClient("https://elastic.local")
    with pytest.raises(ReadOnlyViolationError, match="arama uç noktalarında"):
        await client.search("/my-index/_delete_by_query", body={})
    await client.aclose()


async def test_get_reaches_the_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(200, json={"count": 3})

    client = ReadOnlyHttpClient("https://elastic.local", transport=httpx.MockTransport(handler))
    async with client:
        response = await client.get("/app-msube-2026/_count")
        assert response.json() == {"count": 3}


async def test_search_post_is_allowed_for_elasticsearch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/_search")
        return httpx.Response(200, json={"hits": {"total": {"value": 1}}})

    client = ReadOnlyHttpClient("https://elastic.local", transport=httpx.MockTransport(handler))
    async with client:
        response = await client.search("/app-msube-2026/_search", body={"size": 1})
        assert response.status_code == 200


async def test_request_cannot_leave_the_configured_host() -> None:
    client = ReadOnlyHttpClient("https://elastic.local")
    with pytest.raises(ReadOnlyViolationError, match="dışına çıkıyor"):
        await client.get("https://attacker.example/steal")
    await client.aclose()


# --- summarize ----------------------------------------------------------


def test_short_output_is_untouched() -> None:
    assert summarize_output("kisa cikti") == "kisa cikti"


def test_line_limit_reports_the_total() -> None:
    result = summarize_output("satir\n" * 50, max_lines=10)
    assert "toplam 50 satır" in result
    assert "ilk 10 satır" in result


def test_character_limit_is_a_hard_ceiling() -> None:
    result = summarize_output("x" * 5000, max_chars=100)
    assert "çıktı kırpıldı" in result
    assert result.count("x") == 100


def test_table_renders_rows() -> None:
    table = format_table([{"pod": "msube-web-1", "durum": "Running"}], columns=["pod", "durum"])
    assert "msube-web-1" in table
    assert "durum" in table


def test_table_handles_empty_result() -> None:
    assert format_table([], columns=["pod"]) == "(sonuç yok)"
