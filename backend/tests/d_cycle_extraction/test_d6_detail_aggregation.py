"""D6-2 明细表 aux 归集：纯函数行构建 + 可复用入口（真 SQLite 行）。

spec: .kiro/specs/d-cycle-tier-a-writeback-detail-seed/  (Requirements 4.3, 4.4 / 决策4)
      .kiro/specs/_archive/28-four-table-extraction-entry-completion/（Task 4 / Property 4）
      .kiro/specs/_archive/71-formula-fetch-and-wp-generation-defect-closure/（R7.2）

契约（four-table-extraction-entry-completion Task 4 起，018d0b33c）：
  * `build_d6_detail_rows_from_aux` **只写录入列**（合同/客户名 + 期初未审 + 来源标记）；账龄
    （agePrior*/ageEnd*/receivable*）与派生列（priorAudited/endUnadjusted/endAudited）不写 ——
    旧实现把期初/期末全额塞进账龄首段（伪造账龄，红基线 ④），派生列由前端 recalcRow 现算。
  * `aggregate_d6_detail_rows` 经共享件 `aggregate_d_cycle_aux` 归集（active dataset + 单一
    aux_type + 报表映射前缀，兜底 1141），**年度必传**。

🔴 本文件原断言迁移前的 30 列 schema（账龄首段 = 期初/期末全额）与裸 SQL，自 018d0b33c 起 4 条
一直红；归档证据声称的锁定用例 `test_build_rows_only_record_columns` 在 git 历史里从未存在过。
现按现行契约重写，并补上该用例。可复用入口改用真 SQLite 行验证（替身按 SQL 文本路由认不出
共享件的 ORM 查询，正是旧用例失效的原因）。
"""
from __future__ import annotations

import asyncio
import re
import uuid
from decimal import Decimal
from pathlib import Path

from app.services.d_cycle_extraction.detail_aggregation import (
    DEFAULT_ROW_LIMIT,
    aggregate_d6_detail_rows,
    build_d6_detail_rows_from_aux,
)
from tests.d_cycle_extraction._aux_sqlite import aux_row, run_on_aux_rows

_FRONTEND_D6 = (
    Path(__file__).resolve().parents[3]
    / "audit-platform/frontend/src/components/workpaper/composables/useD6Detail.ts"
)
_RECORD_KEYS = {"rowId", "seqNo", "contractName", "customerName", "priorUnadjusted", "source_kind"}


def _seq_factory():
    """确定性 rowId 工厂（供断言其余字段）。"""
    counter = {"n": 0}

    def _make():
        counter["n"] += 1
        return f"row-{counter['n']}"

    return _make


def _frontend_detail_row_fields() -> tuple[set[str], set[str]]:
    """解析前端 `DetailRow` 接口：返回（全部字段, 注释标「自动」的派生字段）。"""
    text = _FRONTEND_D6.read_text(encoding="utf-8")
    body = text.split("export interface DetailRow {", 1)[1].split("\n}", 1)[0]
    fields: set[str] = set()
    derived: set[str] = set()
    for line in body.split("\n"):
        m = re.match(r"^[ \t]+(\w+):", line)
        if not m:
            continue
        fields.add(m.group(1))
        comment = line.split("//", 1)[1] if "//" in line else ""
        if "自动" in comment:
            derived.add(m.group(1))
    return fields, derived


# ---------------------------------------------------------------------------
# 纯函数 build_d6_detail_rows_from_aux
# ---------------------------------------------------------------------------


def test_build_rows_field_mapping():
    """aux_name → 合同/客户名；期初余额 → priorUnadjusted；期末余额不写（交前端 recalc）。"""
    rows = build_d6_detail_rows_from_aux(
        [("客户甲合同", 1000.0, 1500.0)], row_id_factory=_seq_factory()
    )
    assert rows == [{
        "rowId": "row-1",
        "seqNo": 1,
        "contractName": "客户甲合同",
        "customerName": "客户甲合同",
        "priorUnadjusted": 1000.0,
        "source_kind": "aux_balance_import",
    }]


def test_build_rows_only_record_columns():
    """行键 = 录入列；不含账龄列与派生列（Property 4 / 红基线 ④ 不伪造账龄）。"""
    rows = build_d6_detail_rows_from_aux([("c", 1.0, 2.0)], row_id_factory=_seq_factory())
    keys = set(rows[0].keys())
    assert keys == _RECORD_KEYS
    assert not [k for k in keys if k.startswith(("agePrior", "ageEnd", "receivable"))]
    fields, derived = _frontend_detail_row_fields()
    assert {"priorAudited", "endUnadjusted", "endAudited"} <= derived, "前端派生列标注变了"
    assert keys - {"source_kind"} <= fields, "行键必须是前端 DetailRow 的字段"
    assert not keys & derived, "派生列由前端 recalcRow 现算，后端不写"


