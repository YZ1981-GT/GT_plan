"""灰度两态验证（Wave 6 / Task 7.1）—— 用**已落库的真实 binding 数据**驱动.

Spec:   .kiro/specs/disclosure-note-formula-data-population/
Props:  Property 10（灰度关闭数值零回归 + 唯一声明性差异）
        Property 11（灰度开启数值与 `_backfill_totals` 口径一致，公式只把黑箱显式化）

数据源：`data/note_template_bindings.json` 中由 Task 4.1 写入的
``source='formula'`` + ``formula_kind='sum'`` binding（不构造假 binding，
直接验证 shipped 数据可被引擎求值）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.disclosure_engine import DisclosureEngine
from app.services.note_formula_evaluator import NoteFormulaEvaluator

_DATA = Path(__file__).resolve().parents[2] / "data"
_BINDINGS = _DATA / "note_template_bindings.json"


# ---------------------------------------------------------------------------
# 从真实数据里挑一个 movement binding
# ---------------------------------------------------------------------------


def _load_bindings() -> dict[str, Any]:
    return json.loads(_BINDINGS.read_text(encoding="utf-8"))


def _template_index() -> dict[str, dict[str, Any]]:
    """section_number → section（listed 优先，镜像 bindings 合并口径 §V3）。"""
    out: dict[str, dict[str, Any]] = {}
    for variant in ("soe", "listed"):  # listed 后写 → 覆盖 soe
        tpl = json.loads(
            (_DATA / f"note_template_{variant}.json").read_text(encoding="utf-8")
        )
        for sec in tpl.get("sections") or []:
            num = sec.get("section_number") if isinstance(sec, dict) else None
            if isinstance(num, str) and num:
                out[num] = sec
    return out


def _find_movement_table() -> tuple[str, int, dict[str, Any], dict[str, Any]]:
    """→ (section, table_index, template_table, binding_table)：首个含 formula binding 的表。"""
    doc = _load_bindings()
    templates = _template_index()
    for section, sec in (doc.get("bindings") or {}).items():
        tpl_sec = templates.get(section)
        if not isinstance(tpl_sec, dict):
            continue
        t_tables = tpl_sec.get("tables") or []
        for ti, tbl in enumerate(sec.get("tables") or []):
            if not isinstance(tbl, dict) or ti >= len(t_tables):
                continue
            for row in (tbl.get("rows") or {}).values():
                if not isinstance(row, dict):
                    continue
                for cell in (row.get("binding") or {}).values():
                    if isinstance(cell, dict) and cell.get("source") == "formula":
                        return section, ti, t_tables[ti], tbl
    pytest.skip("数据文件中暂无 movement formula binding（Task 4.1 未 apply）")
    raise AssertionError  # pragma: no cover


@pytest.fixture(scope="module")
def movement_table() -> tuple[str, int, dict[str, Any], dict[str, Any]]:
    return _find_movement_table()


def _engine() -> DisclosureEngine:
    db = MagicMock()
    db.execute = AsyncMock()
    eng = DisclosureEngine(db)
    eng._wp_cache = {}
    eng._tb_cache = {}
    eng._wp_account_cache = {}
    eng._prior_notes_cache = {}
    return eng


def _build_table_data(
    table_template: dict[str, Any], table_binding: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """按**模板行序**（= 运行时输出行序，§V4/V5）造 table_data。

    值：期初 100 / 增 30 / 减 10，期末留 None；列位置由 header_normalize 语义决定
    （不硬编码）。行序取模板 rows（含 header_label 与合计行）—— 这也顺带验证
    Task 4.1 写入的坐标是以模板行序为基准的。
    """
    hn = table_binding.get("header_normalize") or []
    sems = [h.get("semantic") for h in hn[1:]]
    n_cols = len(sems)
    idx = {s: i for i, s in enumerate(sems) if s}
    c_open = idx["opening_balance"]
    c_inc = idx["current_year_increase"]
    c_dec = idx["current_year_decrease"]

    binding_rows = table_binding.get("rows") or {}
    rows: list[dict[str, Any]] = []
    formula_labels: list[str] = []
    for tr in table_template.get("rows") or []:
        if not isinstance(tr, dict):
            continue
        label = tr.get("label") or ""
        brow = binding_rows.get(label)
        cells = brow.get("binding") if isinstance(brow, dict) else None
        has_formula = isinstance(cells, dict) and any(
            isinstance(c, dict) and c.get("source") == "formula" for c in cells.values()
        )
        values: list[Any] = [None] * n_cols
        if has_formula:
            values[c_open] = 100.0
            values[c_inc] = 30.0
            values[c_dec] = 10.0
            formula_labels.append(label)
        is_total = bool(tr.get("is_total")) or tr.get("row_type") in (
            "total",
            "subtotal",
        )
        rows.append(
            {
                "label": label,
                "values": values,
                "is_total": is_total,
                "row_type": tr.get("row_type") or "data",
                "_cell_modes": {str(i): "auto" for i in range(n_cols)},
                "_cell_meta": {},
            }
        )
    return {"rows": rows}, formula_labels


def _ctx_for(engine: DisclosureEngine, table_binding: dict[str, Any]) -> dict[str, Any]:
    binding_rows = table_binding.get("rows") or {}
    header_normalize = table_binding.get("header_normalize") or []

    def _resolver(table_index: int, label: str, col_idx: int, cell_meta: dict):
        return engine._resolve_cell_binding(
            label, col_idx, binding_rows, header_normalize, cell_meta
        )

    return {
        "db": None,
        "project_id": None,
        "year": 2025,
        "_cell_binding_resolver": _resolver,
    }


def _closing_col(table_binding: dict[str, Any]) -> int:
    hn = table_binding.get("header_normalize") or []
    sems = [h.get("semantic") for h in hn[1:]]
    return sems.index("closing_balance")


# ---------------------------------------------------------------------------
# Property 10 —— 灰度关闭：数值零回归（期末仍为 None，绝不被 None 覆盖既有值）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_off_keeps_values_unchanged(monkeypatch, movement_table):
    from app.core import config

    monkeypatch.setattr(
        config.settings, "DISCLOSURE_NOTE_FORMULA_ENABLED", False, raising=False
    )
    _section, _ti, tt, tb = movement_table
    eng = _engine()
    table_data, labels = _build_table_data(tt, tb)
    assert labels, "应至少有一行带 formula binding"
    before = json.dumps(table_data, ensure_ascii=False, sort_keys=True)

    out = await NoteFormulaEvaluator().evaluate_table(table_data, _ctx_for(eng, tb))

    # 入参未被就地修改；产出数值与入参逐字节一致（灰度关 = 零回归）
    assert json.dumps(table_data, ensure_ascii=False, sort_keys=True) == before
    assert json.dumps(out["rows"], ensure_ascii=False, sort_keys=True) == json.dumps(
        table_data["rows"], ensure_ascii=False, sort_keys=True
    )


@pytest.mark.asyncio
async def test_flag_off_does_not_overwrite_existing_manual_number(
    monkeypatch, movement_table
):
    """灰度关时既有数值绝不被 None 覆盖。"""
    from app.core import config

    monkeypatch.setattr(
        config.settings, "DISCLOSURE_NOTE_FORMULA_ENABLED", False, raising=False
    )
    _section, _ti, tt, tb = movement_table
    eng = _engine()
    table_data, labels = _build_table_data(tt, tb)
    c_close = _closing_col(tb)
    target_row = next(r for r in table_data["rows"] if r["label"] == labels[0])
    target_row["values"][c_close] = 777.0

    out = await NoteFormulaEvaluator().evaluate_table(table_data, _ctx_for(eng, tb))
    got = next(r for r in out["rows"] if r["label"] == labels[0])
    assert got["values"][c_close] == pytest.approx(777.0)


# ---------------------------------------------------------------------------
# Property 11 —— 灰度开启：恒等式数值正确 + 合计与 `_backfill_totals` 一致
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_on_fills_movement_identity(monkeypatch, movement_table):
    from app.core import config

    monkeypatch.setattr(
        config.settings, "DISCLOSURE_NOTE_FORMULA_ENABLED", True, raising=False
    )
    _section, _ti, tt, tb = movement_table
    eng = _engine()
    table_data, labels = _build_table_data(tt, tb)
    c_close = _closing_col(tb)

    out = await NoteFormulaEvaluator().evaluate_table(table_data, _ctx_for(eng, tb))

    filled = 0
    for label in labels:
        row = next(r for r in out["rows"] if r["label"] == label)
        assert row["values"][c_close] == pytest.approx(120.0), label  # 100 + 30 - 10
        filled += 1
    assert filled == len(labels)


@pytest.mark.asyncio
async def test_flag_on_totals_equal_manual_equivalent(monkeypatch, movement_table):
    """公式只把黑箱显式化：合计数值与"人工填同样期末数"完全一致。"""
    from app.core import config

    monkeypatch.setattr(
        config.settings, "DISCLOSURE_NOTE_FORMULA_ENABLED", True, raising=False
    )
    _section, _ti, tt, tb = movement_table
    eng = _engine()
    c_close = _closing_col(tb)

    # A：公式路径
    td_formula, labels = _build_table_data(tt, tb)
    n_cols = len(td_formula["rows"][0]["values"])
    out = await NoteFormulaEvaluator().evaluate_table(td_formula, _ctx_for(eng, tb))
    DisclosureEngine._backfill_totals(out["rows"], n_cols)

    # B：人工填同样数值（不经公式）
    td_manual, _labels = _build_table_data(tt, tb)
    for label in labels:
        row = next(r for r in td_manual["rows"] if r["label"] == label)
        row["values"][c_close] = 120.0
    DisclosureEngine._backfill_totals(td_manual["rows"], n_cols)

    got = [r["values"] for r in out["rows"]]
    expected = [r["values"] for r in td_manual["rows"]]
    assert got == expected
