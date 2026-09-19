"""高级查询硬化：Hypothesis 属性测试 —— 契约与分页域。

Feature: advanced-query-hardening-wiring-closure

覆盖 Property 7/8（adapter 与列元数据往返）· 9~13（分页）· 15/16（JOIN 与预算）·
17/18（列分层与 PII）。作用域 / 执行路径 / 治理 / 只读门禁域见
`test_advanced_query_hardening_properties_scope.py`。

与定点守卫 `test_advanced_query_scope_budget_tiers.py` 互补：那里用具体样例锚住
行为，这里用随机输入检验**不变式**。`max_examples >= 100`（spec Testing Strategy）。

标签约定：`Feature: advanced-query-hardening-wiring-closure, Property N`
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from hypothesis import given
from hypothesis import strategies as st

from app.routers.custom_query import QueryRequest as ApiQueryRequest
from app.services.custom_query.execute_compatibility import ExecuteCompatibilityAdapter
from app.services.custom_query.pagination import (
    MAX_LIMIT,
    MIN_LIMIT,
    apply_pagination,
    collect_available_columns,
    resolve_sort,
    validate_pagination,
)
from app.services.custom_query.query_orchestrator import (
    Agg,
    ColumnMeta,
    QueryRequest,
    QueryResult,
)
from app.services.custom_query.table_whitelist import (
    JOIN_WHITELIST,
    MAX_AGGREGATES,
    MAX_GROUP_DIMS,
    MAX_JOINS_PER_QUERY,
    TABLE_WHITELIST,
    derive_field_tiers,
    enforce_complexity_budget,
    enforce_join_business_key,
    enforce_pii_field_access,
    join_business_keys,
)

# 共享夹具与策略见 `_advanced_query_pbt_common`（拆分自本文件，避免行数门禁超限）
from tests._advanced_query_pbt_common import (  # noqa: E402
    PBT,
    _Addressing,
    _Guard,
    _IDENT,
    _PassthroughCache,
    _SCALAR,
    _orch,
    _run,
)


# ════════════════════════════════════════════════════════════════════════════
# Feature: advanced-query-hardening-wiring-closure, Property 8
# **Validates: Requirements 3.5, 3.6**
# ════════════════════════════════════════════════════════════════════════════
@PBT
@given(
    cols=st.lists(
        st.tuples(
            _IDENT,
            st.text(max_size=10),
            st.one_of(st.none(), _IDENT),
            st.one_of(
                st.none(),
                st.fixed_dictionaries(
                    {
                        "manual": st.booleans(),
                        "provenance": st.lists(st.dictionaries(_IDENT, _SCALAR, max_size=2), max_size=2),
                        "trace": st.lists(st.dictionaries(_IDENT, _SCALAR, max_size=2), max_size=2),
                    }
                ),
            ),
        ),
        max_size=6,
    ),
    total=st.integers(min_value=0, max_value=10**6),
    limit=st.integers(min_value=MIN_LIMIT, max_value=MAX_LIMIT),
    offset=st.integers(min_value=0, max_value=10**5),
)
def test_p8_query_result_payload_roundtrip_is_lossless(cols, total, limit, offset):
    """列元数据 + 分页字段经 to_payload/from_payload 往返恒无损。"""
    columns = [
        ColumnMeta(key=k, title=t, addr_id=a, source=s) for k, t, a, s in cols
    ]
    original = QueryResult(
        columns=columns, rows=[], total=total, limit=limit, offset=offset
    )
    restored = QueryResult.from_payload(original.to_payload(), cache_hit=True)
    assert restored.total == total
    assert restored.limit == limit
    assert restored.offset == offset
    assert len(restored.columns) == len(columns)
    for before, after in zip(columns, restored.columns):
        assert after.key == before.key
        assert after.title == before.title
        assert after.addr_id == before.addr_id
        assert after.source == before.source
        # 不变式：drillable ⇔ addr_id 非空
        assert after.drillable == (after.addr_id is not None)


# ════════════════════════════════════════════════════════════════════════════
# Property 7 — adapter 往返：缺字段填安全默认，有字段无损传递
# **Validates: Requirements 3.3**
# ════════════════════════════════════════════════════════════════════════════
@PBT
@given(
    year=st.integers(min_value=1990, max_value=2100),
    source=_IDENT,
    limit=st.integers(min_value=MIN_LIMIT, max_value=MAX_LIMIT),
    offset=st.integers(min_value=0, max_value=10**4),
    filters=st.dictionaries(_IDENT, _SCALAR, max_size=4),
    columns=st.lists(_IDENT, max_size=4, unique=True),
)
def test_p7_adapter_maps_legacy_body_losslessly(year, source, limit, offset, filters, columns):
    """legacy 请求体的每个字段都恒被无损映射；缺失的新字段恒得安全默认。"""
    body = SimpleNamespace(
        project_id="p1",
        year=year,
        source=source,
        filters=dict(filters),
        columns=list(columns),
        limit=limit,
        offset=offset,
    )
    req = ExecuteCompatibilityAdapter.to_orchestrator_request(body)
    assert req.year == year
    assert req.source == source
    assert req.filters == filters
    assert req.columns == columns
    assert req.limit == limit
    assert req.offset == offset
    # 缺失字段的安全默认
    assert req.sort == []
    assert req.group_by == []
    assert req.aggs == []
    assert req.pivot is None
    assert req.targets == []


# ════════════════════════════════════════════════════════════════════════════
# Property 9 / 12 — total 反映聚合后行数；逐页并集 == 全集且不重叠
# **Validates: Requirements 4.1, 4.5**
# ════════════════════════════════════════════════════════════════════════════
@PBT
@given(
    rows=st.lists(
        st.fixed_dictionaries({"id": st.integers(min_value=0, max_value=10**4), "v": st.integers()}),
        min_size=1,
        max_size=40,
        unique_by=lambda r: r["id"],
    ),
    limit=st.integers(min_value=1, max_value=10),
)
def test_p12_all_pages_union_equals_full_set_without_overlap(rows, limit):
    """任意行集与任意 limit，逐页取完的并集恒等于全集且各页互不重叠。"""
    async def fetcher(req, resolved, db):
        return list(rows), [ColumnMeta(key="id", title="id"), ColumnMeta(key="v", title="v")]

    orch = _orch(fetcher)
    seen: list[int] = []
    offset = 0
    totals: set[int] = set()
    while True:
        result = _run(
            orch.execute(
                QueryRequest(
                    entry="business", project_id="p1", source="trial_balance",
                    limit=limit, offset=offset,
                ),
                user=SimpleNamespace(id="u1"), db=None,
            )
        )
        totals.add(result.total)
        seen.extend(r["id"] for r in result.rows)
        if len(result.rows) < limit:
            break
        offset += limit
        if offset > len(rows) + limit:  # 防御：不应发生
            break
    assert totals == {len(rows)}, f"total 不稳定：{totals}"
    assert len(seen) == len(set(seen)), "页间存在重复行"
    assert set(seen) == {r["id"] for r in rows}, "逐页并集 != 全集"


@PBT
@given(
    groups=st.lists(_IDENT, min_size=1, max_size=6, unique=True),
    per_group=st.integers(min_value=1, max_value=5),
)
def test_p9_total_reflects_post_group_row_count(groups, per_group):
    """任意分组配置下 total 恒等于分组后行数，而非原始取数行数。"""
    raw = [
        {"category": g, "amount": i + 1}
        for g in groups
        for i in range(per_group)
    ]

    async def fetcher(req, resolved, db):
        return list(raw), [
            ColumnMeta(key="category", title="category"),
            ColumnMeta(key="amount", title="amount"),
        ]

    result = _run(
        _orch(fetcher).execute(
            QueryRequest(
                entry="business", project_id="p1", source="trial_balance",
                group_by=["category"],
                aggs=[Agg(field="amount", func="sum", alias="total_amount")],
                limit=MAX_LIMIT, offset=0,
            ),
            user=SimpleNamespace(id="u1"), db=None,
        )
    )
    assert result.total == len(groups), (
        f"分组 {len(groups)} 组、原始 {len(raw)} 行，total={result.total}"
    )


# ════════════════════════════════════════════════════════════════════════════
# Property 10 / 11 — tie-breaker 追加不替换；排序确定性
# **Validates: Requirements 4.2, 4.3**
# ════════════════════════════════════════════════════════════════════════════
@PBT
@given(
    fields=st.lists(_IDENT, min_size=1, max_size=3, unique=True),
    directions=st.lists(st.sampled_from(["asc", "desc"]), min_size=1, max_size=3),
)
def test_p10_tie_breaker_is_appended_never_replaces_user_sort(fields, directions):
    """用户排序恒是结果排序键的前缀，tie-breaker 恒在其后。"""
    available = set(fields) | {"id"}
    user_sort = [
        {"field": f, "direction": directions[i % len(directions)]}
        for i, f in enumerate(fields)
    ]
    keys = resolve_sort("trial_balance", user_sort, available)
    prefix = keys[: len(user_sort)]
    assert [k.field for k in prefix] == fields
    assert [k.direction for k in prefix] == [s["direction"] for s in user_sort]
    assert all(not k.is_tie_breaker for k in prefix)
    assert keys[len(user_sort):], "必须追加至少一个 tie-breaker"
    assert all(k.is_tie_breaker for k in keys[len(user_sort):])


@PBT
@given(
    rows=st.lists(
        st.fixed_dictionaries(
            {"id": st.integers(min_value=0, max_value=50), "score": st.integers(min_value=0, max_value=3)}
        ),
        min_size=1,
        max_size=25,
        unique_by=lambda r: r["id"],
    ),
    direction=st.sampled_from(["asc", "desc"]),
)
def test_p11_sort_is_deterministic_across_repeated_runs(rows, direction):
    """含大量重复排序键时，重复执行恒得到相同顺序。"""
    available = collect_available_columns(rows, ["id", "score"])
    keys = resolve_sort("trial_balance", [{"field": "score", "direction": direction}], available)
    orders = [
        [r["id"] for r in apply_pagination(list(rows), sort=keys, limit=MAX_LIMIT, offset=0).rows]
        for _ in range(4)
    ]
    assert all(o == orders[0] for o in orders), "排序不确定"
    # 用户排序仍生效
    scores = [
        next(r["score"] for r in rows if r["id"] == rid) for rid in orders[0]
    ]
    assert scores == sorted(scores, reverse=(direction == "desc"))


@PBT
@given(
    scores=st.lists(
        st.integers(min_value=0, max_value=20), min_size=2, max_size=20
    ),
    direction=st.sampled_from(["asc", "desc"]),
)
def test_p11_orchestrator_actually_applies_user_sort(scores, direction):
    """经**编排器**验证排序真的生效（而非只测纯函数）。

    🔴 判据层级说明：`test_p11_sort_is_deterministic_across_repeated_runs` 直接调
    `resolve_sort` + `apply_pagination` 两个纯函数，编排器若把排序键丢掉它检测不到
    （变异 P06 实测 GREEN）。此处让 fetcher 返回**逆序**数据，只有编排器真的施加
    排序，结果才会是有序的。
    """
    rows = [{"id": i, "score": s} for i, s in enumerate(scores)]
    # 故意按与目标相反的顺序交付，使「不排序」与「排对了」可区分
    rows_reversed = sorted(rows, key=lambda r: r["score"], reverse=(direction == "asc"))

    async def fetcher(req, resolved, db):
        return list(rows_reversed), [
            ColumnMeta(key="id", title="id"),
            ColumnMeta(key="score", title="score"),
        ]

    result = _run(
        _orch(fetcher).execute(
            QueryRequest(
                entry="business", project_id="p1", source="trial_balance",
                sort=[{"field": "score", "direction": direction}],
                limit=MAX_LIMIT, offset=0,
            ),
            user=SimpleNamespace(id="u1"), db=None,
        )
    )
    got = [r["score"] for r in result.rows]
    assert got == sorted(scores, reverse=(direction == "desc")), (
        f"编排器未施加用户排序：交付 {[r['score'] for r in rows_reversed]} → 得到 {got}"
    )


# ════════════════════════════════════════════════════════════════════════════
# Property 13 — 分页边界一律 422（双入口）
# **Validates: Requirements 4.6**
# ════════════════════════════════════════════════════════════════════════════
@PBT
@given(
    bad_limit=st.one_of(
        st.integers(max_value=MIN_LIMIT - 1),
        st.integers(min_value=MAX_LIMIT + 1, max_value=MAX_LIMIT + 10**4),
    ),
)
def test_p13_out_of_range_limit_rejected_at_both_entries(bad_limit):
    """越界 limit 在 pydantic 与编排器两处入口恒 422。"""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ApiQueryRequest(project_id="p1", year=2025, source="report", limit=bad_limit)
    with pytest.raises(HTTPException) as exc:
        validate_pagination(bad_limit, 0)
    assert exc.value.status_code == 422


@PBT
@given(bad_offset=st.integers(max_value=-1))
def test_p13_negative_offset_rejected_at_both_entries(bad_offset):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ApiQueryRequest(project_id="p1", year=2025, source="report", offset=bad_offset)
    with pytest.raises(HTTPException) as exc:
        validate_pagination(100, bad_offset)
    assert exc.value.status_code == 422


# ════════════════════════════════════════════════════════════════════════════
# Property 15 — JOIN 必须含业务键
# **Validates: Requirements 6.1**
# ════════════════════════════════════════════════════════════════════════════
@PBT
@given(
    scope_cols=st.lists(
        st.sampled_from(["project_id", "year", "company_code", "is_deleted"]),
        min_size=1,
        max_size=4,
    )
)
def test_p15_scope_only_join_always_rejected(scope_cols):
    """任意由作用域列组成的 ON 恒被拒绝（不论几列、何种组合）。"""
    on_pairs = [(c, c) for c in scope_cols]
    assert join_business_keys(on_pairs) == []
    with pytest.raises(HTTPException) as exc:
        enforce_join_business_key("a", "b", on_pairs)
    assert exc.value.detail["error_code"] == "JOIN_MISSING_BUSINESS_KEY"


@PBT
@given(
    business_col=_IDENT.filter(
        lambda s: s not in {"project_id", "year", "company_code", "is_deleted"}
    ),
    scope_cols=st.lists(
        st.sampled_from(["project_id", "year", "company_code"]), max_size=3
    ),
)
def test_p15_any_business_key_makes_join_acceptable(business_col, scope_cols):
    """只要 ON 含任一业务键，无论混入多少作用域列都恒被接受。"""
    on_pairs = [(c, c) for c in scope_cols] + [(business_col, business_col)]
    enforce_join_business_key("a", "b", on_pairs)


def test_p15_registered_joins_all_have_business_key():
    """登记表内每条 JOIN 恒含业务键（结构不变式，非随机输入）。"""
    for base, targets in JOIN_WHITELIST.items():
        for target, spec in targets.items():
            assert join_business_keys(spec.get("on") or ()), f"{base} -> {target}"


# ════════════════════════════════════════════════════════════════════════════
# Property 16 — 复杂度预算
# **Validates: Requirements 6.2, 6.3**
# ════════════════════════════════════════════════════════════════════════════
@PBT
@given(
    joins=st.integers(min_value=0, max_value=30),
    dims=st.integers(min_value=0, max_value=30),
    aggs=st.integers(min_value=0, max_value=40),
)
def test_p16_budget_verdict_matches_limits_exactly(joins, dims, aggs):
    """预算判定恒与上限一致：任一超限即拒，全部不超即通过。"""
    over = (
        joins > MAX_JOINS_PER_QUERY
        or dims > MAX_GROUP_DIMS
        or aggs > MAX_AGGREGATES
    )
    if over:
        with pytest.raises(HTTPException) as exc:
            enforce_complexity_budget(joins=joins, group_dims=dims, aggregates=aggs)
        assert exc.value.detail["error_code"] == "COMPLEXITY_BUDGET_EXCEEDED"
    else:
        enforce_complexity_budget(joins=joins, group_dims=dims, aggregates=aggs)


# ════════════════════════════════════════════════════════════════════════════
# Property 17 / 18 — 列分层划分不变式 + PII 收敛
# **Validates: Requirements 7.1, 7.4**
# ════════════════════════════════════════════════════════════════════════════
@PBT
@given(
    fields=st.lists(_IDENT, min_size=1, max_size=12, unique=True),
    pii_pick=st.integers(min_value=0, max_value=11),
)
def test_p17_tiers_partition_fields_without_loss_or_overlap(fields, pii_pick):
    """任意字段集：三层恒构成一个划分（并集=全集、两两不相交）。"""
    pii = {fields[pii_pick % len(fields)]}
    tiers = derive_field_tiers(fields, pii=pii)
    d, t, p = (
        set(tiers["default_fields"]),
        set(tiers["technical_fields"]),
        set(tiers["pii_fields"]),
    )
    assert d | t | p == set(fields), "三层并集必须等于全字段"
    # 严格划分：两两不相交。含「同时是技术列与 PII 列」的边界（如 project_id 被
    # 登记为某表 PII）—— 此时必须按 PII 归类，否则会绕过 PII 角色准入。
    assert not (d & t) and not (d & p) and not (t & p), (
        f"三层重叠：default={sorted(d)} technical={sorted(t)} pii={sorted(p)}"
    )
    # PII 恒不进默认列，且恒被归入 pii 层（安全优先）
    assert not (d & pii)
    assert pii & set(fields) <= p, "登记为 PII 的列必须出现在 pii_fields 层"


@PBT
@given(role=st.sampled_from(["auditor", "qc", "eqcr", "readonly", "assistant"]))
def test_p18_unprivileged_role_never_gets_pii(role):
    """任意无权角色请求任意 PII 列恒 403（含双段语法）。"""
    for field in TABLE_WHITELIST["staff_members"]["pii_fields"]:
        for spelling in (field, f"staff_members.{field}"):
            with pytest.raises(HTTPException) as exc:
                enforce_pii_field_access("staff_members", [spelling], role)
            assert exc.value.status_code == 403
            assert exc.value.detail["error_code"] == "PII_FIELD_FORBIDDEN"
