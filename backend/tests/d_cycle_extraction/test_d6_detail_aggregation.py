"""Wave 0 / Task 1.3 块 C-2 —— D6-2 aux 归集抽取纯函数单测.

spec: .kiro/specs/d-cycle-tier-a-writeback-detail-seed/  (Requirements 4.3, 4.4 / 决策4)

前置核实结论：D6-2 明细表 `tb_aux_balance` 1402 客户/合同维度归集原本**仅内联于 HTTP
handler** `d6_import_aux_balance`，无可复用后端函数。按 R4.4 已抽取为纯函数
`build_d6_detail_rows_from_aux`（无 I/O）+ 可复用入口 `aggregate_d6_detail_rows`（供
P0-2 render 自动 seed 按名调用），原端点改为委托、行为逐字节不变。

本单测锁定纯函数正确性（不触库）：行 schema 30 字段、字段映射（aux_name→合同/客户名、
期初/期末余额→未审/审定/账龄）、row_limit 截断、空输入、None 名回退、seqNo 从 1 起；
并以 fake async session 验证可复用入口的查询→构建串联。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.d_cycle_extraction.detail_aggregation import (
    DEFAULT_ROW_LIMIT,
    aggregate_d6_detail_rows,
    build_d6_detail_rows_from_aux,
)


def _seq_factory():
    """确定性 rowId 工厂（供断言其余字段）。"""
    counter = {"n": 0}

    def _make():
        counter["n"] += 1
        return f"row-{counter['n']}"

    return _make


# ---------------------------------------------------------------------------
# 纯函数 build_d6_detail_rows_from_aux
# ---------------------------------------------------------------------------


def test_build_rows_field_mapping():
    """字段映射：aux_name→合同/客户名、期初→priorUnadjusted/priorAudited/agePrior1y、
    期末→endUnadjusted/endAudited/ageEnd1y/receivableWithin1y，常量字段固定。"""
    rows = build_d6_detail_rows_from_aux(
        [("客户甲合同", 1000.0, 1500.0)], row_id_factory=_seq_factory()
    )
    assert len(rows) == 1
    r = rows[0]
    assert r["rowId"] == "row-1"
    assert r["seqNo"] == 1
    assert r["contractName"] == "客户甲合同"
    assert r["customerName"] == "客户甲合同"
    assert r["contractType"] == "工程施工"
    assert r["relatedPartyType"] == "非关联方"
    # 期初余额映射
    assert r["priorUnadjusted"] == 1000.0
    assert r["priorAudited"] == 1000.0
    assert r["agePrior1y"] == 1000.0
    assert r["priorAje"] == 0 and r["priorRje"] == 0
    # 期末余额映射
    assert r["endUnadjusted"] == 1500.0
    assert r["endAudited"] == 1500.0
    assert r["ageEnd1y"] == 1500.0
    assert r["receivableWithin1y"] == 1500.0
    assert r["endAje"] == 0 and r["endRje"] == 0
    # 常量字段
    assert r["isInConstructionPeriod"] == "否"
    assert r["creditRiskGroup"] == "业务类型组合"
    assert r["isConfirmed"] == "否"
    assert r["postPeriodSettlement"] == 0


def test_build_rows_full_schema_30_fields():
    """行 schema 必含全部 30 个 D6-2 字段（与原端点逐字节一致）。"""
    rows = build_d6_detail_rows_from_aux([("c", 1.0, 2.0)], row_id_factory=_seq_factory())
    expected_keys = {
        "rowId", "seqNo", "contractName", "contractType", "customerName",
        "companyCode", "relatedPartyType",
        "priorUnadjusted", "priorAje", "priorRje", "priorAudited",
        "agePrior1y", "agePrior1to2y", "agePrior2to3y", "agePrior3yAbove",
        "debitAmount", "creditAmount",
        "endUnadjusted", "endAje", "endRje", "endAudited",
        "ageEnd1y", "ageEnd1to2y", "ageEnd2to3y", "ageEnd3yAbove",
        "receivableWithin1y", "receivableAbove1y",
        "isInConstructionPeriod", "creditRiskGroup", "isConfirmed",
        "postPeriodSettlement",
    }
    assert set(rows[0].keys()) == expected_keys


def test_build_rows_seq_no_and_order():
    """多行 seqNo 从 1 递增，保持输入顺序。"""
    rows = build_d6_detail_rows_from_aux(
        [("甲", 1.0, 2.0), ("乙", 3.0, 4.0), ("丙", 5.0, 6.0)],
        row_id_factory=_seq_factory(),
    )
    assert [r["seqNo"] for r in rows] == [1, 2, 3]
    assert [r["contractName"] for r in rows] == ["甲", "乙", "丙"]


def test_build_rows_none_name_falls_back_to_empty():
    """aux_name 为 None → 合同/客户名回退空串（与原端点 `aux_row.aux_name or ""` 一致）。"""
    rows = build_d6_detail_rows_from_aux([(None, 1.0, 2.0)], row_id_factory=_seq_factory())
    assert rows[0]["contractName"] == ""
    assert rows[0]["customerName"] == ""


def test_build_rows_empty_input():
    """空归集 → 空行列表。"""
    assert build_d6_detail_rows_from_aux([]) == []


def test_build_rows_respects_row_limit():
    """超过 row_limit 截断（与原端点 `aux_rows[:_ROW_LIMIT]` 一致）。"""
    entries = [(f"c{i}", float(i), float(i + 1)) for i in range(10)]
    rows = build_d6_detail_rows_from_aux(entries, row_limit=3, row_id_factory=_seq_factory())
    assert len(rows) == 3
    assert [r["contractName"] for r in rows] == ["c0", "c1", "c2"]


def test_build_rows_coerces_to_float():
    """期初/期末余额强制 float（Decimal/int 输入亦可，与原端点 float() 一致）。"""
    from decimal import Decimal

    rows = build_d6_detail_rows_from_aux(
        [("c", Decimal("100.50"), 200)], row_id_factory=_seq_factory()
    )
    assert rows[0]["priorUnadjusted"] == 100.5
    assert isinstance(rows[0]["priorUnadjusted"], float)
    assert rows[0]["endUnadjusted"] == 200.0
    assert isinstance(rows[0]["endUnadjusted"], float)


def test_build_rows_default_row_id_is_uuid_like():
    """默认 row_id_factory（未注入）产生非空唯一 rowId（uuid4）。"""
    rows = build_d6_detail_rows_from_aux([("a", 1.0, 2.0), ("b", 3.0, 4.0)])
    ids = [r["rowId"] for r in rows]
    assert all(isinstance(i, str) and i for i in ids)
    assert len(set(ids)) == 2, "rowId 应唯一"


def test_default_row_limit_matches_endpoint():
    """DEFAULT_ROW_LIMIT 与端点 `_ROW_LIMIT` 一致（500）。"""
    from app.routers.wp_render_strategies._d6_import_export import _ROW_LIMIT

    assert DEFAULT_ROW_LIMIT == _ROW_LIMIT == 500


# ---------------------------------------------------------------------------
# 可复用入口 aggregate_d6_detail_rows（fake async session）
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _FakeSession:
    """记录执行的 SQL + 参数，返回预置 aux 行。"""

    def __init__(self, aux_rows):
        self.aux_rows = aux_rows
        self.executed = []

    async def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))
        return _FakeResult(self.aux_rows)


def _run(coro):
    return asyncio.run(coro)


def test_aggregate_queries_1402_and_builds_rows():
    """可复用入口：查询 tb_aux_balance 1402 → 构建 D6-2 行。"""
    aux = [
        SimpleNamespace(aux_name="合同A", prior_balance=100.0, current_balance=200.0),
        SimpleNamespace(aux_name="合同B", prior_balance=0.0, current_balance=50.0),
    ]
    db = _FakeSession(aux)
    rows = _run(aggregate_d6_detail_rows(db, "proj-1", row_id_factory=_seq_factory()))
    # 查询命中 tb_aux_balance + 科目 1402 + 传入 project_id
    sql, params = db.executed[0]
    assert "tb_aux_balance" in sql
    assert "1402" in sql
    assert params == {"pid": "proj-1"}
    # 构建结果
    assert [r["contractName"] for r in rows] == ["合同A", "合同B"]
    assert rows[0]["priorUnadjusted"] == 100.0
    assert rows[1]["endUnadjusted"] == 50.0


def test_aggregate_empty_aux_returns_empty():
    """无 1402 归集数据 → 返回空列表（端点据此返回 imported_count=0）。"""
    db = _FakeSession([])
    rows = _run(aggregate_d6_detail_rows(db, "proj-1"))
    assert rows == []
