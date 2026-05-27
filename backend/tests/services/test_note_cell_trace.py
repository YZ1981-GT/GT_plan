"""单测 — disclosure_engine.trace_cell + GET /api/disclosure-notes/.../trace.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 2 Task 2.3
Design: D5 CellTrace 溯源链 端点 schema
Reqs:   R3.1 验收 21、22

≥ 5 用例覆盖：
  1. 命中 trial_balance binding → 完整返回 binding + formula_resolved + evidence
  2. 缺 binding_id → error="no_binding" + computed_value 仍返回
  3. row_idx 越界 → error="cell_index_out_of_range" axis="row"
  4. col_idx 越界 → error="cell_index_out_of_range" axis="col"
  5. evidence 限 100 行（造 200 条 _tb_cache 验证截断）
  6. note_not_found → error="note_not_found"
  7. binding_not_found → error="binding_not_found"
  8. _expand_formula 7 source 字符串生成正确性
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services import note_template_bindings_loader as loader
from app.services.disclosure_engine import DisclosureEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine() -> DisclosureEngine:
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    db.commit = AsyncMock()
    eng = DisclosureEngine(db)
    eng._wp_cache = {}
    eng._tb_cache = {}
    eng._wp_account_cache = {}
    eng._wp_fine_cache = {}
    eng._prior_notes_cache = {}
    return eng


def _make_note(
    *,
    note_section: str = "五、1 货币资金",
    rows: list | None = None,
    note_id=None,
):
    """构造最小 SimpleNamespace 模拟 DisclosureNote ORM 对象 (含 _cell_meta)."""
    return SimpleNamespace(
        id=note_id or uuid4(),
        project_id=uuid4(),
        year=2025,
        note_section=note_section,
        section_title="货币资金",
        account_name="货币资金",
        content_type=None,
        table_data={
            "headers": ["项目", "期末余额", "期初余额"],
            "rows": rows or [],
        },
        text_content=None,
        source_template=None,
        status=None,
        sort_order=None,
        is_deleted=False,
        is_stale=False,
        updated_at=None,
    )


def _patch_note_query(engine: DisclosureEngine, note) -> None:
    """让 db.execute 第一次调用返 scalar_one_or_none()=note."""
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=note)
    engine.db.execute = AsyncMock(return_value=result)


def _patch_loader(monkeypatch, sec_binding):
    """劫持 binding loader 返回 fixture binding 字典."""
    monkeypatch.setattr(
        loader,
        "get_binding_for_section",
        lambda section_number: sec_binding,
    )


def _trial_balance_binding(account_codes: list[str]) -> dict:
    """构造一个简单的 trial_balance binding section 配置 (供 _lookup_binding 反查)."""
    return {
        "wp_code": None,
        "tables": [
            {
                "table_index": 0,
                "table_name": "项  目",
                "header_normalize": [
                    {"text": "项目", "semantic": "manual_text"},
                    {"text": "期末余额", "semantic": "closing_balance"},
                    {"text": "期初余额", "semantic": "opening_balance"},
                ],
                "rows": {
                    "库存现金": {
                        "row_type": "data",
                        "binding": {
                            "closing_balance": {
                                "source": "trial_balance",
                                "field": "audited_amount",
                                "account_codes": account_codes,
                                "mode": "auto",
                                "agg": "sum",
                            },
                            "opening_balance": {
                                "source": "trial_balance",
                                "field": "opening_balance",
                                "account_codes": account_codes,
                                "mode": "auto",
                                "agg": "sum",
                            },
                        },
                    },
                },
            }
        ],
    }


# ===========================================================================
# 1. 命中 trial_balance binding → 完整返回
# ===========================================================================


@pytest.mark.asyncio
async def test_trace_cell_trial_balance_full_return(monkeypatch):
    """命中 trial_balance binding：返回 binding + formula_resolved + evidence."""
    eng = _make_engine()
    eng._tb_cache = {
        "1001": {"audited": 1000.0, "opening": 800.0, "unadjusted": 0},
        "1002": {"audited": 234.56, "opening": 100.0, "unadjusted": 0},
    }
    note = _make_note(rows=[
        {
            "label": "库存现金",
            "values": [1234.56, 900.0],
            "row_type": "data",
            "_cell_modes": {"0": "auto", "1": "auto"},
            "_cell_meta": {
                "0": {
                    "manual_value": None,
                    "semantic": "closing_balance",
                    "binding_id": "五、1 货币资金.库存现金.closing_balance",
                },
                "1": {
                    "manual_value": None,
                    "semantic": "opening_balance",
                    "binding_id": "五、1 货币资金.库存现金.opening_balance",
                },
            },
        },
    ])
    _patch_note_query(eng, note)
    _patch_loader(monkeypatch, _trial_balance_binding(["1001", "1002"]))

    out = await eng.trace_cell(note.id, 0, 0)

    assert "error" not in out, f"unexpected error: {out.get('error')}"
    assert out["computed_value"] == 1234.56
    assert out["semantic"] == "closing_balance"
    assert out["row_label"] == "库存现金"
    # binding 元数据完整
    b = out["binding"]
    assert b["source"] == "trial_balance"
    assert b["field"] == "audited_amount"
    assert b["account_codes"] == ["1001", "1002"]
    # formula_resolved 字符串展开
    assert "TB('1001'" in out["formula_resolved"]
    assert "TB('1002'" in out["formula_resolved"]
    # evidence trial_balance_rows 命中两条（缓存路径，无 SQL）
    tb_rows = out["evidence"]["trial_balance_rows"]
    assert len(tb_rows) == 2
    assert {r["account_code"] for r in tb_rows} == {"1001", "1002"}
    # ledger / aux 不取（source 不匹配）
    assert out["evidence"]["ledger_sample"] == []
    assert out["evidence"]["aux_balance_sample"] == []
    assert out["computed_at"]  # 有时间戳


# ===========================================================================
# 2. 缺 binding_id → error="no_binding" + computed_value 仍返回
# ===========================================================================


@pytest.mark.asyncio
async def test_trace_cell_no_binding_id_returns_value(monkeypatch):
    """cell_meta 缺 binding_id：返 no_binding + 仍带原 computed_value."""
    eng = _make_engine()
    note = _make_note(rows=[
        {
            "label": "其他",
            "values": [777.0, 0],
            "row_type": "data",
            "_cell_modes": {"0": "manual"},
            "_cell_meta": {
                "0": {
                    "manual_value": 777.0,
                    "semantic": None,
                    "binding_id": None,  # ← 显式无 binding
                },
            },
        },
    ])
    _patch_note_query(eng, note)

    out = await eng.trace_cell(note.id, 0, 0)
    assert out["error"] == "no_binding"
    assert out["computed_value"] == 777.0
    assert out["computed_at"]


# ===========================================================================
# 3. row_idx 越界
# ===========================================================================


@pytest.mark.asyncio
async def test_trace_cell_row_idx_out_of_range():
    eng = _make_engine()
    note = _make_note(rows=[
        {"label": "X", "values": [1, 2], "_cell_meta": {}},
    ])
    _patch_note_query(eng, note)

    out = await eng.trace_cell(note.id, 99, 0)
    assert out["error"] == "cell_index_out_of_range"
    assert out["axis"] == "row"
    assert out["row_idx"] == 99
    assert out["row_count"] == 1
    assert out["computed_value"] is None


# ===========================================================================
# 4. col_idx 越界
# ===========================================================================


@pytest.mark.asyncio
async def test_trace_cell_col_idx_out_of_range():
    eng = _make_engine()
    note = _make_note(rows=[
        {"label": "X", "values": [1, 2], "_cell_meta": {}},
    ])
    _patch_note_query(eng, note)

    out = await eng.trace_cell(note.id, 0, 99)
    assert out["error"] == "cell_index_out_of_range"
    assert out["axis"] == "col"
    assert out["col_idx"] == 99
    assert out["col_count"] == 2
    assert out["computed_value"] is None


# ===========================================================================
# 5. evidence 限 100 行（造 200 条 _tb_cache 验证截断）
# ===========================================================================


@pytest.mark.asyncio
async def test_trace_cell_evidence_capped_at_100(monkeypatch):
    """造 200 条 account_codes + 200 条 _tb_cache，验证 trial_balance_rows ≤ 100."""
    eng = _make_engine()
    codes = [f"99{i:04d}" for i in range(200)]
    eng._tb_cache = {
        c: {"audited": float(i), "opening": 0.0, "unadjusted": 0}
        for i, c in enumerate(codes)
    }
    note = _make_note(rows=[
        {
            "label": "库存现金",
            "values": [1.0],
            "row_type": "data",
            "_cell_modes": {"0": "auto"},
            "_cell_meta": {
                "0": {
                    "manual_value": None,
                    "semantic": "closing_balance",
                    "binding_id": "五、1 货币资金.库存现金.closing_balance",
                },
            },
        },
    ])
    _patch_note_query(eng, note)
    _patch_loader(monkeypatch, _trial_balance_binding(codes))

    out = await eng.trace_cell(note.id, 0, 0)
    tb_rows = out["evidence"]["trial_balance_rows"]
    assert len(tb_rows) == 100, f"trial_balance_rows 应截断到 100，实际 {len(tb_rows)}"
    # 截取的是前 100 个 code（按列表顺序）
    assert tb_rows[0]["account_code"] == codes[0]
    assert tb_rows[99]["account_code"] == codes[99]


# ===========================================================================
# 6. note_not_found
# ===========================================================================


@pytest.mark.asyncio
async def test_trace_cell_note_not_found():
    eng = _make_engine()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=None)
    eng.db.execute = AsyncMock(return_value=result)

    out = await eng.trace_cell(uuid4(), 0, 0)
    assert out["error"] == "note_not_found"


# ===========================================================================
# 7. binding_not_found（cell_meta 有 binding_id 但 loader 无对应 row）
# ===========================================================================


@pytest.mark.asyncio
async def test_trace_cell_binding_not_found(monkeypatch):
    eng = _make_engine()
    note = _make_note(rows=[
        {
            "label": "未知行",  # ← binding 中无此 label
            "values": [100.0],
            "row_type": "data",
            "_cell_modes": {"0": "auto"},
            "_cell_meta": {
                "0": {
                    "manual_value": None,
                    "semantic": "closing_balance",
                    "binding_id": "五、1 货币资金.未知行.closing_balance",
                },
            },
        },
    ])
    _patch_note_query(eng, note)
    _patch_loader(monkeypatch, _trial_balance_binding(["1001"]))

    out = await eng.trace_cell(note.id, 0, 0)
    assert out["error"] == "binding_not_found"
    assert out["computed_value"] == 100.0
    assert out["binding_id"] == "五、1 货币资金.未知行.closing_balance"


# ===========================================================================
# 8. _expand_formula 7 source 全覆盖（纯静态字符串生成，无需 db）
# ===========================================================================


def test_expand_formula_trial_balance_sum():
    s = DisclosureEngine._expand_formula({
        "source": "trial_balance",
        "field": "audited_amount",
        "account_codes": ["1601", "1602"],
        "agg": "sum",
    })
    assert s.startswith("=")
    assert "TB('1601','audited_amount')" in s
    assert "TB('1602','audited_amount')" in s


def test_expand_formula_trial_balance_sum_minus():
    s = DisclosureEngine._expand_formula({
        "source": "trial_balance",
        "field": "opening_balance",
        "account_codes": ["1601"],
        "agg": "sum_minus",
    })
    assert s.startswith("=-")


def test_expand_formula_ledger_sum_period_filter():
    s = DisclosureEngine._expand_formula({
        "source": "ledger_sum",
        "field": "debit_amount",
        "account_codes": ["1601"],
        "period_filter": {"mode": "month_range", "start": 1, "end": 6},
    })
    assert "LEDGER_SUM" in s
    assert "month_range" in s


def test_expand_formula_aux_balance():
    s = DisclosureEngine._expand_formula({
        "source": "aux_balance",
        "field": "closing_balance",
        "account_codes": ["1122"],
        "aux_type": "customer",
    })
    assert "AUX_BALANCE" in s
    assert "customer" in s


def test_expand_formula_aging():
    s = DisclosureEngine._expand_formula({
        "source": "aux_ledger_aging",
        "account_codes": ["1122"],
        "bucket": "1年以内",
    })
    assert "AGING" in s
    assert "1年以内" in s


def test_expand_formula_prior_year_note():
    s = DisclosureEngine._expand_formula({
        "source": "prior_year_note",
        "section": "五、1 货币资金",
        "field": "value",
    })
    assert "PRIOR" in s


def test_expand_formula_manual_and_formula():
    assert "MANUAL" in DisclosureEngine._expand_formula({
        "source": "manual",
        "manual_value": 123,
    })
    assert "FORMULA" in DisclosureEngine._expand_formula({
        "source": "formula",
        "expression": "=cell(R1,C1)+cell(R2,C1)",
    })
