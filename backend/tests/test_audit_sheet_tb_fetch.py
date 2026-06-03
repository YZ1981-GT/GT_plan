"""审定表（audit-sheet）TB 取数逻辑单元测试 + 属性测试

覆盖 spec `audit-sheet-editable` Task 13：
`wp_render_config._fetch_audit_sheet_tb_values` / `_generate_audit_sheet_data`
按 audit_rows 各行 account_code 批量查 trial_balance 填充 tb_values。

Validates: Requirements 3.1, 3.2, 3.3

测试通过 mock AsyncSession.execute 返回伪 TB 行（不依赖真实 DB），断言：
- tb_values 按 row.id 正确组装 + Decimal→float 转换
- 无 TB 行的科目自动省略
- 年度为空 / db/project_id 缺失 / 无 account_code → 降级返回 {}
- 任意异常 → 降级返回 {}（不抛出阻塞渲染）
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_config import (
    _decimal_to_float,
    _fetch_audit_sheet_tb_values,
    _generate_audit_sheet_data,
)


# ─── 测试辅助：构造 mock AsyncSession ──────────────────────────────────────


def _make_year_result(year: int | None):
    """模拟 `db.execute(sa.text(year_query))` 的返回（带 .first()）。"""
    res = MagicMock()
    res.first.return_value = (year,) if year is not None else None
    return res


def _make_tb_result(rows: list[tuple]):
    """模拟 `db.execute(sa.select(...))` 的返回（带 .all()）。

    每行元组结构：(standard_account_code, opening_balance,
                    unadjusted_amount, aje_adjustment, rje_adjustment)
    """
    res = MagicMock()
    res.all.return_value = rows
    return res


def _make_db(*, year: int | None, tb_rows: list[tuple]):
    """构造 execute 依次返回 [年度结果, TB 结果] 的 mock db。"""
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[_make_year_result(year), _make_tb_result(tb_rows)]
    )
    return db


def _rows(*account_codes: str | None) -> list[dict]:
    """构造最小 audit_rows（仅含 id + account_code）。"""
    out = []
    for i, code in enumerate(account_codes, start=1):
        out.append({"id": f"row-{i}", "item": f"项目{i}", "account_code": code})
    return out


# ─── _decimal_to_float 转换 ────────────────────────────────────────────────


def test_decimal_to_float_converts_decimal():
    assert _decimal_to_float(Decimal("100.50")) == pytest.approx(100.50)


def test_decimal_to_float_none_stays_none():
    assert _decimal_to_float(None) is None


def test_decimal_to_float_bad_value_returns_none():
    assert _decimal_to_float("not-a-number") is None


# ─── _fetch_audit_sheet_tb_values 正常路径 ─────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_tb_values_keyed_by_row_id_with_float_conversion():
    """正常取数：tb_values 按 row.id 组装 + Decimal→float（Req 3.1）。"""
    rows = _rows("1121", "1231")
    db = _make_db(
        year=2025,
        tb_rows=[
            ("1121", Decimal("100000.00"), Decimal("120000.00"),
             Decimal("500.00"), Decimal("0.00")),
            ("1231", Decimal("0.00"), Decimal("8000.00"),
             Decimal("0.00"), Decimal("300.00")),
        ],
    )
    result = await _fetch_audit_sheet_tb_values(rows, db=db, project_id=uuid4())

    assert set(result.keys()) == {"row-1", "row-2"}
    assert result["row-1"] == {
        "opening_unadjusted": pytest.approx(100000.00),
        "current_unadjusted": pytest.approx(120000.00),
        "sys_aje": pytest.approx(500.00),
        "sys_rje": pytest.approx(0.00),
    }
    # 全部为 float（非 Decimal）
    for v in result["row-1"].values():
        assert isinstance(v, float)
    assert result["row-2"]["current_unadjusted"] == pytest.approx(8000.00)
    assert result["row-2"]["sys_rje"] == pytest.approx(300.00)


@pytest.mark.asyncio
async def test_fetch_tb_values_omits_rows_without_tb_match():
    """某 account_code 无对应 TB 行 → 该行省略，不影响其他行（Req 3.3）。"""
    rows = _rows("1121", "9999")  # 9999 无 TB 行
    db = _make_db(
        year=2025,
        tb_rows=[
            ("1121", Decimal("100000.00"), Decimal("120000.00"),
             Decimal("0.00"), Decimal("0.00")),
        ],
    )
    result = await _fetch_audit_sheet_tb_values(rows, db=db, project_id=uuid4())

    assert "row-1" in result
    assert "row-2" not in result  # 9999 无 TB → 省略


@pytest.mark.asyncio
async def test_fetch_tb_values_null_amounts_become_none():
    """TB 行金额列为 NULL → 对应字段为 None（前端显示「—」）。"""
    rows = _rows("1121")
    db = _make_db(
        year=2025,
        tb_rows=[("1121", None, None, Decimal("0.00"), Decimal("0.00"))],
    )
    result = await _fetch_audit_sheet_tb_values(rows, db=db, project_id=uuid4())

    assert result["row-1"]["opening_unadjusted"] is None
    assert result["row-1"]["current_unadjusted"] is None
    assert result["row-1"]["sys_aje"] == pytest.approx(0.00)


# ─── _fetch_audit_sheet_tb_values 降级路径 ─────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_tb_values_db_none_returns_empty():
    """db 缺失 → 降级返回 {}。"""
    result = await _fetch_audit_sheet_tb_values(_rows("1121"), db=None, project_id=uuid4())
    assert result == {}


@pytest.mark.asyncio
async def test_fetch_tb_values_project_id_none_returns_empty():
    """project_id 缺失 → 降级返回 {}。"""
    db = _make_db(year=2025, tb_rows=[])
    result = await _fetch_audit_sheet_tb_values(_rows("1121"), db=db, project_id=None)
    assert result == {}


@pytest.mark.asyncio
async def test_fetch_tb_values_no_account_codes_returns_empty():
    """所有行 account_code 为 None → 降级返回 {}（不查 DB）。"""
    db = _make_db(year=2025, tb_rows=[])
    result = await _fetch_audit_sheet_tb_values(
        _rows(None, None), db=db, project_id=uuid4()
    )
    assert result == {}


@pytest.mark.asyncio
async def test_fetch_tb_values_year_none_returns_empty():
    """项目年度为空（audit_period_end NULL）→ 跳过取数返回 {}（Req 3.3 降级）。"""
    db = _make_db(year=None, tb_rows=[])
    result = await _fetch_audit_sheet_tb_values(_rows("1121"), db=db, project_id=uuid4())
    assert result == {}


@pytest.mark.asyncio
async def test_fetch_tb_values_sql_error_returns_empty():
    """任意 SQL/数据异常 → 记 warning 并降级返回 {}（绝不阻塞渲染，Req 3.3）。"""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=RuntimeError("DB connection lost"))
    result = await _fetch_audit_sheet_tb_values(_rows("1121"), db=db, project_id=uuid4())
    assert result == {}


# ─── _generate_audit_sheet_data 集成（持久化优先 + TB 实时取数）────────────


@pytest.mark.asyncio
async def test_generate_audit_sheet_data_persisted_rows_with_tb():
    """持久化优先：existing.audit_rows 沿用，但 tb_values 仍实时查（Req 4.3 + 3.4）。"""
    existing = {
        "audit_rows": [
            {"id": "row-1", "item": "原值", "account_code": "1121",
             "adj_amount": 5000.0, "reason": "确认坏账"},
        ]
    }
    db = _make_db(
        year=2025,
        tb_rows=[("1121", Decimal("100000.00"), Decimal("120000.00"),
                  Decimal("0.00"), Decimal("0.00"))],
    )
    result = await _generate_audit_sheet_data(
        file_path=None,
        sheet_name="审定表D1-1",
        existing=existing,
        db=db,
        project_id=uuid4(),
        wp_code="D1",
    )
    # 行结构沿用持久化（含用户编辑值）
    assert result["audit_rows"][0]["adj_amount"] == 5000.0
    assert result["audit_rows"][0]["reason"] == "确认坏账"
    # tb_values 实时查（不持久化）
    assert result["tb_values"]["row-1"]["current_unadjusted"] == pytest.approx(120000.00)


@pytest.mark.asyncio
async def test_generate_audit_sheet_data_no_file_no_db_degrades():
    """无模板 + 无 db → audit_rows=[] + tb_values={}（全降级，不抛异常）。"""
    result = await _generate_audit_sheet_data(
        file_path=None,
        sheet_name="审定表D1-1",
        existing=None,
        db=None,
        project_id=None,
        wp_code="D1",
    )
    assert result == {"audit_rows": [], "tb_values": {}}


# ─── 属性测试：tb_values 键集合 ⊆ 含 TB 匹配的行（Validates: Requirements 3.1, 3.3）──


@settings(max_examples=5, deadline=None)
@given(
    codes=st.lists(
        st.sampled_from(["1121", "1231", "1401", "9999", None]),
        min_size=1,
        max_size=6,
    ),
    matched=st.sets(st.sampled_from(["1121", "1231", "1401"]), max_size=3),
)
@pytest.mark.asyncio
async def test_property_tb_values_keys_only_for_matched_rows(codes, matched):
    """属性：tb_values 的键恰为「account_code 命中 TB 且非空」的行 id 集合。

    Validates: Requirements 3.1, 3.3
    - 命中 TB 的行必出现在 tb_values（取数成功）
    - 未命中 / account_code 为空的行必不出现（graceful degradation）
    """
    rows = _rows(*codes)
    tb_rows = [
        (c, Decimal("1.00"), Decimal("2.00"), Decimal("0.00"), Decimal("0.00"))
        for c in matched
    ]
    db = _make_db(year=2025, tb_rows=tb_rows)

    result = await _fetch_audit_sheet_tb_values(rows, db=db, project_id=uuid4())

    expected_keys = {
        r["id"]
        for r in rows
        if r["account_code"] is not None and r["account_code"] in matched
    }
    assert set(result.keys()) == expected_keys
    # 每个返回值含 4 个 TB 字段
    for v in result.values():
        assert set(v.keys()) == {
            "opening_unadjusted", "current_unadjusted", "sys_aje", "sys_rje"
        }
