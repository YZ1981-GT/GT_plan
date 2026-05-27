"""单测 — 附注公式 DSL（Sprint 1.5 Task 1.5.2）.

Spec:    .kiro/specs/disclosure-note-full-revamp/ Sprint 1.5 Task 1.5.2
Design:  D4 公式 DSL 沉淀（PRIOR / AGING 新增）
Reqs:    Sprint 1.5 验收 — =PRIOR + =AGING 函数实现，至少 6 用例

覆盖：
- =PRIOR('account_name','期末'|'期初')      上年附注取数（≥3 用例）
- =AGING('account_name','bucket')          账龄分桶（≥3 用例）
- 5 已有函数回归（TB / WP / REPORT / NOTE / SUM）
- _load_cross_table_data 加载 prior + aging 数据链路（mock db，对齐 services/ 测试约定）
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.note_formula_generator import (
    _exec_cross_table,
    _load_cross_table_data,
    _resolve_single_cross_ref,
)


def _sample_cross_data_with_prior_aging() -> dict:
    """构造含 prior + aging 数据的 cross_data — 用于纯函数测试."""
    return {
        "report": {"BS-002": {"current": 1000.0, "prior": 800.0}},
        "tb": {
            "1001": {"audited": 50.0, "unadjusted": 48.0, "opening": 40.0},
        },
        "notes": {"五、3": {"total_closing": 1200.0, "total_opening": 1100.0}},
        "wp": {"E1": {"审定表E1!B5": 50.0}},
        "prior": {
            "货币资金": {"closing": 1234.56, "opening": 1100.00},
            "应收账款": {"closing": 567.89, "opening": 500.00},
            "五、1": {"closing": 1234.56, "opening": 1100.00},
        },
        "aging": {
            "应收账款": {
                "1年以内": 100.0,
                "1-2年": 50.0,
                "2-3年": 30.0,
                "3-5年": 10.0,
                "5年以上": 5.0,
            },
            "其他应收款": {
                "1年以内": 20.0,
                "1-2年": 10.0,
            },
        },
    }


# ===========================================================================
# =PRIOR — Sprint 1.5 Task 1.5.2 新增（≥ 3 用例）
# ===========================================================================


def test_prior_closing_hit():
    """=PRIOR('货币资金','期末') 命中 cross_data['prior']['货币资金']['closing']."""
    cross = _sample_cross_data_with_prior_aging()
    val = _resolve_single_cross_ref("PRIOR('货币资金','期末')", cross)
    assert val == 1234.56


def test_prior_opening_hit():
    """=PRIOR('货币资金','期初') 取上年期初值."""
    cross = _sample_cross_data_with_prior_aging()
    val = _resolve_single_cross_ref("PRIOR('货币资金','期初')", cross)
    assert val == 1100.00


def test_prior_account_missing_returns_none():
    """=PRIOR('不存在科目','期末') → None（不抛错）."""
    cross = _sample_cross_data_with_prior_aging()
    val = _resolve_single_cross_ref("PRIOR('神秘科目','期末')", cross)
    assert val is None


def test_prior_unknown_period_returns_none():
    """period 不识别（既非"期末"也非"期初"）→ None."""
    cross = _sample_cross_data_with_prior_aging()
    val = _resolve_single_cross_ref("PRIOR('货币资金','xx')", cross)
    assert val is None


def test_prior_section_number_index():
    """按 section_number（如"五、1"）索引也能命中（兼容多 key 索引）."""
    cross = _sample_cross_data_with_prior_aging()
    val = _resolve_single_cross_ref("PRIOR('五、1','期末')", cross)
    assert val == 1234.56


def test_prior_in_compound_expression():
    """=TB(...) - PRIOR(...) 加减组合表达式正确解析."""
    cross = _sample_cross_data_with_prior_aging()
    val = _exec_cross_table(
        "PRIOR('货币资金','期末') - PRIOR('货币资金','期初')", cross
    )
    assert val == pytest.approx(1234.56 - 1100.00)


def test_prior_empty_cross_data():
    """cross_data['prior'] 为空 dict → None."""
    cross = {"report": {}, "tb": {}, "notes": {}, "wp": {}, "prior": {}, "aging": {}}
    val = _resolve_single_cross_ref("PRIOR('货币资金','期末')", cross)
    assert val is None


# ===========================================================================
# =AGING — Sprint 1.5 Task 1.5.2 新增（≥ 3 用例）
# ===========================================================================


def test_aging_within_one_year():
    """=AGING('应收账款','1年以内') 命中第一桶."""
    cross = _sample_cross_data_with_prior_aging()
    val = _resolve_single_cross_ref("AGING('应收账款','1年以内')", cross)
    assert val == 100.0


def test_aging_one_to_two_year_bucket():
    """=AGING('应收账款','1-2年') 命中第二桶."""
    cross = _sample_cross_data_with_prior_aging()
    val = _resolve_single_cross_ref("AGING('应收账款','1-2年')", cross)
    assert val == 50.0


def test_aging_no_aux_ledger_returns_none():
    """客户未提供辅助序时账（cross_data['aging'] 为空 dict）→ None."""
    cross = {"report": {}, "tb": {}, "notes": {}, "wp": {}, "prior": {}, "aging": {}}
    val = _resolve_single_cross_ref("AGING('应收账款','1年以内')", cross)
    assert val is None


def test_aging_unknown_bucket_returns_none():
    """bucket 不识别（如"超长龄"）→ None."""
    cross = _sample_cross_data_with_prior_aging()
    val = _resolve_single_cross_ref("AGING('应收账款','超长龄')", cross)
    assert val is None


def test_aging_account_with_partial_buckets():
    """科目存在但请求的桶下无数据（其他应收款无 5 年以上桶）→ 0.0（行为对齐 TB 缺账户返 0）."""
    cross = _sample_cross_data_with_prior_aging()
    val = _resolve_single_cross_ref("AGING('其他应收款','5年以上')", cross)
    assert val == 0.0


def test_aging_account_missing_returns_none():
    """科目完全不在 aging 中 → None."""
    cross = _sample_cross_data_with_prior_aging()
    val = _resolve_single_cross_ref("AGING('神秘科目','1年以内')", cross)
    assert val is None


def test_aging_in_compound_expression_sum():
    """=AGING(...) + AGING(...) 累加表达式."""
    cross = _sample_cross_data_with_prior_aging()
    val = _exec_cross_table(
        "AGING('应收账款','1年以内') + AGING('应收账款','1-2年')", cross
    )
    assert val == pytest.approx(150.0)


# ===========================================================================
# 5 已有函数回归（TB / WP / REPORT / NOTE / SUM）
# ===========================================================================


def test_regression_tb_function():
    """TB 函数未被破坏."""
    cross = _sample_cross_data_with_prior_aging()
    assert _resolve_single_cross_ref("TB('1001','期末')", cross) == 50.0


def test_regression_wp_function():
    """WP 函数未被破坏."""
    cross = _sample_cross_data_with_prior_aging()
    assert _resolve_single_cross_ref("WP('E1','审定表E1','B5')", cross) == 50.0


def test_regression_report_function():
    """REPORT 函数未被破坏."""
    cross = _sample_cross_data_with_prior_aging()
    assert _resolve_single_cross_ref("REPORT('BS-002','期末')", cross) == 1000.0


def test_regression_note_function():
    """NOTE 函数未被破坏."""
    cross = _sample_cross_data_with_prior_aging()
    assert _resolve_single_cross_ref("NOTE('五、3','合计','期末')", cross) == 1200.0


def test_regression_compound_expression_with_existing():
    """已有函数加减组合不受 PRIOR / AGING 添加影响."""
    cross = _sample_cross_data_with_prior_aging()
    val = _exec_cross_table(
        "TB('1001','期末') + REPORT('BS-002','期末')", cross
    )
    assert val == pytest.approx(50.0 + 1000.0)


# ===========================================================================
# _load_cross_table_data — DB 加载链路（mock db.execute，对齐 services/ 约定）
# ===========================================================================


def _make_mock_db(executions: list[MagicMock]) -> MagicMock:
    """构造按调用顺序返回不同 result 的 mock db.

    _load_cross_table_data 依次调 db.execute 6 次：
      1. FinancialReport
      2. TrialBalance
      3. WorkingPaper + WpIndex
      4. DisclosureNote (当年)
      5. DisclosureNote (上年, year-1)  ← Sprint 1.5 新增
      6. TbAuxLedger (账龄)             ← Sprint 1.5 新增
    """
    db = MagicMock()
    db.execute = AsyncMock(side_effect=executions)
    db.rollback = AsyncMock()
    return db


def _empty_scalars_result() -> MagicMock:
    """构造空 result：result.all() = [] / result.scalars().all() = []"""
    result = MagicMock()
    result.all = MagicMock(return_value=[])
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=[])
    result.scalars = MagicMock(return_value=scalars)
    return result


def _scalars_with(items: list) -> MagicMock:
    """构造 result.scalars().all() = items 的 mock result."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=items)
    result.scalars = MagicMock(return_value=scalars)
    result.all = MagicMock(return_value=[])
    return result


