"""编排器与 execute 契约接入 FetchPage（advanced-query-linkage-closure 任务 5；design §3.3、§10.1；R2.1~R2.5、R2.8、N3）。

- ``FetchPage(paged=True)``：数据库已完成计数 / 排序 / 分页，编排器跳过内存分组、排序与切片，total 原样；
- 旧取数器的 ``(rows, columns)`` 元组仍走内存路径（既有约 40 个编排器测试不改）；
- 内存源（``paged=False``）默认按 ``_row_index`` 保持取数行序，用户排序时同值行保持原序；
- 条件与条件逻辑进缓存键；``meta`` 经缓存往返无损，响应里没有内容时整键省略；
- 兼容适配层映射 ``conditions`` / ``condition_logic``，旧请求体缺字段取默认；canonical identity 覆盖条件。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.custom_query.execute_compatibility import ExecuteCompatibilityAdapter
from app.services.custom_query.query_orchestrator import (
    ColumnMeta,
    FetchPage,
    QueryOrchestrator,
    QueryRequest,
    QueryResult,
)
from app.services.query_cache import build_canonical_query_identity


class _Guard:
    async def assert_target_accessible(self, **_kw):
        return None

    async def filter_accessible_rows(self, rows, **_kw):
        return rows


class _Addressing:
    async def resolve_many(self, targets, **_kw):
        return []


class _Cache:
    """记下缓存键、直接计算（不连 Redis）。"""

    def __init__(self):
        self.keys: list[str] = []

    def cache_key(self, query_def, project_id, scope_sig):
        import json

        key = json.dumps([query_def, project_id, scope_sig], sort_keys=True, ensure_ascii=False, default=str)
        self.keys.append(key)
        return key

    async def get_or_compute(self, key, compute, *, ttl=30):
        return await compute()


def _orchestrator(fetcher, cache=None) -> QueryOrchestrator:
    return QueryOrchestrator(addressing=_Addressing(), guard=_Guard(), cache=cache or _Cache(), business_fetcher=fetcher)


def _req(**kw) -> QueryRequest:
    return QueryRequest(entry="business", project_id="p1", year=2025, source=kw.pop("source", "ledger_entries"), **kw)


_USER = SimpleNamespace(id="u1")


async def test_paged_fetch_page_skips_in_memory_paging_and_keeps_total() -> None:
    rows = [{"id": "c", "v": 1}, {"id": "a", "v": 3}, {"id": "b", "v": 2}]  # 数据库给的顺序，编排器不得重排

    async def fetcher(req, resolved, db):
        return FetchPage(rows=rows, columns=[ColumnMeta(key="v", title="v")], total=1_147_414, paged=True,
                         meta={"ref_context": {"template_type": "soe", "year": 2025}}, warnings=["w1"])

    result = await _orchestrator(fetcher).execute(_req(limit=3, offset=6000), user=_USER, db=None)
    assert result.total == 1_147_414, "total 是数据库 COUNT，不是本页行数"
    assert [r["id"] for r in result.rows] == ["c", "a", "b"] and (result.limit, result.offset) == (3, 6000)
    assert result.warnings == ["w1"] and result.meta == {"ref_context": {"template_type": "soe", "year": 2025}}


async def test_tuple_path_is_unchanged() -> None:
    async def fetcher(req, resolved, db):
        return [{"id": 3}, {"id": 1}, {"id": 2}], [ColumnMeta(key="id", title="id")]

    result = await _orchestrator(fetcher).execute(_req(limit=2, offset=0), user=_USER, db=None)
    assert result.total == 3 and [r["id"] for r in result.rows] == [1, 2], "旧取数器仍在内存里排序、计数、切片"
    assert result.meta == {}


async def test_memory_source_keeps_fetch_order_and_stable_ties() -> None:
    # 列名「C2」按字典序排在 _row_index 之前：若默认排序 / tie-breaker 不认 _row_index，回退到「全部列按列名排」
    # 就会先按 C2 的取值重排（这正是改造前附注表格行被按金额重排、cell_ref 按字符串排序的形态）
    raw = [{"label": "货币资金", "v": 2, "C2": "9"}, {"label": "其中：银行", "v": 1, "C2": "1"},
           {"label": "其他", "v": 2, "C2": "5"}, {"label": "合计", "v": 5, "C2": "0"}]
    rows = [{**r, "_row_index": i} for i, r in enumerate(raw)]

    async def fetcher(req, resolved, db):
        return FetchPage(rows=list(rows), columns=[ColumnMeta(key="label", title="label"), ColumnMeta(key="v", title="v"),
                                                   ColumnMeta(key="C2", title="C2")],
                         total=len(rows), paged=False)

    plain = await _orchestrator(fetcher).execute(_req(source="disclosure_note:八、1", limit=10), user=_USER, db=None)
    assert [r["label"] for r in plain.rows] == ["货币资金", "其中：银行", "其他", "合计"], "默认保持原表行序（合计行在最后）"
    by_v = await _orchestrator(fetcher).execute(
        _req(source="ws_consol_tb", limit=10, sort=[{"field": "v", "direction": "desc"}]), user=_USER, db=None)
    assert [r["label"] for r in by_v.rows] == ["合计", "货币资金", "其他", "其中：银行"], "同值行（v=2）保持原序"


async def test_conditions_enter_the_cache_key() -> None:
    cache = _Cache()

    async def fetcher(req, resolved, db):
        return FetchPage(rows=[], columns=[], total=0, paged=True)

    orch = _orchestrator(fetcher, cache)
    await orch.execute(_req(), user=_USER, db=None)
    await orch.execute(_req(conditions=[{"field": "debit_amount", "op": "gt", "value": 100000000}]), user=_USER, db=None)
    await orch.execute(_req(conditions=[{"field": "debit_amount", "op": "gt", "value": 100000000}],
                            condition_logic="or"), user=_USER, db=None)
    assert len(set(cache.keys)) == 3, "不同条件 / 条件逻辑必须是不同的缓存键"


def test_meta_round_trips_and_is_omitted_when_empty() -> None:
    result = QueryResult(columns=[ColumnMeta(key="a", title="a")], rows=[{"a": 1}], total=1, limit=10, offset=0,
                         meta={"ref_context": {"template_type": "listed", "year": 2025}})
    back = QueryResult.from_payload(result.to_payload(), cache_hit=True)
    assert back.meta == result.meta and back.cache_hit
    assert ExecuteCompatibilityAdapter.to_legacy_response(back)["meta"] == result.meta
    plain = ExecuteCompatibilityAdapter.to_legacy_response(QueryResult(columns=[], rows=[], total=0))
    assert "meta" not in plain, "没有内容时整键省略（N3：既有响应形状不变）"
    assert QueryResult.from_payload({"rows": [], "total": 0}, cache_hit=False).meta == {}, "旧缓存条目没有 meta 键"


def test_adapter_maps_conditions_and_defaults() -> None:
    body = SimpleNamespace(project_id="p1", year=2025, source="ledger_entries",
                           conditions=[SimpleNamespace(model_dump=lambda: {"field": "summary", "op": "like", "value": "冲销"})],
                           condition_logic="or")
    req = ExecuteCompatibilityAdapter.to_orchestrator_request(body)
    assert req.conditions == [{"field": "summary", "op": "like", "value": "冲销"}] and req.condition_logic == "or"
    legacy = ExecuteCompatibilityAdapter.to_orchestrator_request(SimpleNamespace(project_id="p1", year=2025, source="x"))
    assert legacy.conditions == [] and legacy.condition_logic == "and", "旧请求体缺字段取默认"


def test_canonical_identity_covers_conditions_in_order() -> None:
    base = {"project_id": "p1", "year": 2025, "source": "ledger_entries"}
    a = {"field": "summary", "op": "like", "value": "冲销"}
    b = {"field": "debit_amount", "op": "gt", "value": 1}
    plain = build_canonical_query_identity(**base)
    with_a = build_canonical_query_identity(**base, conditions=[a])
    ab = build_canonical_query_identity(**base, conditions=[a, b])
    ba = build_canonical_query_identity(**base, conditions=[b, a])
    ab_or = build_canonical_query_identity(**base, conditions=[a, b], condition_logic="or")
    assert len({plain.key, with_a.key, ab.key, ba.key, ab_or.key}) == 5
    assert ab.payload["conditions"] == [a, b] and ab.payload["condition_logic"] == "and"


@pytest.mark.parametrize("paged", [True, False])
async def test_fetch_page_warnings_reach_the_result(paged: bool) -> None:
    async def fetcher(req, resolved, db):
        return FetchPage(rows=[{"_row_index": 0, "a": 1}], columns=[ColumnMeta(key="a", title="a")], total=1,
                         paged=paged, warnings=["该项目年度没有生效数据集，按未删除行返回"])

    result = await _orchestrator(fetcher).execute(_req(), user=_USER, db=None)
    assert result.warnings == ["该项目年度没有生效数据集，按未删除行返回"] and result.total == 1
