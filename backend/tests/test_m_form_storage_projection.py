# -*- coding: utf-8 -*-
"""M 循环表单存储 → 单元格投影的守卫（spec `m-cycle-form-storage-cell-projection`）。

## 覆盖

1. 纯函数正向（M1 明细表 H14）
2. 10 个 provider 的 `json_key → column` 逐值对拍（读 provider 现算，不手写期望）
3. 反向：非法 JSON / 未知字段 / 超行号 / 空行 / 审定表形态
4. 幂等 + 零写入
5. 登记表与 provider 一致（前缀 / sheet_name / first_data_row）
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from app.services.wp_form_storage_projection import (
    FORM_ROW_PREFIXES,
    REASON_DETERMINATION_NOT_PROJECTED,
    REASON_FIELD_NOT_IN_PROVIDER,
    REASON_ROW_BEYOND_TEMPLATE,
    REASON_ROW_JSON_INVALID,
    project_form_rows_to_cells,
    row_prefix_for_wp_code,
)

_BACKEND = Path(__file__).resolve().parents[1]

#: 10 个 M 循环：wp_code → provider 模块名（与 FORM_ROW_PREFIXES 同源）
_M_MODULES = {code: modname for code, (_prefix, modname) in FORM_ROW_PREFIXES.items()}


def _provider_sheet(wp_code: str):
    """读 provider 的第一个 MSheetConfig（现算，不硬编码）。"""
    mod = importlib.import_module(f"app.services.workpaper_sync.{_M_MODULES[wp_code]}")
    return mod.CONFIG.sheets[0]


def _field_columns(wp_code: str) -> dict[str, str]:
    sh = _provider_sheet(wp_code)
    return {str(f.json_key): str(f.column) for f in sh.fields}


# ══════════════════════════════════════════════════════════════════════════
# 1. 登记表与 provider 一致（防「手写映射表」漂移）
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("wp_code", sorted(FORM_ROW_PREFIXES))
def test_registry_provider_module_has_config(wp_code: str) -> None:
    """每个登记项的 provider 模块必须能 import 且有一张 MSheetConfig。"""
    mod = importlib.import_module(f"app.services.workpaper_sync.{_M_MODULES[wp_code]}")
    assert getattr(mod, "CONFIG", None) is not None, f"{wp_code} provider 没有 CONFIG"
    assert mod.CONFIG.sheets, f"{wp_code} provider CONFIG.sheets 为空"
    sh = mod.CONFIG.sheets[0]
    assert sh.sheet_name, f"{wp_code} 的 sheet_name 为空"
    assert sh.first_data_row > 0, f"{wp_code} 的 first_data_row 非法"
    assert sh.last_data_row >= sh.first_data_row, f"{wp_code} 的行区间非法"
    assert sh.fields, f"{wp_code} 的 fields 为空"


@pytest.mark.parametrize("wp_code", sorted(FORM_ROW_PREFIXES))
def test_registry_prefix_is_used_by_frontend_composable(wp_code: str) -> None:
    """登记的 item_id 前缀必须真的出现在前端 composable 里（防登记了不用）。

    🔴 这条防的是「登记表写了个前缀，但前端实际写的是别的」——
    那种情况下投影永远命中不到，而纯函数单测照样全绿。
    """
    fe = _BACKEND.parent / "audit-platform" / "frontend" / "src" / "components" / "workpaper" / "composables" / f"use{wp_code}Detail.ts"
    assert fe.exists(), f"{fe.name} 不存在 —— 改名后必须同步本守卫"
    src = fe.read_text(encoding="utf-8")
    prefix = row_prefix_for_wp_code(wp_code)
    assert prefix, f"{wp_code} 没有登记前缀"
    assert prefix in src, (
        f"{wp_code} 登记的前缀 {prefix!r} 不在 {fe.name} 里。\n"
        "前端写的是别的键 ⇒ 投影永远命中不到（纯函数单测不会发现）。"
    )


# ══════════════════════════════════════════════════════════════════════════
# 2. 纯函数正向（M1 明细表 H14）
# ══════════════════════════════════════════════════════════════════════════


def test_m1_row_zero_maps_to_first_data_row() -> None:
    """`M1-M1-2-row-0-data` + `{"priorAdjAje": 100}` ⇒ `("明细表M1-2", "H14", 100)`。

    行号 = provider `first_data_row`（M1 = 14）+ 0 = 14
    列号 = provider `json_key 'priorAdjAje' → 'H'`
    """
    sh = _provider_sheet("M1")
    cells, reasons = project_form_rows_to_cells(
        wp_code="M1",
        rows=[("M1-M1-2-row-0-data", json.dumps({"priorAdjAje": 100}))],
        sheet_name=sh.sheet_name,
        first_data_row=sh.first_data_row,
        last_data_row=sh.last_data_row,
        field_columns=_field_columns("M1"),
    )
    assert not reasons, f"不该有失败原因: {reasons}"
    assert len(cells) == 1
    c = cells[0]
    assert c.sheet == "明细表M1-2"
    assert c.cell == "H14"
    assert str(c.value) == "100"


@pytest.mark.parametrize("wp_code", sorted(FORM_ROW_PREFIXES))
def test_every_provider_first_field_lands_on_first_data_row(wp_code: str) -> None:
    """10 个 provider 各自：首个字段在第 0 行必须落到 `first_data_row` + 该字段的列。

    🔴 期望值全部**读 provider 现算**（不手写）—— 手写会在 provider 改列后静默失效。
    """
    sh = _provider_sheet("M1" if wp_code == "M1" else wp_code)
    fc = _field_columns(wp_code)
    first_key = next(iter(fc))
    first_col = fc[first_key]
    prefix = row_prefix_for_wp_code(wp_code)
    cells, reasons = project_form_rows_to_cells(
        wp_code=wp_code,
        rows=[(f"{prefix}0-data", json.dumps({first_key: 42}))],
        sheet_name=sh.sheet_name,
        first_data_row=sh.first_data_row,
        last_data_row=sh.last_data_row,
        field_columns=fc,
    )
    assert not reasons, f"{wp_code} 不该有失败原因: {reasons}"
    assert len(cells) == 1, f"{wp_code} 期望 1 格，实得 {len(cells)}"
    assert cells[0].sheet == sh.sheet_name
    assert cells[0].cell == f"{first_col}{sh.first_data_row}"
    assert str(cells[0].value) == "42"


# ══════════════════════════════════════════════════════════════════════════
# 3. 反向：失败必须给原因，不得静默当 0
# ══════════════════════════════════════════════════════════════════════════


def _m1_kwargs(rows):
    sh = _provider_sheet("M1")
    return dict(
        wp_code="M1",
        rows=rows,
        sheet_name=sh.sheet_name,
        first_data_row=sh.first_data_row,
        last_data_row=sh.last_data_row,
        field_columns=_field_columns("M1"),
    )


def test_invalid_json_yields_reason_not_zero() -> None:
    cells, reasons = project_form_rows_to_cells(**_m1_kwargs([("M1-M1-2-row-0-data", "{not json")]))
    assert not cells, "解析失败不该产出任何格（更不能当 0）"
    assert any(REASON_ROW_JSON_INVALID in r for r in reasons), reasons


def test_non_object_json_yields_reason() -> None:
    cells, reasons = project_form_rows_to_cells(**_m1_kwargs([("M1-M1-2-row-0-data", "[1,2,3]")]))
    assert not cells
    assert any(REASON_ROW_JSON_INVALID in r for r in reasons), reasons


def test_unknown_field_yields_reason() -> None:
    cells, reasons = project_form_rows_to_cells(
        **_m1_kwargs([("M1-M1-2-row-0-data", json.dumps({"inventedBogusKey": 1}))])
    )
    assert not cells, "未知字段不该产出格"
    assert any(REASON_FIELD_NOT_IN_PROVIDER in r for r in reasons), reasons


def test_row_beyond_template_yields_reason() -> None:
    sh = _provider_sheet("M1")
    too_far = sh.last_data_row - sh.first_data_row + 1  # 第一行就超界
    cells, reasons = project_form_rows_to_cells(
        **_m1_kwargs([(f"M1-M1-2-row-{too_far}-data", json.dumps({"priorAdjAje": 1}))])
    )
    assert not cells
    assert any(REASON_ROW_BEYOND_TEMPLATE in r for r in reasons), reasons


def test_empty_remark_yields_no_cell_and_no_reason() -> None:
    """空行是合法态：不产出格、不报错（取值层按 cell_empty 处理，现有语义）。"""
    cells, reasons = project_form_rows_to_cells(**_m1_kwargs([("M1-M1-2-row-0-data", "")]))
    assert not cells
    assert not reasons, f"空行不该报错: {reasons}"


def test_determination_like_item_yields_reason() -> None:
    """审定表形态（`M1-1-tb-amount`）必须给「暂不支持」而不是静默跳过。"""
    cells, reasons = project_form_rows_to_cells(**_m1_kwargs([("M1-1-tb-amount", "100")]))
    assert not cells
    assert any(REASON_DETERMINATION_NOT_PROJECTED in r for r in reasons), reasons


def test_full_data_key_is_ignored() -> None:
    """整表 `*-full-data` 已在前序 spec 删除；若出现只跳过、不投影（防复活）。"""
    cells, reasons = project_form_rows_to_cells(
        **_m1_kwargs([("M1-M1-2-full-data", json.dumps([{"priorAdjAje": 1}]))])
    )
    assert not cells, "整表 full-data 不该被投影"
    # 不强制要求 reason（它可能被前面的判定逻辑吞掉），但绝不能不报错地当成明细行
    assert not any("H14" in c.cell for c in cells)


# ══════════════════════════════════════════════════════════════════════════
# 4. 幂等
# ══════════════════════════════════════════════════════════════════════════


def test_idempotent() -> None:
    kw = _m1_kwargs([("M1-M1-2-row-0-data", json.dumps({"priorAdjAje": 100, "aging": "1年以内"}))])
    a = project_form_rows_to_cells(**kw)
    b = project_form_rows_to_cells(**kw)
    assert a == b, "同输入两次调用结果必须相同"


def test_multiple_rows_ordered() -> None:
    sh = _provider_sheet("M1")
    kw = _m1_kwargs(
        [
            ("M1-M1-2-row-0-data", json.dumps({"priorAdjAje": 1})),
            ("M1-M1-2-row-1-data", json.dumps({"priorAdjAje": 2})),
        ]
    )
    cells, reasons = project_form_rows_to_cells(**kw)
    assert not reasons
    got = sorted((c.cell, str(c.value)) for c in cells)
    assert got == [
        (f"H{sh.first_data_row}", "1"),
        (f"H{sh.first_data_row + 1}", "2"),
    ], got