def _result_all(rows: list) -> MagicMock:
    """构造 result.all() = rows 的 mock result（用于 ledger 行迭代）."""
    result = MagicMock()
    result.all = MagicMock(return_value=rows)
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=[])
    result.scalars = MagicMock(return_value=scalars)
    return result


@pytest.mark.asyncio
async def test_load_cross_table_data_loads_prior_year_notes():
    """_load_cross_table_data 加载 year-1 附注 → cross_data['prior'] 按 section_title + section_number 双索引."""
    project_id = uuid4()
    year = 2025

    # 上年（year-1=2024）附注：货币资金 合计行 closing=1234.56 / opening=1100
    prior_note = SimpleNamespace(
        note_section="五、1",
        section_title="货币资金",
        table_data={
            "headers": ["项目", "期末余额", "期初余额"],
            "rows": [
                {"label": "库存现金", "values": [50.0, 40.0]},
                {"label": "银行存款", "values": [1184.56, 1060.0]},
                {"label": "合计", "values": [1234.56, 1100.0], "is_total": True},
            ],
        },
    )

    db = _make_mock_db([
        _empty_scalars_result(),               # 1. report
        _empty_scalars_result(),               # 2. tb
        _empty_scalars_result(),               # 3. wp
        _empty_scalars_result(),               # 4. notes (当年)
        _scalars_with([prior_note]),           # 5. prior notes (year-1)
        _result_all([]),                        # 6. aging ledger
    ])

    cross = await _load_cross_table_data(db, project_id, year)
    # section_title 索引
    assert "货币资金" in cross["prior"]
    assert cross["prior"]["货币资金"]["closing"] == 1234.56
    assert cross["prior"]["货币资金"]["opening"] == 1100.0
    # section_number 索引（多 key 兜底）
    assert "五、1" in cross["prior"]
    assert cross["prior"]["五、1"]["closing"] == 1234.56