def test_build_rows_seq_no_and_order():
    """多行 seqNo 从 1 递增，保持输入顺序。"""
    rows = build_d6_detail_rows_from_aux(
        [("甲", 1.0, 2.0), ("乙", 3.0, 4.0), ("丙", 5.0, 6.0)],
        row_id_factory=_seq_factory(),
    )
    assert [r["seqNo"] for r in rows] == [1, 2, 3]
    assert [r["contractName"] for r in rows] == ["甲", "乙", "丙"]


def test_build_rows_none_name_falls_back_to_empty():
    """aux_name 为 None → 合同/客户名回退空串。"""
    rows = build_d6_detail_rows_from_aux([(None, 1.0, 2.0)], row_id_factory=_seq_factory())
    assert rows[0]["contractName"] == ""
    assert rows[0]["customerName"] == ""


def test_build_rows_empty_input():
    """空归集 → 空行列表。"""
    assert build_d6_detail_rows_from_aux([]) == []


def test_build_rows_respects_row_limit():
    """超过 row_limit 截断。"""
    entries = [(f"c{i}", float(i), float(i + 1)) for i in range(10)]
    rows = build_d6_detail_rows_from_aux(entries, row_limit=3, row_id_factory=_seq_factory())
    assert len(rows) == 3
    assert [r["contractName"] for r in rows] == ["c0", "c1", "c2"]


def test_build_rows_coerces_to_float():
    """期初余额强制 float（Decimal / int 输入亦可）；None 期初 → 0.0。"""
    rows = build_d6_detail_rows_from_aux(
        [("c", Decimal("100.50"), 200), ("d", None, 1)], row_id_factory=_seq_factory()
    )
    assert rows[0]["priorUnadjusted"] == 100.5
    assert isinstance(rows[0]["priorUnadjusted"], float)
    assert rows[1]["priorUnadjusted"] == 0.0


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
# 可复用入口 aggregate_d6_detail_rows（真 SQLite 行：共享件的 ORM 查询原样执行）
# ---------------------------------------------------------------------------

_PID = uuid.uuid4()
_OTHER_PID = uuid.uuid4()


def _aux(name, *, opening, closing, pid=_PID, **kw):
    return aux_row(name, project_id=pid, opening=opening, closing=closing, **kw)


async def _aggregate_on_sqlite(rows, *, project_id, year):
    return await run_on_aux_rows(rows, lambda db: aggregate_d6_detail_rows(
        db, str(project_id), year, row_id_factory=_seq_factory()))


def _seed_rows():
    return [
        _aux("客户甲", opening=100, closing=150),
        _aux("客户甲", opening=10, closing=20, code="1141.01"),  # 子科目前缀命中，同名合并
        _aux("客户乙", opening=0, closing=50),
        _aux("合同X", opening=999, closing=999, aux_type="项目"),  # 非往来维度：锁定「客户」后排除
        _aux("客户丙", opening=7, closing=7, year=2024),  # 他年
        _aux("客户丁", opening=8, closing=8, code="1122"),  # 他科目
        _aux("客户戊", opening=9, closing=9, pid=_OTHER_PID),  # 他项目
        _aux("客户己", opening=6, closing=6, deleted=True),  # 已删
    ]


def test_aggregate_reads_project_year_1141_single_aux_type():
    """只归集本项目 · 本年度 · 1141 前缀 · 锁定的往来维度 · 未删行；按名称合并期初。"""
    rows = asyncio.run(_aggregate_on_sqlite(_seed_rows(), project_id=_PID, year=2025))
    assert {r["contractName"]: r["priorUnadjusted"] for r in rows} == {"客户甲": 110.0, "客户乙": 0.0}
    assert sorted(r["seqNo"] for r in rows) == [1, 2]
    assert all(set(r) == _RECORD_KEYS for r in rows)


def test_aggregate_year_is_a_filter_not_ignored():
    """换年度只取该年的行（年度是过滤条件；year=0 恒空，证明调用方必须传对年度）。"""
    rows_2024 = asyncio.run(_aggregate_on_sqlite(_seed_rows(), project_id=_PID, year=2024))
    assert [r["contractName"] for r in rows_2024] == ["客户丙"]
    rows_0 = asyncio.run(_aggregate_on_sqlite(_seed_rows(), project_id=_PID, year=0))
    assert rows_0 == []


def test_aggregate_empty_aux_returns_empty():
    """本项目本年无 1141 归集数据 → 返回空列表（端点据此返回 imported_count=0）。"""
    rows = asyncio.run(_aggregate_on_sqlite(
        [_aux("客户丁", opening=8, closing=8, code="1122")], project_id=_PID, year=2025))
    assert rows == []
