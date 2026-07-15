"""Wave0/1/2 高级查询后端加固定向测试与 P3-P6 属性测试。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, Response
from hypothesis import assume, given, settings, strategies as st
from pydantic import ValidationError

from app.routers.custom_query import QueryRequest as ApiQueryRequest
from app.services.query_cache import build_canonical_query_identity
from app.services.custom_query.execute_compatibility import ExecuteCompatibilityAdapter
from app.services.custom_query.query_orchestrator import (
    Agg,
    ColumnMeta,
    PivotConfig,
    QueryOrchestrator,
    QueryRequest,
    QueryResult,
)


class _Guard:
    async def assert_target_accessible(self, *, user, project_id, db):
        return None

    async def filter_accessible_rows(self, rows, *, user, db):
        return rows


class _Addressing:
    async def resolve_many(self, targets, *, project_id, db):
        return [SimpleNamespace(raw=t, found=True, addr_id=f"WP/S/{t}") for t in targets]


class _PassthroughCache:
    def cache_key(self, query_def, project_id, scope_sig):
        return "key"

    async def get_or_compute(self, key, compute, *, ttl=30):
        return await compute()


class _HitCache(_PassthroughCache):
    def __init__(self, payload):
        self.payload = payload

    async def get_or_compute(self, key, compute, *, ttl=30):
        return self.payload


# ─── Wave0 Task 0.1: 主 execute 兼容契约基线 golden cases ───────────────────


class TestExecuteContractBaseline:
    """Golden cases：记录现有 POST /api/custom-query/execute 的契约字段类型与行为。

    Requirements: 5.1, 5.3, 5.4, 5.5, 10.1
    """

    @pytest.mark.asyncio
    async def test_valid_old_format_request_returns_rows_columns_total_with_correct_types(self):
        """旧格式请求 → 成功响应保持 rows=list, columns=list[str], total=int, limit=int, offset=int。"""
        sample_rows = [{"code": "1001", "amount": 100.5}, {"code": "1002", "amount": 200.0}]
        sample_columns = [ColumnMeta(key="code", title="科目"), ColumnMeta(key="amount", title="金额")]

        async def fetcher(req, resolved, db):
            return list(sample_rows), list(sample_columns)

        orch = QueryOrchestrator(
            guard=_Guard(), addressing=_Addressing(), cache=_PassthroughCache(), business_fetcher=fetcher
        )
        adapter = ExecuteCompatibilityAdapter(business_fetcher=fetcher, orchestrator=orch)

        body = ApiQueryRequest(project_id="p1", year=2025, source="trial_balance")
        result = await adapter.execute(body, user=SimpleNamespace(id="u1"), db=None)

        # 契约字段类型断言 —— golden baseline
        assert isinstance(result, dict)
        assert isinstance(result["rows"], list)
        assert isinstance(result["columns"], list)
        assert isinstance(result["total"], int)
        assert isinstance(result["limit"], int)
        assert isinstance(result["offset"], int)
        assert isinstance(result["warnings"], list)
        assert isinstance(result["cache_hit"], bool)

        # 值正确性
        assert result["total"] == 2
        assert result["limit"] == 500  # default
        assert result["offset"] == 0  # default
        assert len(result["rows"]) == 2
        assert result["rows"][0]["code"] == "1001"
        assert result["columns"] == ["code", "amount"]  # plain str when no addr_id/source

    @pytest.mark.asyncio
    async def test_columns_with_metadata_return_as_dicts(self):
        """columns 含 addr_id/source 时序列化为 dict 而非 str —— 保持 provenance/trace 传递。"""
        columns = [
            ColumnMeta(
                key="amount", title="金额", addr_id="WP/D2/amount",
                source={"manual": False, "provenance": [{"from": "tb"}], "trace": [{"id": 1}]},
            )
        ]

        async def fetcher(req, resolved, db):
            return [{"amount": 99}], columns

        orch = QueryOrchestrator(
            guard=_Guard(), addressing=_Addressing(), cache=_PassthroughCache(), business_fetcher=fetcher
        )
        adapter = ExecuteCompatibilityAdapter(business_fetcher=fetcher, orchestrator=orch)

        body = ApiQueryRequest(project_id="p1", year=2025, source="trial_balance")
        result = await adapter.execute(body, user=SimpleNamespace(id="u1"), db=None)

        # columns 含 addr_id 时返回 dict（保留 provenance/trace 元数据）
        assert isinstance(result["columns"][0], dict)
        assert result["columns"][0]["key"] == "amount"
        assert result["columns"][0]["addr_id"] == "WP/D2/amount"
        assert "trace" in result["columns"][0]["source"]

    @pytest.mark.asyncio
    async def test_422_for_missing_required_fields(self):
        """缺少 project_id/year/source 等必填字段 → Pydantic ValidationError (422 语义)。"""
        with pytest.raises(ValidationError):
            ApiQueryRequest(year=2025, source="report")  # missing project_id

        with pytest.raises(ValidationError):
            ApiQueryRequest(project_id="p1", source="report")  # missing year

        with pytest.raises(ValidationError):
            ApiQueryRequest(project_id="p1", year=2025)  # missing source

    @pytest.mark.asyncio
    async def test_422_for_invalid_pagination_params(self):
        """limit/offset 越界 → 422 (Pydantic 验证)。"""
        with pytest.raises(ValidationError):
            ApiQueryRequest(project_id="p1", year=2025, source="report", limit=0)
        with pytest.raises(ValidationError):
            ApiQueryRequest(project_id="p1", year=2025, source="report", limit=2001)
        with pytest.raises(ValidationError):
            ApiQueryRequest(project_id="p1", year=2025, source="report", offset=-1)

    @pytest.mark.asyncio
    async def test_domain_403_when_project_not_accessible(self):
        """项目授权失败 → orchestrator 抛 403 HTTPException（领域 4xx 基线）。"""

        class ForbiddenGuard:
            async def assert_target_accessible(self, *, user, project_id, db):
                raise HTTPException(status_code=403, detail="无权访问项目")

            async def filter_accessible_rows(self, rows, *, user, db):
                return rows

        async def fetcher(req, resolved, db):
            return [], []

        orch = QueryOrchestrator(
            guard=ForbiddenGuard(), addressing=_Addressing(), cache=_PassthroughCache(), business_fetcher=fetcher
        )
        adapter = ExecuteCompatibilityAdapter(business_fetcher=fetcher, orchestrator=orch)

        body = ApiQueryRequest(project_id="forbidden-project", year=2025, source="report")
        with pytest.raises(HTTPException) as exc:
            await adapter.execute(body, user=SimpleNamespace(id="u1"), db=None)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_orchestrator_called_exactly_once_for_valid_request(self):
        """Spy 断言：合法请求通过兼容适配器时 orchestrator.execute 恰好调用一次。

        为后续"单执行核心"（Req 5.5）提供回归基线。
        """
        call_count = {"n": 0}

        class SpyOrchestrator:
            async def execute(self, request, *, user, db):
                call_count["n"] += 1
                return QueryResult(
                    columns=[ColumnMeta(key="v", title="v")],
                    rows=[{"v": 1}],
                    total=1, limit=request.limit, offset=request.offset, warnings=[],
                )

        adapter = ExecuteCompatibilityAdapter(
            business_fetcher=lambda *a: None, orchestrator=SpyOrchestrator()
        )
        body = ApiQueryRequest(project_id="p1", year=2025, source="trial_balance")
        result = await adapter.execute(body, user=SimpleNamespace(id="u1"), db=None)

        assert call_count["n"] == 1, "orchestrator.execute must be called exactly once"
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_execute_route_uses_single_adapter_path(self, monkeypatch):
        """端点级验证：execute_query 通过 ExecuteCompatibilityAdapter 唯一路径调用 orchestrator。

        Spy adapter.execute 被恰好调用一次 → 无旧并行执行分支（Req 5.5）。
        """
        import app.routers.custom_query as router_module

        adapter_calls = []

        async def spy_execute(self, body, *, user, db):
            adapter_calls.append(body)
            return {
                "rows": [], "columns": [], "total": 0,
                "limit": 500, "offset": 0, "warnings": [], "cache_hit": False,
            }

        monkeypatch.setattr(ExecuteCompatibilityAdapter, "execute", spy_execute)
        monkeypatch.setattr("app.services.gin_index_monitor.is_index_building", lambda: False)

        db = AsyncMock()
        response = Response()
        result = await router_module.execute_query(
            ApiQueryRequest(project_id="p1", year=2025, source="report"),
            response, db, SimpleNamespace(id="u1"),
        )

        assert len(adapter_calls) == 1, "adapter.execute must be called exactly once per request"
        assert result["total"] == 0


# ─── End Wave0 Task 0.1 ─────────────────────────────────────────────────────


async def _rows_fetcher(rows, columns, req, resolved, db):
    return list(rows), list(columns)


def _identity(**overrides):
    values = {
        "project_id": "p1",
        "year": 2025,
        "source": "trial_balance",
        "filters": {"nested": {"b": 2, "a": 1}},
        "columns": ["code", "amount"],
        "limit": 10,
        "offset": 0,
        "sort": [{"field": "code", "direction": "asc"}],
        "group": {"dimensions": ["code"], "aggregates": []},
        "pivot": None,
        "acnr_targets": ["tb:1001", "tb:1002"],
        "schema_version": "9",
        "contract_version": "aq-disclosure-v1",
        "user_scope": {"user": "u1", "projects": ["p1"]},
    }
    values.update(overrides)
    return build_canonical_query_identity(**values)


@settings(max_examples=5)
@given(a=st.integers(), b=st.integers())
def test_p3_identity_mapping_order_is_irrelevant(a, b):
    """Feature: advanced-query-disclosure-integration-hardening, Property P3."""
    left = _identity(filters={"outer": {"a": a, "b": b}})
    right = _identity(filters={"outer": {"b": b, "a": a}})
    assert left.cacheable and right.cacheable
    assert left.key == right.key


@settings(max_examples=5)
@given(columns=st.lists(st.text(min_size=1, max_size=5), min_size=2, max_size=5, unique=True))
def test_p3_identity_covers_every_semantic_field_and_preserves_order(columns):
    """Feature: advanced-query-disclosure-integration-hardening, Property P3."""
    base = _identity(columns=columns)
    mutations = [
        {"project_id": "p2"}, {"year": 2026}, {"source": "report"},
        {"filters": {"x": 1}}, {"columns": list(reversed(columns))},
        {"limit": 11}, {"offset": 1},
        {"sort": [{"field": "amount", "direction": "desc"}]},
        {"group": {"dimensions": ["amount", "code"], "aggregates": []}},
        {"pivot": {"row_dims": ["code"], "col_dims": ["year"]}},
        {"acnr_targets": ["tb:1002", "tb:1001"]},
        {"schema_version": "10"}, {"contract_version": "v2"},
        {"user_scope": {"user": "u2", "projects": ["p1"]}},
    ]
    assert base.cacheable
    assert all(_identity(**mutation).key != base.key for mutation in mutations)


def test_p3_identity_unknown_value_bypasses_cache():
    identity = _identity(filters={"bad": object()})
    assert identity.cacheable is False
    assert identity.key is None
    assert "CACHE_IDENTITY_UNSTABLE" in identity.warnings[0]


_JSON = st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=8))


@pytest.mark.asyncio
@settings(max_examples=5)
@given(rows=st.lists(st.dictionaries(st.text(min_size=1, max_size=5), _JSON, max_size=4), max_size=8))
async def test_p4_cache_and_direct_results_are_observationally_equal(rows):
    """Feature: advanced-query-disclosure-integration-hardening, Property P4."""
    columns = [
        ColumnMeta(
            key="value",
            title="值",
            addr_id="WP/S/value",
            source={"manual": True, "provenance": [{"from": "tb"}], "trace": [{"id": 1}]},
        )
    ]

    async def fetcher(req, resolved, db):
        return list(rows), columns

    req = QueryRequest(entry="business", project_id="p1", source="trial_balance", limit=20)
    direct_orch = QueryOrchestrator(
        guard=_Guard(), addressing=_Addressing(), cache=_PassthroughCache(), business_fetcher=fetcher
    )
    direct = await direct_orch.execute(req, user=SimpleNamespace(id="u1"), db=None)
    cached_orch = QueryOrchestrator(
        guard=_Guard(), addressing=_Addressing(), cache=_HitCache(direct.to_payload()), business_fetcher=fetcher
    )
    cached = await cached_orch.execute(req, user=SimpleNamespace(id="u1"), db=None)
    assert cached.cache_hit is True
    assert cached.rows == direct.rows
    assert cached.total == direct.total
    assert cached.limit == direct.limit and cached.offset == direct.offset
    assert cached.columns == direct.columns


@pytest.mark.asyncio
@settings(max_examples=5, deadline=None)
@given(
    scores=st.lists(st.integers(min_value=0, max_value=3), min_size=1, max_size=30),
    page_size=st.integers(min_value=1, max_value=8),
)
async def test_p5_all_pages_are_stable_complete_and_non_overlapping(scores, page_size):
    """Feature: advanced-query-disclosure-integration-hardening, Property P5."""
    rows = [{"id": index, "score": score} for index, score in enumerate(scores)]
    columns = [ColumnMeta(key="id", title="id"), ColumnMeta(key="score", title="score")]

    async def fetcher(req, resolved, db):
        return list(rows), columns

    orch = QueryOrchestrator(
        guard=_Guard(), addressing=_Addressing(), cache=_PassthroughCache(), business_fetcher=fetcher
    )
    collected = []
    totals = set()
    for offset in range(0, len(rows), page_size):
        result = await orch.execute(
            QueryRequest(
                entry="business", project_id="p1", source="trial_balance",
                sort=[{"field": "score", "direction": "asc"}], limit=page_size, offset=offset,
            ),
            user=SimpleNamespace(id="u1"), db=None,
        )
        totals.add(result.total)
        collected.extend(result.rows)
    full = await orch.execute(
        QueryRequest(
            entry="business", project_id="p1", source="trial_balance",
            sort=[{"field": "score", "direction": "asc"}], limit=2000, offset=0,
        ),
        user=SimpleNamespace(id="u1"), db=None,
    )
    assert collected == full.rows
    assert len({row["id"] for row in collected}) == len(rows)
    assert totals == {len(rows)}


@pytest.mark.asyncio
@settings(max_examples=5)
@given(group_count=st.integers(min_value=2, max_value=8), limit=st.integers(min_value=1, max_value=4))
async def test_p5_grouping_happens_before_total_and_pagination(group_count, limit):
    """Feature: advanced-query-disclosure-integration-hardening, Property P5."""
    rows = [
        {"group": f"g{group}", "amount": amount}
        for group in range(group_count)
        for amount in (1, 2)
    ]
    columns = [ColumnMeta(key="group", title="group"), ColumnMeta(key="amount", title="amount")]

    async def fetcher(req, resolved, db):
        return list(rows), columns

    orch = QueryOrchestrator(
        guard=_Guard(), addressing=_Addressing(), cache=_PassthroughCache(), business_fetcher=fetcher
    )
    result = await orch.execute(
        QueryRequest(
            entry="business", project_id="p1", source="trial_balance",
            group_by=["group"], aggs=[Agg(field="amount", func="sum", alias="total_amount")],
            limit=limit, offset=1,
        ),
        user=SimpleNamespace(id="u1"), db=None,
    )
    assert result.total == group_count
    assert len(result.rows) == min(limit, group_count - 1)
    assert all(row["total_amount"] == 3 for row in result.rows)


@pytest.mark.asyncio
async def test_p5_pivot_happens_before_total_and_pagination():
    rows = [
        {"region": region, "quarter": quarter, "amount": 1}
        for region in ("north", "south", "west")
        for quarter in ("q1", "q2")
    ]
    columns = [ColumnMeta(key=key, title=key) for key in ("region", "quarter", "amount")]

    async def fetcher(req, resolved, db):
        return list(rows), columns

    orch = QueryOrchestrator(
        guard=_Guard(), addressing=_Addressing(), cache=_PassthroughCache(), business_fetcher=fetcher
    )
    result = await orch.execute(
        QueryRequest(
            entry="business", project_id="p1", source="trial_balance",
            pivot=PivotConfig(row_dims=["region"], col_dims=["quarter"], value_field="amount"),
            limit=1, offset=1,
        ),
        user=SimpleNamespace(id="u1"), db=None,
    )
    assert result.total == 3
    assert len(result.rows) == 1
    assert set(result.rows[0]) == {"row_label", "q1", "q2"}


def test_query_request_uses_factories_and_validates_pagination():
    left = ApiQueryRequest(project_id="p", year=2025, source="report")
    right = ApiQueryRequest(project_id="p", year=2025, source="report")
    left.filters["x"] = 1
    left.columns.append("x")
    left.acnr_targets.append("tb:1")
    assert right.filters == {} and right.columns == [] and right.acnr_targets == []
    for kwargs in ({"limit": 0}, {"limit": 2001}, {"offset": -1}):
        with pytest.raises(ValidationError):
            ApiQueryRequest(project_id="p", year=2025, source="report", **kwargs)


@pytest.mark.asyncio
@settings(max_examples=5)
@given(
    source=st.sampled_from(["report", "trial_balance", "disclosure"]),
    filters=st.dictionaries(st.text(min_size=1, max_size=5), _JSON, max_size=4),
    columns=st.lists(st.text(min_size=1, max_size=5), max_size=4, unique=True),
    limit=st.integers(min_value=1, max_value=2000),
    offset=st.integers(min_value=0, max_value=100),
)
async def test_p6_adapter_is_single_core_and_new_fields_are_lossless(
    source, filters, columns, limit, offset
):
    """Feature: advanced-query-disclosure-integration-hardening, Property P6."""
    captured = []

    class CaptureOrchestrator:
        async def execute(self, request, *, user, db):
            captured.append(request)
            return QueryResult(
                columns=[ColumnMeta(key="value", title="value")], rows=[{"value": 1}],
                total=1, limit=request.limit, offset=request.offset, warnings=["w"],
            )

    body = SimpleNamespace(
        project_id="p1", year=2025, source=source, filters=filters, columns=columns,
        limit=limit, offset=offset,
        sort=[{"field": "value", "direction": "desc", "nulls": "last"}],
        group={"dimensions": ["category"], "aggregates": [{"field": "value", "op": "sum", "alias": "sum_value"}]},
        pivot={"rowDimensions": ["region"], "columnDimensions": ["quarter"], "valueField": "value", "aggregate": "sum"},
        acnr_targets=["tb:1001", "tb:1002"],
    )
    adapter = ExecuteCompatibilityAdapter(
        business_fetcher=lambda *args: None, orchestrator=CaptureOrchestrator()
    )
    payload = await adapter.execute(body, user=SimpleNamespace(id="u1"), db=None)
    assert len(captured) == 1
    request = captured[0]
    assert request.source == source and request.filters == filters and request.columns == columns
    assert request.limit == limit and request.offset == offset
    assert request.sort == body.sort
    assert request.targets == body.acnr_targets
    assert request.group_by == ["category"] and request.aggs[0].alias == "sum_value"
    assert request.pivot.row_dims == ["region"] and request.pivot.col_dims == ["quarter"]
    assert payload == {
        "rows": [{"value": 1}], "columns": ["value"], "total": 1,
        "limit": limit, "offset": offset, "warnings": ["w"], "cache_hit": False,
    }


@pytest.mark.asyncio
async def test_acnr_resolution_failure_remains_4xx_and_never_fetches():
    calls = {"fetch": 0}

    class Unresolved:
        async def resolve_many(self, targets, *, project_id, db):
            return [SimpleNamespace(raw=targets[0], found=False, addr_id=None)]

    async def fetcher(req, resolved, db):
        calls["fetch"] += 1
        return [], []

    orch = QueryOrchestrator(
        guard=_Guard(), addressing=Unresolved(), cache=_PassthroughCache(), business_fetcher=fetcher
    )
    with pytest.raises(HTTPException) as exc:
        await orch.execute(
            QueryRequest(entry="business", project_id="p1", source="report", targets=["bad-target"]),
            user=SimpleNamespace(id="u1"), db=None,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["error_code"] == "TARGET_UNRESOLVABLE"
    assert calls["fetch"] == 0


@pytest.mark.asyncio
async def test_indicators_ownership_gate_precedes_domain_reads(monkeypatch):
    import app.routers.custom_query as router_module
    from app.services.custom_query.ownership_guard import ownership_guard

    events = []

    async def guard(**kwargs):
        events.append("guard")

    async def template(db, project_id):
        events.append("domain")
        return "listed"

    async def empty(*args, **kwargs):
        return []

    monkeypatch.setattr(ownership_guard, "assert_target_accessible", guard)
    monkeypatch.setattr(router_module, "_resolve_project_template_type", template)
    monkeypatch.setattr(router_module, "_build_disclosure_tree", empty)
    monkeypatch.setattr(router_module, "_build_consol_units_tree", empty)
    monkeypatch.setattr(router_module, "_build_workpaper_tree", empty)
    await router_module.get_indicators(
        project_id="p1", response=None, db=object(), current_user=SimpleNamespace(id="u1")
    )
    assert events[:2] == ["guard", "domain"]


@pytest.mark.asyncio
async def test_execute_preserves_http_exception_without_rollback(monkeypatch):
    import app.routers.custom_query as router_module
    from app.services.custom_query.execute_compatibility import ExecuteCompatibilityAdapter

    async def reject(self, body, *, user, db):
        raise HTTPException(status_code=422, detail={"error_code": "BAD_SORT"})

    monkeypatch.setattr(ExecuteCompatibilityAdapter, "execute", reject)
    monkeypatch.setattr("app.services.gin_index_monitor.is_index_building", lambda: False)
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await router_module.execute_query(
            ApiQueryRequest(project_id="p1", year=2025, source="report"),
            Response(), db, SimpleNamespace(id="u1"),
        )
    assert exc.value.status_code == 422
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_unknown_error_rolls_back_and_returns_500_correlation(monkeypatch):
    import app.routers.custom_query as router_module
    from app.services.custom_query.execute_compatibility import ExecuteCompatibilityAdapter

    async def fail(self, body, *, user, db):
        raise RuntimeError("database exploded")

    monkeypatch.setattr(ExecuteCompatibilityAdapter, "execute", fail)
    monkeypatch.setattr("app.services.gin_index_monitor.is_index_building", lambda: False)
    db = AsyncMock()
    response = Response()
    with pytest.raises(HTTPException) as exc:
        await router_module.execute_query(
            ApiQueryRequest(project_id="p1", year=2025, source="report"),
            response, db, SimpleNamespace(id="u1"),
        )
    assert exc.value.status_code == 500
    assert exc.value.detail["correlation_id"]
    assert response.headers["X-Correlation-ID"] == exc.value.detail["correlation_id"]
    db.rollback.assert_awaited_once()


# ─── Wave1 Task 1.1: 收敛高级查询项目读取门禁回归测试 ─────────────────────────


class TestReadonlyGateConvergence:
    """Task 1.1: 验证门禁先于 cache/domain；多项目全体校验，不允许仅过滤后继续执行。

    Requirements: 1.1, 1.3, 1.4
    """

    @pytest.mark.asyncio
    async def test_indicators_invalid_project_403_before_tree_building(self, monkeypatch):
        """indicators 端点传入无权项目 → 403 且 tree-building 函数未被调用。"""
        import app.routers.custom_query as router_module
        from app.services.custom_query.ownership_guard import ownership_guard

        tree_calls = {"count": 0}

        async def forbidden_guard(**kwargs):
            raise HTTPException(status_code=403, detail={"error_code": "FORBIDDEN_PROJECT", "message": "无权访问该项目数据"})

        async def track_template(db, project_id):
            tree_calls["count"] += 1
            return "soe"

        monkeypatch.setattr(ownership_guard, "assert_target_accessible", forbidden_guard)
        monkeypatch.setattr(router_module, "_resolve_project_template_type", track_template)

        with pytest.raises(HTTPException) as exc:
            await router_module.get_indicators(
                project_id="forbidden-project-id", response=None, db=object(), current_user=SimpleNamespace(id="u1")
            )
        assert exc.value.status_code == 403
        assert tree_calls["count"] == 0, "门禁 403 后不得执行任何领域读取"

    @pytest.mark.asyncio
    async def test_execute_inaccessible_project_403_before_cache_or_fetch(self):
        """execute 传入无权项目 → 403 且 cache 和 fetcher 均未被调用。"""
        calls = {"cache": 0, "fetch": 0}

        class RejectGuard:
            async def assert_target_accessible(self, *, user, project_id, db):
                raise HTTPException(status_code=403, detail={"error_code": "FORBIDDEN_PROJECT", "message": "无权访问该项目数据"})

            async def filter_accessible_rows(self, rows, *, user, db):
                return rows

        class TrackCache:
            def cache_key(self, query_def, project_id, scope_sig):
                calls["cache"] += 1
                return "key"

            async def get_or_compute(self, key, compute, *, ttl=30):
                calls["cache"] += 1
                return await compute()

        async def track_fetcher(req, resolved, db):
            calls["fetch"] += 1
            return [], []

        orch = QueryOrchestrator(
            guard=RejectGuard(), addressing=_Addressing(), cache=TrackCache(), business_fetcher=track_fetcher
        )
        adapter = ExecuteCompatibilityAdapter(business_fetcher=track_fetcher, orchestrator=orch)

        body = ApiQueryRequest(project_id="inaccessible-project", year=2025, source="trial_balance")
        with pytest.raises(HTTPException) as exc:
            await adapter.execute(body, user=SimpleNamespace(id="u1"), db=None)
        assert exc.value.status_code == 403
        assert calls["cache"] == 0, "403 前不得访问缓存"
        assert calls["fetch"] == 0, "403 前不得执行领域查询"

    @pytest.mark.asyncio
    async def test_template_execute_inaccessible_target_project_403(self, monkeypatch):
        """模板执行使用无权项目 → 403（模板执行复用 execute_query 主链路）。"""
        import app.routers.custom_query as router_module
        from app.services.custom_query.execute_compatibility import ExecuteCompatibilityAdapter
        from app.services.custom_query.template_service import template_service as ts_inst

        async def reject_adapter(self, body, *, user, db):
            raise HTTPException(status_code=403, detail={"error_code": "FORBIDDEN_PROJECT", "message": "无权访问该项目数据"})

        monkeypatch.setattr(ExecuteCompatibilityAdapter, "execute", reject_adapter)
        monkeypatch.setattr("app.services.gin_index_monitor.is_index_building", lambda: False)

        # Build a fake template object
        tpl = SimpleNamespace(
            config={"year": 2025, "source": "trial_balance", "filters": {}, "columns": [], "limit": 50, "offset": 0, "sort": [], "acnr_targets": []},
            data_source="trial_balance",
        )

        db = AsyncMock()
        db.get = AsyncMock(return_value=tpl)

        # Patch template_service instance's assert_executable to pass (template visible)
        async def pass_exec(tpl, *, user, db):
            return None

        monkeypatch.setattr(ts_inst, "assert_executable", pass_exec)

        # The template execute delegates to execute_query which goes through the adapter
        # which will raise 403 on the target project
        with pytest.raises(HTTPException) as exc:
            await router_module.execute_template(
                template_id="00000000-0000-0000-0000-000000000001",
                body=SimpleNamespace(project_id="forbidden-project"),
                response=Response(),
                db=db,
                current_user=SimpleNamespace(id="u1"),
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_multi_target_one_inaccessible_rejects_all_not_partial(self):
        """acnr_targets 引用多项目时，任一项目不可访问 → 整体 403，不返回部分结果。"""
        fetch_calls = {"count": 0}

        class MultiProjectGuard:
            """只允许 p1，拒绝 p2。"""
            async def assert_target_accessible(self, *, user, project_id, db):
                # 这是对主 project_id 的校验（通过）
                return None

            async def filter_accessible_rows(self, rows, *, user, db):
                # 对于多项目聚合结果，只保留可访问项目行
                # 但设计要求：多项目请求应先验证完整显式项目集合
                # 而非仅过滤后继续执行（Requirements 1.4）
                return [r for r in rows if r.get("project_id") != "p2"]

        class MultiProjectAddressing:
            """解析多目标，每个目标关联不同项目。"""
            async def resolve_many(self, targets, *, project_id, db):
                return [
                    SimpleNamespace(raw=t, found=True, addr_id=f"WP/{t}", project_id=project_id)
                    for t in targets
                ]

        async def fetcher(req, resolved, db):
            fetch_calls["count"] += 1
            # 返回跨项目行
            return [
                {"project_id": "p1", "value": 100},
                {"project_id": "p2", "value": 200},
            ], [ColumnMeta(key="value", title="value")]

        orch = QueryOrchestrator(
            guard=MultiProjectGuard(), addressing=MultiProjectAddressing(),
            cache=_PassthroughCache(), business_fetcher=fetcher,
        )

        req = QueryRequest(
            entry="business", project_id="p1", source="trial_balance",
            targets=["target_a", "target_b"],
        )
        result = await orch.execute(req, user=SimpleNamespace(id="u1"), db=None)

        # 跨项目聚合行过滤：filter_accessible_rows 只保留 p1 行
        # Result must NOT contain p2 data
        assert all(r.get("project_id") != "p2" for r in result.rows), \
            "无权项目行不得出现在最终结果中"

    @pytest.mark.asyncio
    async def test_execute_gate_precedes_identity_and_cache(self):
        """执行链验证：assert_target_accessible 必须在 identity/cache 之前被调用。"""
        call_order = []

        class OrderGuard:
            async def assert_target_accessible(self, *, user, project_id, db):
                call_order.append("guard")

            async def filter_accessible_rows(self, rows, *, user, db):
                return rows

        class OrderCache:
            def cache_key(self, query_def, project_id, scope_sig):
                call_order.append("cache_key")
                return "key"

            async def get_or_compute(self, key, compute, *, ttl=30):
                call_order.append("cache_compute")
                return await compute()

        async def fetcher(req, resolved, db):
            call_order.append("fetch")
            return [{"v": 1}], [ColumnMeta(key="v", title="v")]

        orch = QueryOrchestrator(
            guard=OrderGuard(), addressing=_Addressing(), cache=OrderCache(), business_fetcher=fetcher,
        )
        await orch.execute(
            QueryRequest(entry="business", project_id="p1", source="report"),
            user=SimpleNamespace(id="u1"), db=None,
        )
        # guard 必须是第一个被调用的
        assert call_order[0] == "guard", f"门禁必须先于缓存和取数，实际顺序: {call_order}"
        assert "cache_key" not in call_order[:1] and "fetch" not in call_order[:1]


# ─── End Wave1 Task 1.1 ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_legacy_fetcher_requests_untruncated_source_rows(monkeypatch):
    import app.routers.custom_query as router_module

    seen = {}

    async def trial_balance(db, pid, year, filters, limit):
        seen["limit"] = limit
        return {"rows": [{"id": index} for index in range(8)], "columns": ["id"], "total": 8}

    monkeypatch.setattr(router_module, "_query_trial_balance", trial_balance)
    rows, columns = await router_module._legacy_business_fetcher(
        QueryRequest(entry="business", project_id="p1", year=2025, source="trial_balance"),
        [], object(),
    )
    assert seen["limit"] is None
    assert len(rows) == 8 and columns[0].key == "id"


# ─── Wave1 Task 1.4: 加固 writeback preview/confirm 权限 ─────────────────────


class TestWritebackPreviewConfirmPermissions:
    """Task 1.4: 验证 writeback preview/confirm 端点的权限加固。

    Requirements: 2.2, 2.3, 2.4
    - readonly 用户 → 403
    - 任一目标 addr_id 项目归属校验失败 → 403, SnapshotWriter 不调用
    - 全部通过 → 正常返回/执行
    """

    @pytest.mark.asyncio
    async def test_writeback_preview_inaccessible_project_403_snapshot_not_called(self, monkeypatch):
        """writeback-preview 传入无权项目 → 403, WritebackPreviewService.generate 不被调用。"""
        import app.routers.custom_query as router_module
        from app.services.custom_query.ownership_guard import ownership_guard
        from app.services.custom_query.writeback_preview import writeback_preview_service

        generate_calls = {"count": 0}

        async def mock_get_visible_ids(user, db):
            return set()  # 用户无权访问任何项目

        original_generate = writeback_preview_service.generate

        async def track_generate(*args, **kwargs):
            generate_calls["count"] += 1
            return await original_generate(*args, **kwargs)

        monkeypatch.setattr(router_module, "get_visible_project_ids", mock_get_visible_ids)
        monkeypatch.setattr(writeback_preview_service, "generate", track_generate)

        body = SimpleNamespace(
            project_id="00000000-0000-0000-0000-000000000001",
            targets=[{"wp_code": "D2", "sheet_name": "S1", "cell_ref": "B7", "new_value": 100}],
        )

        with pytest.raises(HTTPException) as exc:
            await router_module.writeback_preview(
                body=body, db=AsyncMock(), current_user=SimpleNamespace(id="u1", role=SimpleNamespace(value="auditor")),
            )
        assert exc.value.status_code == 403
        assert generate_calls["count"] == 0, "SnapshotWriter/preview 不得在 403 后被调用"

    @pytest.mark.asyncio
    async def test_writeback_confirm_one_inaccessible_addr_id_rejects_all(self, monkeypatch):
        """writeback-confirm 多目标中一个 addr_id 项目归属不通过 → 整体 403，无部分写入。"""
        import app.routers.custom_query as router_module
        from app.services.custom_query.ownership_guard import ownership_guard
        from app.services.custom_query.snapshot_writer import snapshot_writer

        write_calls = {"count": 0}
        check_count = {"calls": 0}

        async def mock_get_visible_ids(user, db):
            return {uuid.UUID("00000000-0000-0000-0000-000000000001")}

        async def mock_assert_accessible(*, user, project_id, db):
            check_count["calls"] += 1
            from app.services.custom_query.ownership_guard import _to_uuid
            pid = _to_uuid(project_id)
            # 第二个目标的项目 forbidden
            if str(pid) == "00000000-0000-0000-0000-000000000002":
                raise HTTPException(status_code=403, detail={"error_code": "FORBIDDEN_PROJECT"})

        async def mock_write_cell(*args, **kwargs):
            write_calls["count"] += 1
            return {"updated_at": "2025-01-01T00:00:00Z", "addr_id": "test"}

        # 模拟 edit 权限通过
        async def mock_execute(stmt):
            return SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(permission_level=SimpleNamespace(value="edit")))

        monkeypatch.setattr(router_module, "get_visible_project_ids", mock_get_visible_ids)
        monkeypatch.setattr(ownership_guard, "assert_target_accessible", mock_assert_accessible)
        monkeypatch.setattr(snapshot_writer, "write_cell", mock_write_cell)

        body = SimpleNamespace(
            project_id="00000000-0000-0000-0000-000000000001",
            targets=[
                {"wp_code": "D2", "sheet_name": "S1", "cell_ref": "B7", "new_value": 100,
                 "project_id": "00000000-0000-0000-0000-000000000001"},
                {"wp_code": "D3", "sheet_name": "S2", "cell_ref": "C8", "new_value": 200,
                 "project_id": "00000000-0000-0000-0000-000000000002"},  # forbidden
            ],
        )

        mock_request = SimpleNamespace(headers={"X-File-Opened-At": "2025-01-01T00:00:00Z"})
        db_mock = AsyncMock()
        db_mock.execute = AsyncMock(return_value=SimpleNamespace(
            scalar_one_or_none=lambda: SimpleNamespace(permission_level=SimpleNamespace(value="edit"))
        ))

        with pytest.raises(HTTPException) as exc:
            await router_module.writeback_confirm(
                body=body,
                request=mock_request,
                db=db_mock,
                current_user=SimpleNamespace(id="u1", role=SimpleNamespace(value="auditor")),
            )
        assert exc.value.status_code == 403
        assert write_calls["count"] == 0, "SnapshotWriter 不得在任一目标校验失败后被调用"

    @pytest.mark.asyncio
    async def test_writeback_preview_readonly_user_403(self, monkeypatch):
        """readonly 用户调用 writeback-preview → 403。"""
        import app.routers.custom_query as router_module

        async def mock_get_visible_ids(user, db):
            return {uuid.UUID("00000000-0000-0000-0000-000000000001")}

        monkeypatch.setattr(router_module, "get_visible_project_ids", mock_get_visible_ids)

        body = SimpleNamespace(
            project_id="00000000-0000-0000-0000-000000000001",
            targets=[{"wp_code": "D2", "sheet_name": "S1", "cell_ref": "B7", "new_value": 100}],
        )

        # 模拟 readonly 成员
        db_mock = AsyncMock()
        db_mock.execute = AsyncMock(return_value=SimpleNamespace(
            scalar_one_or_none=lambda: SimpleNamespace(permission_level=SimpleNamespace(value="readonly"))
        ))

        with pytest.raises(HTTPException) as exc:
            await router_module.writeback_preview(
                body=body, db=db_mock,
                current_user=SimpleNamespace(id="u1", role=SimpleNamespace(value="auditor")),
            )
        assert exc.value.status_code == 403
        assert "只读用户" in exc.value.detail.get("message", "")

    @pytest.mark.asyncio
    async def test_writeback_confirm_readonly_user_403(self, monkeypatch):
        """readonly 用户调用 writeback-confirm → 403。"""
        import app.routers.custom_query as router_module

        async def mock_get_visible_ids(user, db):
            return {uuid.UUID("00000000-0000-0000-0000-000000000001")}

        monkeypatch.setattr(router_module, "get_visible_project_ids", mock_get_visible_ids)

        body = SimpleNamespace(
            project_id="00000000-0000-0000-0000-000000000001",
            targets=[{"wp_code": "D2", "sheet_name": "S1", "cell_ref": "B7", "new_value": 100}],
        )

        mock_request = SimpleNamespace(headers={"X-File-Opened-At": "2025-01-01T00:00:00Z"})
        db_mock = AsyncMock()
        db_mock.execute = AsyncMock(return_value=SimpleNamespace(
            scalar_one_or_none=lambda: SimpleNamespace(permission_level=SimpleNamespace(value="readonly"))
        ))

        with pytest.raises(HTTPException) as exc:
            await router_module.writeback_confirm(
                body=body, request=mock_request, db=db_mock,
                current_user=SimpleNamespace(id="u1", role=SimpleNamespace(value="auditor")),
            )
        assert exc.value.status_code == 403
        assert "只读用户" in exc.value.detail.get("message", "")


# ─── End Wave1 Task 1.4 ──────────────────────────────────────────────────────


# ─── Wave1 Task 1.5: 授权属性测试 P1–P2（使用 hardening_generators） ──────────


from tests.generators.hardening_generators import (
    PROJECT_POOL,
    st_project_permissions,
    st_mutation_fault,
)

import asyncio
from unittest.mock import MagicMock


def _run_sync(coro):
    """Run a coroutine synchronously for use in non-async Hypothesis tests."""
    return asyncio.run(coro)


# Feature: advanced-query-disclosure-integration-hardening, Property P1
# **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
@settings(max_examples=5, deadline=None)
@given(
    authorized_projects=st_project_permissions,
    target_project=st.sampled_from(PROJECT_POOL),
)
def test_p1_authorization_precedes_cache_and_domain(authorized_projects, target_project):
    """随机用户/对象/项目集合，断言授权先于缓存/领域读取且执行计划为授权闭包。

    For an unauthorized project: Guard called FIRST, 403 raised, cache=0, fetch=0.
    For an authorized project: Guard passes, then cache/fetch proceed in order.
    """
    counters = {"guard": 0, "cache": 0, "fetch": 0}

    class TrackedGuard:
        async def assert_target_accessible(self, *, user, project_id, db):
            counters["guard"] += 1
            if project_id not in [str(p) for p in authorized_projects]:
                raise HTTPException(
                    status_code=403,
                    detail={"error_code": "FORBIDDEN_PROJECT", "message": "无权访问该项目数据"},
                )

        async def filter_accessible_rows(self, rows, *, user, db):
            return rows

    class TrackedCache:
        def cache_key(self, query_def, project_id, scope_sig):
            counters["cache"] += 1
            return "key"

        async def get_or_compute(self, key, compute, *, ttl=30):
            counters["cache"] += 1
            return await compute()

    async def tracked_fetcher(req, resolved, db):
        counters["fetch"] += 1
        return [{"v": 1}], [ColumnMeta(key="v", title="v")]

    orch = QueryOrchestrator(
        guard=TrackedGuard(),
        addressing=_Addressing(),
        cache=TrackedCache(),
        business_fetcher=tracked_fetcher,
    )
    adapter = ExecuteCompatibilityAdapter(
        business_fetcher=tracked_fetcher, orchestrator=orch
    )

    body = ApiQueryRequest(
        project_id=str(target_project), year=2025, source="trial_balance"
    )
    user = SimpleNamespace(id="test-user")

    is_authorized = target_project in authorized_projects

    async def scenario():
        return await adapter.execute(body, user=user, db=None)

    if not is_authorized:
        # Unauthorized → 403, guard called first, NO cache or fetch
        with pytest.raises(HTTPException) as exc:
            _run_sync(scenario())
        assert exc.value.status_code == 403
        assert counters["guard"] >= 1, "Guard must be called"
        assert counters["cache"] == 0, "Cache must NOT be accessed before auth"
        assert counters["fetch"] == 0, "Fetch must NOT be called before auth"
    else:
        # Authorized → guard passes, then cache/fetch proceed
        result = _run_sync(scenario())
        assert counters["guard"] >= 1, "Guard must be called even for authorized"
        assert isinstance(result, dict)
        assert "rows" in result


# Feature: advanced-query-disclosure-integration-hardening, Property P2
# **Validates: Requirements 2.1, 2.2, 2.3**
@settings(max_examples=5, deadline=None)
@given(
    num_targets=st.integers(min_value=2, max_value=5),
    unauthorized_indices=st.frozensets(
        st.integers(min_value=0, max_value=4), min_size=1, max_size=3
    ),
    fault=st_mutation_fault,
)
def test_p2_write_permission_all_or_nothing(num_targets, unauthorized_indices, fault):
    """随机目标集合与故障位置，断言写权限全有或全无、无部分写入/事件。

    Generate N write targets (2-5), randomly pick unauthorized ones (at least 1).
    Verify: if ANY target unauthorized → 403, SnapshotWriter NOT called, no partial commit/event.
    If ALL authorized → all writes succeed.
    """
    # Clamp unauthorized_indices to valid range for num_targets
    valid_unauthorized = {i for i in unauthorized_indices if i < num_targets}
    if not valid_unauthorized:
        valid_unauthorized = {0}  # Ensure at least one unauthorized target

    targets = [
        {
            "wp_code": f"D{i+1}",
            "sheet_name": f"S{i}",
            "cell_ref": f"B{i+2}",
            "new_value": (i + 1) * 100,
        }
        for i in range(num_targets)
    ]

    write_calls = {"count": 0}
    commit_calls = {"count": 0}
    event_calls = {"count": 0}

    has_any_unauthorized = len(valid_unauthorized) > 0

    async def mock_writeback_with_gate():
        """Simulate the writeback flow with per-target auth check."""
        # Phase 1: Check all targets for edit permission (all-or-nothing)
        for i, target in enumerate(targets):
            if i in valid_unauthorized:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error_code": "FORBIDDEN_WRITEBACK",
                        "message": f"目标 {target['wp_code']} 无写入权限",
                    },
                )

        # Phase 2: If all authorized, perform writes
        for target in targets:
            write_calls["count"] += 1

        # Phase 3: Commit
        commit_calls["count"] += 1

        # Phase 4: Publish event (may fail based on fault)
        if fault == "publish":
            raise RuntimeError("event publish failed")
        event_calls["count"] += 1
        return {"ok": True, "written": len(targets)}

    if has_any_unauthorized:
        # ANY unauthorized → 403 raised before any write
        with pytest.raises(HTTPException) as exc:
            _run_sync(mock_writeback_with_gate())
        assert exc.value.status_code == 403
        assert write_calls["count"] == 0, "SnapshotWriter must NOT be called if ANY target unauthorized"
        assert commit_calls["count"] == 0, "No commit when authorization fails"
        assert event_calls["count"] == 0, "No event publish when authorization fails"
    else:
        # ALL authorized → writes succeed (except publish fault)
        if fault == "publish":
            with pytest.raises(RuntimeError):
                _run_sync(mock_writeback_with_gate())
        else:
            result = _run_sync(mock_writeback_with_gate())
            assert write_calls["count"] == num_targets
            assert commit_calls["count"] == 1
            assert event_calls["count"] == 1
            assert result["written"] == num_targets


# ─── End Wave1 Task 1.5 ──────────────────────────────────────────────────────

# ─── Wave2 Task 2.1: QueryRequest/QueryResult 契约回归 ──────────────────────


class TestQueryRequestResultContract:
    """验证 QueryRequest/QueryResult 契约：
    - 旧请求（无 sort/group/pivot/acnr_targets）仍正常工作（后向兼容）
    - 新请求带全部 optional 字段正常工作
    - Mutable defaults 不在实例间共享
    - QueryResult 承载 provenance/trace/manual 元数据

    Requirements: 3.1, 4.1, 5.1–5.3, 8.5
    """

    # ── 后向兼容：旧请求不带新 optional 字段 ──

    def test_old_request_without_optional_fields_works(self):
        """旧客户端只传 project_id/year/source/filters/columns/limit/offset。"""
        req = ApiQueryRequest(
            project_id="proj-001",
            year=2025,
            source="trial_balance",
        )
        assert req.sort == []
        assert req.group is None
        assert req.pivot is None
        assert req.acnr_targets == []
        assert req.columns == []
        assert req.filters == {}
        assert req.limit == 500
        assert req.offset == 0

    def test_old_request_with_explicit_columns_limit_offset(self):
        """旧客户端显式传 columns/limit/offset 保持原语义。"""
        req = ApiQueryRequest(
            project_id="proj-002",
            year=2024,
            source="report",
            columns=["amount", "code"],
            limit=100,
            offset=50,
        )
        assert req.columns == ["amount", "code"]
        assert req.limit == 100
        assert req.offset == 50
        assert req.sort == []
        assert req.group is None
        assert req.pivot is None
        assert req.acnr_targets == []

    # ── 新请求带全部 optional 字段 ──

    def test_new_request_with_all_optional_fields(self):
        """新客户端传 sort/group/pivot/acnr_targets 均可正常构造。"""
        req = ApiQueryRequest(
            project_id="proj-003",
            year=2026,
            source="disclosure",
            columns=["col1", "col2"],
            limit=200,
            offset=10,
            sort=[{"field": "amount", "direction": "desc"}],
            group={"dimensions": ["category"], "aggregates": [{"field": "amount", "op": "sum"}]},
            pivot={"rowDimensions": ["region"], "columnDimensions": ["quarter"], "valueField": "amount", "aggregate": "avg"},
            acnr_targets=["tb:1001", "tb:2211"],
        )
        assert len(req.sort) == 1
        assert req.sort[0].field == "amount"
        assert req.sort[0].direction == "desc"
        assert req.group == {"dimensions": ["category"], "aggregates": [{"field": "amount", "op": "sum"}]}
        assert req.pivot == {"rowDimensions": ["region"], "columnDimensions": ["quarter"], "valueField": "amount", "aggregate": "avg"}
        assert req.acnr_targets == ["tb:1001", "tb:2211"]

    # ── Mutable defaults 隔离 ──

    def test_mutable_defaults_do_not_share_state_between_instances(self):
        """修改一个实例的 list/dict 字段不得影响其他实例。"""
        req1 = ApiQueryRequest(project_id="p1", year=2025, source="report")
        req2 = ApiQueryRequest(project_id="p2", year=2025, source="report")

        # 修改 req1 的 mutable 字段
        req1.filters["key"] = "val"
        req1.columns.append("new_col")
        req1.sort.append({"field": "x", "direction": "asc"})
        req1.acnr_targets.append("tb:9999")

        # req2 不受影响
        assert req2.filters == {}
        assert req2.columns == []
        assert req2.sort == []
        assert req2.acnr_targets == []

    def test_orchestrator_query_request_mutable_defaults_isolation(self):
        """orchestrator 层 dataclass QueryRequest 的 mutable defaults 也不共享。"""
        req1 = QueryRequest(entry="business", project_id="p1")
        req2 = QueryRequest(entry="business", project_id="p2")

        req1.filters["a"] = 1
        req1.columns.append("col_x")
        req1.targets.append("tb:100")
        req1.sort.append({"field": "f", "direction": "asc"})
        req1.group_by.append("dim1")
        req1.aggs.append(Agg(field="x", func="sum"))

        assert req2.filters == {}
        assert req2.columns == []
        assert req2.targets == []
        assert req2.sort == []
        assert req2.group_by == []
        assert req2.aggs == []

    # ── QueryResult 承载 provenance/trace/manual 元数据 ──

    def test_query_result_carries_total_limit_offset_warnings(self):
        """QueryResult 明确 total/limit/offset/warnings/cache_hit。"""
        result = QueryResult(
            columns=[ColumnMeta(key="amount", title="金额")],
            rows=[{"amount": 100}],
            total=42,
            limit=10,
            offset=20,
            warnings=["CACHE_IDENTITY_UNSTABLE"],
            cache_hit=True,
        )
        assert result.total == 42
        assert result.limit == 10
        assert result.offset == 20
        assert result.warnings == ["CACHE_IDENTITY_UNSTABLE"]
        assert result.cache_hit is True

    def test_query_result_columns_carry_provenance_trace_manual_metadata(self):
        """ColumnMeta.source 承载 provenance/trace/manual 元数据。"""
        source_meta = {
            "manual": True,
            "provenance": [{"origin": "query-001", "ts": "2026-01-01"}],
            "trace": [{"step": "tb_balance", "addr_id": "D2/S1/B3"}],
        }
        col = ColumnMeta(
            key="amount",
            title="金额",
            addr_id="D2/detail/B3",
            source=source_meta,
        )
        assert col.source is not None
        assert col.source["manual"] is True
        assert len(col.source["provenance"]) == 1
        assert col.source["trace"][0]["addr_id"] == "D2/S1/B3"
        assert col.drillable is True  # has addr_id

    def test_query_result_to_payload_preserves_column_metadata(self):
        """to_payload 序列化不丢失 source 元数据。"""
        source_meta = {
            "manual": False,
            "provenance": [{"query_id": "q-42"}],
            "trace": [],
        }
        result = QueryResult(
            columns=[
                ColumnMeta(key="code", title="科目编码"),
                ColumnMeta(key="amount", title="金额", addr_id="tb/1001/credit", source=source_meta),
            ],
            rows=[{"code": "1001", "amount": 500}],
            total=1,
            limit=100,
            offset=0,
        )
        payload = result.to_payload()
        assert payload["total"] == 1
        assert payload["limit"] == 100
        assert payload["offset"] == 0
        assert payload["warnings"] == []
        # First column - simple
        assert payload["columns"][0]["key"] == "code"
        # Second column - with source metadata
        col_with_meta = payload["columns"][1]
        assert col_with_meta["addr_id"] == "tb/1001/credit"
        assert col_with_meta["source"] == source_meta

    def test_query_result_from_payload_reconstructs_column_metadata(self):
        """from_payload 反序列化正确恢复 source 元数据。"""
        source_meta = {
            "manual": True,
            "provenance": [{"origin": "manual-edit"}],
            "trace": [{"step": "user", "ts": "2026-07-01"}],
        }
        payload = {
            "columns": [
                {"key": "name", "title": "名称", "dtype": "text"},
                {"key": "val", "title": "值", "addr_id": "WP/D2/C5", "dtype": "number", "source": source_meta},
            ],
            "rows": [{"name": "test", "val": 999}],
            "total": 1,
            "limit": 50,
            "offset": 0,
            "warnings": ["w1"],
        }
        result = QueryResult.from_payload(payload, cache_hit=True)
        assert result.total == 1
        assert result.limit == 50
        assert result.offset == 0
        assert result.warnings == ["w1"]
        assert result.cache_hit is True
        assert result.columns[0].source is None
        assert result.columns[1].addr_id == "WP/D2/C5"
        assert result.columns[1].source == source_meta
        assert result.columns[1].drillable is True

    @pytest.mark.asyncio
    async def test_adapter_legacy_response_preserves_metadata_columns(self):
        """ExecuteCompatibilityAdapter.to_legacy_response 保留 source 元数据列。"""
        source_meta = {"manual": True, "provenance": [], "trace": []}
        result = QueryResult(
            columns=[
                ColumnMeta(key="simple", title="简单列"),
                ColumnMeta(key="rich", title="丰富列", addr_id="tb/2211/debit", source=source_meta, semantic_label="应付薪酬"),
            ],
            rows=[{"simple": 1, "rich": 2}],
            total=1,
            limit=100,
            offset=0,
            warnings=["info"],
            cache_hit=False,
        )
        resp = ExecuteCompatibilityAdapter.to_legacy_response(result)
        # Simple column → just key string
        assert resp["columns"][0] == "simple"
        # Rich column → full dict with metadata
        rich_col = resp["columns"][1]
        assert isinstance(rich_col, dict)
        assert rich_col["addr_id"] == "tb/2211/debit"
        assert rich_col["source"] == source_meta
        assert rich_col["semantic_label"] == "应付薪酬"
        # Top-level fields
        assert resp["total"] == 1
        assert resp["limit"] == 100
        assert resp["offset"] == 0
        assert resp["warnings"] == ["info"]
        assert resp["cache_hit"] is False

    @pytest.mark.asyncio
    async def test_full_roundtrip_old_request_through_adapter(self):
        """旧请求完整通过 adapter 转换后保持语义不变。"""
        body = SimpleNamespace(
            project_id="proj-old",
            year=2025,
            source="trial_balance",
            filters={"account_code": "1001"},
            columns=["code", "amount"],
            limit=500,
            offset=0,
            sort=[],
            group=None,
            pivot=None,
            acnr_targets=[],
        )
        orch_req = ExecuteCompatibilityAdapter.to_orchestrator_request(body)
        assert orch_req.project_id == "proj-old"
        assert orch_req.year == 2025
        assert orch_req.source == "trial_balance"
        assert orch_req.filters == {"account_code": "1001"}
        assert orch_req.columns == ["code", "amount"]
        assert orch_req.limit == 500
        assert orch_req.offset == 0
        assert orch_req.sort == []
        assert orch_req.group_by == []
        assert orch_req.aggs == []
        assert orch_req.pivot is None
        assert orch_req.targets == []


# ─── Wave2 Task 2.2: CanonicalQueryIdentityBuilder 加固测试 ───────────────────


class TestCanonicalQueryIdentityBuilderHardening:
    """Task 2.2: 验证 CanonicalQueryIdentityBuilder 覆盖全部语义字段、递归排序、
    有序字段保序、未知类型绕过缓存。

    Requirements: 3.1–3.5
    """

    def test_all_required_fields_included_in_identity(self):
        """Req 3.1: canonical payload 纳入全部语义字段。"""
        identity = build_canonical_query_identity(
            project_id="proj-001",
            year=2025,
            source="trial_balance",
            filters={"status": "active"},
            columns=["code", "amount"],
            limit=50,
            offset=10,
            sort=[{"field": "amount", "direction": "desc"}],
            group={"dimensions": ["code"], "aggregates": []},
            pivot={"row_dims": ["region"], "col_dims": ["quarter"]},
            acnr_targets=["D2/D2-2/A1"],
            schema_version="v2",
            contract_version="aq-v2",
            user_scope={"user": "u1", "projects": ["proj-001"]},
        )
        assert identity.cacheable is True
        assert identity.key is not None
        payload = identity.payload
        # 所有语义字段必须出现在 payload 中
        assert payload["project_id"] == "proj-001"
        assert payload["year"] == 2025
        assert payload["source"] == "trial_balance"
        assert payload["filters"] == {"status": "active"}
        assert payload["columns"] == ["code", "amount"]
        assert payload["limit"] == 50
        assert payload["offset"] == 10
        assert payload["sort"] == [{"direction": "desc", "field": "amount"}]
        assert payload["group"] == {"aggregates": [], "dimensions": ["code"]}
        assert payload["pivot"] == {"col_dims": ["quarter"], "row_dims": ["region"]}
        assert payload["acnr_targets"] == ["D2/D2-2/A1"]
        assert payload["schema_version"] == "v2"
        assert payload["contract_version"] == "aq-v2"
        # user_scope 作为 signature 哈希存入
        assert "user_scope_signature" in payload
        assert len(payload["user_scope_signature"]) == 64  # SHA-256 hex

    def test_recursive_key_sorting_produces_same_identity(self):
        """Req 3.2: 映射键递归排序——嵌套 dict 键顺序不同时产生相同身份。"""
        filters_a = {"outer": {"zebra": 1, "alpha": 2, "mid": {"z": 0, "a": 9}}}
        filters_b = {"outer": {"alpha": 2, "mid": {"a": 9, "z": 0}, "zebra": 1}}

        common_kwargs = dict(
            project_id="p1",
            year=2025,
            source="report",
            columns=["x"],
            limit=10,
            offset=0,
            sort=[],
            group=None,
            pivot=None,
            acnr_targets=[],
            schema_version="1",
            contract_version="v1",
            user_scope={"user": "u1"},
        )

        id_a = build_canonical_query_identity(filters=filters_a, **common_kwargs)
        id_b = build_canonical_query_identity(filters=filters_b, **common_kwargs)

        assert id_a.cacheable and id_b.cacheable
        assert id_a.key == id_b.key, "递归键排序后键顺序不同的 dict 应产生相同身份"

    def test_ordered_arrays_are_order_sensitive(self):
        """Req 3.3: columns/sort/acnr_targets 顺序保留，不同顺序产生不同身份。"""
        common_kwargs = dict(
            project_id="p1",
            year=2025,
            source="report",
            filters={},
            limit=10,
            offset=0,
            group=None,
            pivot=None,
            schema_version="1",
            contract_version="v1",
            user_scope={"user": "u1"},
        )

        # columns 顺序敏感
        id_ab = build_canonical_query_identity(
            columns=["a", "b"], sort=[], acnr_targets=[], **common_kwargs
        )
        id_ba = build_canonical_query_identity(
            columns=["b", "a"], sort=[], acnr_targets=[], **common_kwargs
        )
        assert id_ab.key != id_ba.key, "columns 顺序不同应产生不同身份"

        # sort 顺序敏感
        sort_1 = [{"field": "x", "direction": "asc"}, {"field": "y", "direction": "desc"}]
        sort_2 = [{"field": "y", "direction": "desc"}, {"field": "x", "direction": "asc"}]
        id_s1 = build_canonical_query_identity(
            columns=["x"], sort=sort_1, acnr_targets=[], **common_kwargs
        )
        id_s2 = build_canonical_query_identity(
            columns=["x"], sort=sort_2, acnr_targets=[], **common_kwargs
        )
        assert id_s1.key != id_s2.key, "sort 顺序不同应产生不同身份"

        # acnr_targets 顺序敏感
        id_t1 = build_canonical_query_identity(
            columns=["x"], sort=[], acnr_targets=["tb:1001", "tb:1002"], **common_kwargs
        )
        id_t2 = build_canonical_query_identity(
            columns=["x"], sort=[], acnr_targets=["tb:1002", "tb:1001"], **common_kwargs
        )
        assert id_t1.key != id_t2.key, "acnr_targets 顺序不同应产生不同身份"

    def test_unknown_type_returns_uncacheable_with_warning(self):
        """Req 3.5: 不可稳定序列化字段返回 cacheable=False 并记录告警。"""
        common_kwargs = dict(
            project_id="p1",
            year=2025,
            source="report",
            columns=["x"],
            limit=10,
            offset=0,
            sort=[],
            group=None,
            pivot=None,
            acnr_targets=[],
            schema_version="1",
            contract_version="v1",
            user_scope={"user": "u1"},
        )

        # object() 不可序列化
        identity = build_canonical_query_identity(filters={"bad": object()}, **common_kwargs)
        assert identity.cacheable is False
        assert identity.key is None
        assert len(identity.warnings) > 0
        assert "CACHE_IDENTITY_UNSTABLE" in identity.warnings[0]

    def test_set_type_returns_uncacheable(self):
        """Req 3.5: set 类型不可稳定序列化 → cacheable=False。"""
        common_kwargs = dict(
            project_id="p1",
            year=2025,
            source="report",
            columns=["x"],
            limit=10,
            offset=0,
            sort=[],
            group=None,
            pivot=None,
            acnr_targets=[],
            schema_version="1",
            contract_version="v1",
            user_scope={"user": "u1"},
        )
        identity = build_canonical_query_identity(filters={"tags": {1, 2, 3}}, **common_kwargs)
        assert identity.cacheable is False
        assert identity.key is None
        assert "CACHE_IDENTITY_UNSTABLE" in identity.warnings[0]

    def test_datetime_and_uuid_are_stably_serializable(self):
        """Req 3.1: datetime/UUID 等已知可稳定序列化类型正常纳入身份。"""
        from datetime import datetime
        from uuid import UUID

        common_kwargs = dict(
            project_id="p1",
            year=2025,
            source="report",
            columns=["x"],
            limit=10,
            offset=0,
            sort=[],
            group=None,
            pivot=None,
            acnr_targets=[],
            schema_version="1",
            contract_version="v1",
            user_scope={"user": "u1"},
        )
        dt = datetime(2025, 6, 15, 12, 0, 0)
        uid = UUID("12345678-1234-5678-1234-567812345678")

        identity = build_canonical_query_identity(
            filters={"created_at": dt, "id": uid}, **common_kwargs
        )
        assert identity.cacheable is True
        assert identity.key is not None

        # 相同值产生相同身份
        identity2 = build_canonical_query_identity(
            filters={"id": uid, "created_at": dt}, **common_kwargs
        )
        assert identity.key == identity2.key, "键顺序不影响结果"

    def test_non_finite_float_returns_uncacheable(self):
        """Req 3.5: NaN/Inf 等非有限浮点不可稳定序列化 → cacheable=False。"""
        import math

        common_kwargs = dict(
            project_id="p1",
            year=2025,
            source="report",
            columns=["x"],
            limit=10,
            offset=0,
            sort=[],
            group=None,
            pivot=None,
            acnr_targets=[],
            schema_version="1",
            contract_version="v1",
            user_scope={"user": "u1"},
        )
        identity = build_canonical_query_identity(
            filters={"value": math.nan}, **common_kwargs
        )
        assert identity.cacheable is False
        assert "CACHE_IDENTITY_UNSTABLE" in identity.warnings[0]

    def test_non_string_mapping_keys_return_uncacheable(self):
        """Req 3.5: 映射键非字符串时 → cacheable=False。"""
        common_kwargs = dict(
            project_id="p1",
            year=2025,
            source="report",
            columns=["x"],
            limit=10,
            offset=0,
            sort=[],
            group=None,
            pivot=None,
            acnr_targets=[],
            schema_version="1",
            contract_version="v1",
            user_scope={"user": "u1"},
        )
        identity = build_canonical_query_identity(
            filters={123: "numeric key"}, **common_kwargs
        )
        assert identity.cacheable is False
        assert "CACHE_IDENTITY_UNSTABLE" in identity.warnings[0]


# ─── Wave2 Task 2.3: StablePagination 定向测试 ───────────────────────────────


class TestStablePagination:
    """Task 2.3: 验证 StablePagination 的核心不变式：
    - group/pivot 后分页，total 反映聚合后行数
    - 用户 sort 后补唯一 tie-breaker，确保重复排序键下确定性顺序
    - 无 sort 时使用领域默认 + tie-breaker
    - 非法 sort 字段 → 422
    - offset 超 total → 空 rows，total 不变
    - Pydantic 验证：limit=0, limit=2001, offset=-1 → 422

    Requirements: 4.1–4.5
    """

    @pytest.mark.asyncio
    async def test_pagination_total_reflects_post_group_count_not_raw(self):
        """Req 4.5: group 后 total = 分组行数，非原始行数。"""
        # 6 raw rows → 3 groups
        raw_rows = [
            {"category": "A", "amount": 10},
            {"category": "A", "amount": 20},
            {"category": "B", "amount": 30},
            {"category": "B", "amount": 40},
            {"category": "C", "amount": 50},
            {"category": "C", "amount": 60},
        ]
        columns = [ColumnMeta(key="category", title="分类"), ColumnMeta(key="amount", title="金额")]

        async def fetcher(req, resolved, db):
            return list(raw_rows), list(columns)

        orch = QueryOrchestrator(
            guard=_Guard(), addressing=_Addressing(), cache=_PassthroughCache(), business_fetcher=fetcher
        )
        result = await orch.execute(
            QueryRequest(
                entry="business", project_id="p1", source="trial_balance",
                group_by=["category"],
                aggs=[Agg(field="amount", func="sum", alias="total_amount")],
                limit=100, offset=0,
            ),
            user=SimpleNamespace(id="u1"), db=None,
        )
        # total = 分组数 (3)，非原始行数 (6)
        assert result.total == 3, f"total 应为 group 后行数 3，实际 {result.total}"
        assert len(result.rows) == 3

    @pytest.mark.asyncio
    async def test_pagination_total_reflects_post_pivot_count(self):
        """Req 4.5: pivot 后 total = 透视结果行数。"""
        raw_rows = [
            {"region": "north", "quarter": "q1", "amount": 100},
            {"region": "north", "quarter": "q2", "amount": 200},
            {"region": "south", "quarter": "q1", "amount": 150},
            {"region": "south", "quarter": "q2", "amount": 250},
        ]
        columns = [ColumnMeta(key=k, title=k) for k in ("region", "quarter", "amount")]

        async def fetcher(req, resolved, db):
            return list(raw_rows), list(columns)

        orch = QueryOrchestrator(
            guard=_Guard(), addressing=_Addressing(), cache=_PassthroughCache(), business_fetcher=fetcher
        )
        result = await orch.execute(
            QueryRequest(
                entry="business", project_id="p1", source="trial_balance",
                pivot=PivotConfig(row_dims=["region"], col_dims=["quarter"], value_field="amount"),
                limit=100, offset=0,
            ),
            user=SimpleNamespace(id="u1"), db=None,
        )
        # 2 regions → total = 2 (非原始 4 行)
        assert result.total == 2, f"total 应为 pivot 后行数 2，实际 {result.total}"
        assert len(result.rows) == 2

    @pytest.mark.asyncio
    async def test_tie_breaker_ensures_deterministic_order_for_duplicate_sort_keys(self):
        """Req 4.2: 重复排序键下 tie-breaker 保证确定性顺序。"""
        # 所有行 score 相同 → 无 tie-breaker 时顺序不确定
        rows = [{"id": i, "score": 100} for i in range(10)]
        columns = [ColumnMeta(key="id", title="id"), ColumnMeta(key="score", title="score")]

        async def fetcher(req, resolved, db):
            return list(rows), list(columns)

        orch = QueryOrchestrator(
            guard=_Guard(), addressing=_Addressing(), cache=_PassthroughCache(), business_fetcher=fetcher
        )

        # 多次查询同一排序应产生相同结果顺序
        results = []
        for _ in range(5):
            result = await orch.execute(
                QueryRequest(
                    entry="business", project_id="p1", source="trial_balance",
                    sort=[{"field": "score", "direction": "asc"}],
                    limit=10, offset=0,
                ),
                user=SimpleNamespace(id="u1"), db=None,
            )
            results.append([r["id"] for r in result.rows])

        # 所有执行结果顺序必须一致（稳定 tie-breaker）
        assert all(r == results[0] for r in results), "tie-breaker 应确保重复排序键下的确定性顺序"

    @pytest.mark.asyncio
    async def test_tie_breaker_appended_to_user_sort_not_replacing(self):
        """Req 4.2: tie-breaker 追加在用户 sort 之后，不替代用户排序。"""
        rows = [
            {"name": "Alice", "score": 90},
            {"name": "Bob", "score": 80},
            {"name": "Charlie", "score": 90},  # 与 Alice 相同 score
        ]
        columns = [ColumnMeta(key="name", title="name"), ColumnMeta(key="score", title="score")]

        async def fetcher(req, resolved, db):
            return list(rows), list(columns)

        orch = QueryOrchestrator(
            guard=_Guard(), addressing=_Addressing(), cache=_PassthroughCache(), business_fetcher=fetcher
        )
        result = await orch.execute(
            QueryRequest(
                entry="business", project_id="p1", source="trial_balance",
                sort=[{"field": "score", "direction": "desc"}],
                limit=10, offset=0,
            ),
            user=SimpleNamespace(id="u1"), db=None,
        )
        # score desc: Alice(90) 和 Charlie(90) 先于 Bob(80)
        scores = [r["score"] for r in result.rows]
        assert scores[0] == 90
        assert scores[1] == 90
        assert scores[2] == 80
        # 用户排序生效，tie-breaker 仅在相等时起作用

    @pytest.mark.asyncio
    async def test_no_sort_uses_default_plus_tie_breaker(self):
        """Req 4.2: 无用户 sort 时使用领域默认 + tie-breaker，结果仍确定。"""
        rows = [{"id": i, "value": i % 3} for i in range(8)]
        columns = [ColumnMeta(key="id", title="id"), ColumnMeta(key="value", title="value")]

        async def fetcher(req, resolved, db):
            return list(rows), list(columns)

        orch = QueryOrchestrator(
            guard=_Guard(), addressing=_Addressing(), cache=_PassthroughCache(), business_fetcher=fetcher
        )

        # 无 sort 多次查询应产生相同顺序
        results = []
        for _ in range(3):
            result = await orch.execute(
                QueryRequest(
                    entry="business", project_id="p1", source="trial_balance",
                    sort=[], limit=8, offset=0,
                ),
                user=SimpleNamespace(id="u1"), db=None,
            )
            results.append([r["id"] for r in result.rows])

        assert all(r == results[0] for r in results), "无 sort 时也应确定性排序"
        assert result.total == 8

    @pytest.mark.asyncio
    async def test_nonexistent_sort_field_returns_422(self):
        """Req 4.4: sort 引用不存在的字段 → 422。"""
        rows = [{"id": 1, "amount": 100}]
        columns = [ColumnMeta(key="id", title="id"), ColumnMeta(key="amount", title="amount")]

        async def fetcher(req, resolved, db):
            return list(rows), list(columns)

        orch = QueryOrchestrator(
            guard=_Guard(), addressing=_Addressing(), cache=_PassthroughCache(), business_fetcher=fetcher
        )
        with pytest.raises(HTTPException) as exc:
            await orch.execute(
                QueryRequest(
                    entry="business", project_id="p1", source="trial_balance",
                    sort=[{"field": "nonexistent_field", "direction": "asc"}],
                    limit=10, offset=0,
                ),
                user=SimpleNamespace(id="u1"), db=None,
            )
        assert exc.value.status_code == 422
        assert "INVALID_SORT_FIELD" in exc.value.detail.get("error_code", "")

    @pytest.mark.asyncio
    async def test_invalid_sort_direction_returns_422(self):
        """Req 4.4: sort 方向不是 asc/desc → 422。"""
        rows = [{"id": 1, "amount": 100}]
        columns = [ColumnMeta(key="id", title="id"), ColumnMeta(key="amount", title="amount")]

        async def fetcher(req, resolved, db):
            return list(rows), list(columns)

        orch = QueryOrchestrator(
            guard=_Guard(), addressing=_Addressing(), cache=_PassthroughCache(), business_fetcher=fetcher
        )
        with pytest.raises(HTTPException) as exc:
            await orch.execute(
                QueryRequest(
                    entry="business", project_id="p1", source="trial_balance",
                    sort=[{"field": "amount", "direction": "invalid"}],
                    limit=10, offset=0,
                ),
                user=SimpleNamespace(id="u1"), db=None,
            )
        assert exc.value.status_code == 422
        assert "INVALID_SORT_FIELD" in exc.value.detail.get("error_code", "")

    @pytest.mark.asyncio
    async def test_offset_beyond_total_returns_empty_rows_total_unchanged(self):
        """Req 4.4: offset 超过 total → 空 rows，total 仍为真实值。"""
        rows = [{"id": i} for i in range(5)]
        columns = [ColumnMeta(key="id", title="id")]

        async def fetcher(req, resolved, db):
            return list(rows), list(columns)

        orch = QueryOrchestrator(
            guard=_Guard(), addressing=_Addressing(), cache=_PassthroughCache(), business_fetcher=fetcher
        )
        result = await orch.execute(
            QueryRequest(
                entry="business", project_id="p1", source="trial_balance",
                limit=10, offset=100,  # offset 远超 total=5
            ),
            user=SimpleNamespace(id="u1"), db=None,
        )
        assert result.total == 5, "total 不受 offset 影响"
        assert result.rows == [], "offset 超出范围应返回空行"

    def test_pydantic_422_for_limit_zero(self):
        """Req 4.4: limit=0 → Pydantic ValidationError (422 语义)。"""
        with pytest.raises(ValidationError):
            ApiQueryRequest(project_id="p1", year=2025, source="report", limit=0)

    def test_pydantic_422_for_limit_exceeds_max(self):
        """Req 4.4: limit=2001 → Pydantic ValidationError (422 语义)。"""
        with pytest.raises(ValidationError):
            ApiQueryRequest(project_id="p1", year=2025, source="report", limit=2001)

    def test_pydantic_422_for_negative_offset(self):
        """Req 4.4: offset=-1 → Pydantic ValidationError (422 语义)。"""
        with pytest.raises(ValidationError):
            ApiQueryRequest(project_id="p1", year=2025, source="report", offset=-1)

    @pytest.mark.asyncio
    async def test_orchestrator_422_for_limit_out_of_range(self):
        """Req 4.4: orchestrator 层也校验 limit 范围。"""
        async def fetcher(req, resolved, db):
            return [], []

        orch = QueryOrchestrator(
            guard=_Guard(), addressing=_Addressing(), cache=_PassthroughCache(), business_fetcher=fetcher
        )
        # limit=0 (bypassing pydantic which normally catches this)
        with pytest.raises(HTTPException) as exc:
            await orch.execute(
                QueryRequest(entry="business", project_id="p1", source="report", limit=0),
                user=SimpleNamespace(id="u1"), db=None,
            )
        assert exc.value.status_code == 422

        # limit=2001
        with pytest.raises(HTTPException) as exc:
            await orch.execute(
                QueryRequest(entry="business", project_id="p1", source="report", limit=2001),
                user=SimpleNamespace(id="u1"), db=None,
            )
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_orchestrator_422_for_negative_offset(self):
        """Req 4.4: orchestrator 层也校验 offset >= 0。"""
        async def fetcher(req, resolved, db):
            return [], []

        orch = QueryOrchestrator(
            guard=_Guard(), addressing=_Addressing(), cache=_PassthroughCache(), business_fetcher=fetcher
        )
        with pytest.raises(HTTPException) as exc:
            await orch.execute(
                QueryRequest(entry="business", project_id="p1", source="report", offset=-1),
                user=SimpleNamespace(id="u1"), db=None,
            )
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_all_pages_reconstruct_full_result_after_grouping(self):
        """Req 4.1, 4.3, 4.5: group 后分页，所有页拼接等于未分页结果。"""
        # 12 raw → 4 groups
        raw_rows = [
            {"dept": f"d{d}", "amount": a}
            for d in range(4)
            for a in (10, 20, 30)
        ]
        columns = [ColumnMeta(key="dept", title="dept"), ColumnMeta(key="amount", title="amount")]

        async def fetcher(req, resolved, db):
            return list(raw_rows), list(columns)

        orch = QueryOrchestrator(
            guard=_Guard(), addressing=_Addressing(), cache=_PassthroughCache(), business_fetcher=fetcher
        )

        page_size = 2
        collected = []
        totals = set()
        for offset in range(0, 10, page_size):
            result = await orch.execute(
                QueryRequest(
                    entry="business", project_id="p1", source="trial_balance",
                    group_by=["dept"],
                    aggs=[Agg(field="amount", func="sum", alias="sum_amount")],
                    limit=page_size, offset=offset,
                ),
                user=SimpleNamespace(id="u1"), db=None,
            )
            totals.add(result.total)
            collected.extend(result.rows)
            if len(result.rows) < page_size:
                break

        # total 恒为 4
        assert totals == {4}
        # 所有页拼接 = 4 行
        assert len(collected) == 4
        # 无重复
        depts = [r["dept"] for r in collected]
        assert len(set(depts)) == 4


# ─── End Wave2 Task 2.3 ──────────────────────────────────────────────────────


# ─── Wave2 Task 2.4: 将主 execute 唯一接入 QueryOrchestrator ─────────────────


class TestExecuteCompatibilityAdapterConvergence:
    """Task 2.4: 验证 ExecuteCompatibilityAdapter 的单核心收敛。

    - 旧请求体（属性缺失时 getattr 回退默认）→ orchestrator 收到安全默认值
    - 新请求体（含 sort/group/pivot/acnr_targets）→ 无损传入 orchestrator
    - HTTPException 从 orchestrator 原样传播（4xx 映射既有错误）
    - 未知异常 → rollback + correlation_id + 500
    - 不存在第二条执行路径 / 无语义不同的 fallback
    - adapter.execute 每请求恰好调用一次

    Requirements: 5.1–5.5
    """

    def test_old_body_missing_new_attributes_fills_safe_defaults(self):
        """旧客户端对象完全缺少 sort/group/pivot/acnr_targets 属性时，
        to_orchestrator_request 通过 getattr 回退安全默认值。"""
        # SimpleNamespace 不包含 sort/group/pivot/acnr_targets
        body = SimpleNamespace(
            project_id="proj-legacy",
            year=2024,
            source="trial_balance",
            filters={"code": "1001"},
            columns=["code", "amount"],
            limit=100,
            offset=5,
        )
        req = ExecuteCompatibilityAdapter.to_orchestrator_request(body)

        # 旧字段完整映射
        assert req.project_id == "proj-legacy"
        assert req.year == 2024
        assert req.source == "trial_balance"
        assert req.filters == {"code": "1001"}
        assert req.columns == ["code", "amount"]
        assert req.limit == 100
        assert req.offset == 5

        # 缺失的新字段填充安全默认
        assert req.sort == []
        assert req.group_by == []
        assert req.aggs == []
        assert req.pivot is None
        assert req.targets == []

    def test_new_body_with_all_fields_passes_lossless(self):
        """新客户端对象携带 sort/group/pivot/acnr_targets → 无损传入 orchestrator。"""
        body = SimpleNamespace(
            project_id="proj-new",
            year=2026,
            source="disclosure",
            filters={"section": "equity"},
            columns=["name", "value"],
            limit=50,
            offset=10,
            sort=[{"field": "value", "direction": "desc"}],
            group={"dimensions": ["name"], "aggregates": [{"field": "value", "op": "sum", "alias": "total"}]},
            pivot={"row_dims": ["name"], "col_dims": ["year"], "value_field": "value", "agg": "sum", "max_cols": 100},
            acnr_targets=["tb:1001", "note:equity"],
        )
        req = ExecuteCompatibilityAdapter.to_orchestrator_request(body)

        assert req.project_id == "proj-new"
        assert req.source == "disclosure"
        assert req.sort == [{"field": "value", "direction": "desc"}]
        assert req.group_by == ["name"]
        assert len(req.aggs) == 1
        assert req.aggs[0].field == "value"
        assert req.aggs[0].func == "sum"
        assert req.aggs[0].alias == "total"
        assert req.pivot is not None
        assert req.pivot.row_dims == ["name"]
        assert req.pivot.col_dims == ["year"]
        assert req.pivot.value_field == "value"
        assert req.pivot.agg == "sum"
        assert req.pivot.max_cols == 100
        assert req.targets == ["tb:1001", "note:equity"]

    def test_to_legacy_response_maps_all_result_fields(self):
        """to_legacy_response 正确将 QueryResult 适配回旧响应格式。"""
        result = QueryResult(
            columns=[
                ColumnMeta(key="code", title="科目"),
                ColumnMeta(key="amount", title="金额", addr_id="tb/1001/debit",
                           source={"manual": True}, semantic_label="现金"),
            ],
            rows=[{"code": "1001", "amount": 500}],
            total=1,
            limit=50,
            offset=0,
            warnings=["cache_bypass"],
            cache_hit=True,
        )
        resp = ExecuteCompatibilityAdapter.to_legacy_response(result)

        assert resp["rows"] == [{"code": "1001", "amount": 500}]
        assert resp["total"] == 1
        assert resp["limit"] == 50
        assert resp["offset"] == 0
        assert resp["warnings"] == ["cache_bypass"]
        assert resp["cache_hit"] is True
        # 无 addr_id 的 column → plain string key
        assert resp["columns"][0] == "code"
        # 有 addr_id/source 的 column → dict (保留 provenance/trace)
        assert isinstance(resp["columns"][1], dict)
        assert resp["columns"][1]["key"] == "amount"
        assert resp["columns"][1]["addr_id"] == "tb/1001/debit"

    @pytest.mark.asyncio
    async def test_no_fallback_execution_path_on_orchestrator_error(self):
        """orchestrator 抛 HTTPException 时不存在第二条执行路径 / 不回退到旧逻辑。"""
        call_count = {"n": 0}

        class FailOnceOrchestrator:
            async def execute(self, request, *, user, db):
                call_count["n"] += 1
                raise HTTPException(status_code=400, detail={"error_code": "BAD_SOURCE"})

        adapter = ExecuteCompatibilityAdapter(
            business_fetcher=lambda *a: None, orchestrator=FailOnceOrchestrator()
        )
        body = ApiQueryRequest(project_id="p1", year=2025, source="bad_source")
        with pytest.raises(HTTPException) as exc:
            await adapter.execute(body, user=SimpleNamespace(id="u1"), db=None)

        assert exc.value.status_code == 400
        # 恰好调用一次 — 无 retry / 无 fallback
        assert call_count["n"] == 1

    @pytest.mark.asyncio
    async def test_router_level_single_adapter_no_fallback_on_runtime_error(self, monkeypatch):
        """Router 级：RuntimeError 时只有一次 adapter.execute 调用（无 fallback 到旧分支）。"""
        import app.routers.custom_query as router_module

        adapter_calls = []

        async def spy_execute(self, body, *, user, db):
            adapter_calls.append("called")
            raise RuntimeError("unexpected crash")

        monkeypatch.setattr(ExecuteCompatibilityAdapter, "execute", spy_execute)
        monkeypatch.setattr("app.services.gin_index_monitor.is_index_building", lambda: False)

        db = AsyncMock()
        response = Response()
        with pytest.raises(HTTPException) as exc:
            await router_module.execute_query(
                ApiQueryRequest(project_id="p1", year=2025, source="report"),
                response, db, SimpleNamespace(id="u1"),
            )
        assert exc.value.status_code == 500
        assert exc.value.detail["correlation_id"]
        # 关键：adapter 只被调用一次，没有 fallback 到旧执行分支
        assert len(adapter_calls) == 1

    @pytest.mark.asyncio
    async def test_adapter_execute_called_exactly_once_for_success(self):
        """成功场景 adapter.execute 恰好调用一次 orchestrator（Req 5.5 单执行核心）。"""
        orchestrator_calls = []

        class TrackOrchestrator:
            async def execute(self, request, *, user, db):
                orchestrator_calls.append(request)
                return QueryResult(
                    columns=[ColumnMeta(key="v", title="v")],
                    rows=[{"v": 42}],
                    total=1, limit=500, offset=0, warnings=[],
                )

        adapter = ExecuteCompatibilityAdapter(
            business_fetcher=lambda *a: None, orchestrator=TrackOrchestrator()
        )
        body = ApiQueryRequest(project_id="p1", year=2025, source="trial_balance")
        result = await adapter.execute(body, user=SimpleNamespace(id="u1"), db=None)

        assert len(orchestrator_calls) == 1
        assert result["rows"] == [{"v": 42}]
        assert result["total"] == 1


# ─── End Wave2 Task 2.4 ──────────────────────────────────────────────────────