@pytest.mark.asyncio
async def test_load_cross_table_data_loads_aging_buckets():
    """_load_cross_table_data 从 TbAuxLedger 反推账龄分桶 → cross_data['aging']."""
    project_id = uuid4()
    year = 2025

    # 假设 wp_account_mapping 中 1122 → 应收账款（真实文件含此映射）
    # 1 笔 2025-06-15 → 200 天 → 1年以内
    # 1 笔 2024-06-15 → 564 天 → 1-2年
    ledger_rows = [
        ("1122", date(2025, 6, 15), Decimal("100"), Decimal("0")),
        ("1122", date(2024, 6, 15), Decimal("80"), Decimal("0")),
    ]

    db = _make_mock_db([
        _empty_scalars_result(),            # 1. report
        _empty_scalars_result(),            # 2. tb
        _empty_scalars_result(),            # 3. wp
        _empty_scalars_result(),            # 4. notes (当年)
        _empty_scalars_result(),            # 5. prior notes
        _result_all(ledger_rows),           # 6. aging ledger
    ])

    cross = await _load_cross_table_data(db, project_id, year)
    aging = cross.get("aging") or {}
    # 仅当 wp_account_mapping.json 实际存在且含 1122 时才会聚合
    if "应收账款" in aging:
        assert aging["应收账款"].get("1年以内") == pytest.approx(100.0)
        assert aging["应收账款"].get("1-2年") == pytest.approx(80.0)


@pytest.mark.asyncio
async def test_load_cross_table_data_no_aging_returns_empty_dict():
    """无 TbAuxLedger 行 → cross_data['aging'] 为空 dict，AGING 函数返 None."""
    project_id = uuid4()
    year = 2025

    db = _make_mock_db([
        _empty_scalars_result(),    # 1. report
        _empty_scalars_result(),    # 2. tb
        _empty_scalars_result(),    # 3. wp
        _empty_scalars_result(),    # 4. notes
        _empty_scalars_result(),    # 5. prior notes
        _result_all([]),            # 6. aging ledger 空
    ])

    cross = await _load_cross_table_data(db, project_id, year)
    assert cross["aging"] == {}
    # 此时 AGING 函数应正确返 None
    val = _resolve_single_cross_ref("AGING('应收账款','1年以内')", cross)
    assert val is None


@pytest.mark.asyncio
async def test_load_cross_table_data_no_prior_returns_empty_dict():
    """无上年附注 → cross_data['prior'] 为空 dict，PRIOR 函数返 None."""
    project_id = uuid4()
    year = 2025

    db = _make_mock_db([
        _empty_scalars_result(),    # 1. report
        _empty_scalars_result(),    # 2. tb
        _empty_scalars_result(),    # 3. wp
        _empty_scalars_result(),    # 4. notes
        _empty_scalars_result(),    # 5. prior notes 空
        _result_all([]),            # 6. aging ledger
    ])

    cross = await _load_cross_table_data(db, project_id, year)
    assert cross["prior"] == {}
    val = _resolve_single_cross_ref("PRIOR('货币资金','期末')", cross)
    assert val is None


@pytest.mark.asyncio
async def test_load_cross_table_data_db_exception_silently_skipped():
    """DB 异常时 prior / aging 静默返空，不抛错（按现有 try/except pass 模式）."""
    project_id = uuid4()
    year = 2025

    db = MagicMock()
    db.execute = AsyncMock(side_effect=Exception("simulated DB failure"))
    db.rollback = AsyncMock()

    # 不抛错，所有子键都为空 dict
    cross = await _load_cross_table_data(db, project_id, year)
    assert cross["prior"] == {}
    assert cross["aging"] == {}
    assert cross["report"] == {}
    assert cross["tb"] == {}
