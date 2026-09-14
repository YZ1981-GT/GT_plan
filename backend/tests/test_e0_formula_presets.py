"""E0 公式预设守卫（Property 15）。

结论（2026-08-03 Task 14 核实）：
E0 在 `prefill_formula_mapping.json` 和 `formula_presets_seed.json` 中均为 0 条。
数据库 `wp_formula` 表里也无 E0 相关条目（源模板 requirement 里描述的
`sheet='审定表E0-1' + wp_name='银行询证函'` 贴错标签的预设条目从未被播种）。

守卫确保将来若新增 E0 预设，其 sheet 名必须命中源 xlsx 的真实 tab 名。
"""
from __future__ import annotations

import json
from pathlib import Path

import openpyxl
import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_TEMPLATE = _BACKEND / "wp_templates" / "E" / "E0 货币资金 - 函证（Leap应对措施-函证）.xlsx"
_PREFILL = _BACKEND / "data" / "prefill_formula_mapping.json"
_SEED = _BACKEND / "data" / "formula_presets" / "formula_presets_seed.json"


@pytest.fixture(scope="module")
def e0_tab_names() -> set[str]:
    """源 xlsx 的全部 tab 名（含 hidden，供白名单比对）。"""
    if not _TEMPLATE.exists():
        pytest.skip(f"源模板不存在: {_TEMPLATE}")
    wb = openpyxl.load_workbook(_TEMPLATE, read_only=True)
    try:
        return set(wb.sheetnames)
    finally:
        wb.close()


def _load_prefill_e0() -> list[dict]:
    """从 prefill_formula_mapping.json 提取 E0 相关条目。"""
    if not _PREFILL.exists():
        return []
    data = json.loads(_PREFILL.read_text(encoding="utf-8-sig"))
    mappings = data.get("mappings", [])
    return [m for m in mappings if m.get("page_key", "").startswith("workpaper:E0")]


def _load_seed_e0() -> list[dict]:
    """从 formula_presets_seed.json 提取 E0 相关条目。"""
    if not _SEED.exists():
        return []
    data = json.loads(_SEED.read_text(encoding="utf-8-sig"))
    presets = data.get("presets", [])
    return [p for p in presets if "E0" in str(p.get("wp_code", "")) or "E0" in str(p.get("sheet", ""))]


def test_e0_prefill_is_empty():
    """E0 在 prefill_formula_mapping.json 中应为 0 条（贴错标签的条目从未播种）。"""
    entries = _load_prefill_e0()
    assert entries == [], f"E0 prefill 条目不为空: {len(entries)} 条"


def test_e0_seed_is_empty():
    """E0 在 formula_presets_seed.json 中应为 0 条。"""
    entries = _load_seed_e0()
    assert entries == [], f"E0 seed 条目不为空: {len(entries)} 条"


def test_any_future_e0_preset_sheet_must_match_source_tab(e0_tab_names):
    """若将来新增 E0 预设，其 sheet 名必须命中源 xlsx 的真实 tab 名。

    反向自检：`审定表E0-1` 不在源 xlsx tab 名中（真实为 `函证结果汇总表E0-1`）。
    """
    assert "审定表E0-1" not in e0_tab_names, "如果这通过了说明源模板改了名"
    assert "函证结果汇总表E0-1" in e0_tab_names

    # 如果有条目，每条 sheet 必须命中
    for entry in _load_prefill_e0():
        sheet = entry.get("sheet", "")
        if sheet:
            assert sheet in e0_tab_names, (
                f"E0 预设 sheet='{sheet}' 不在源 xlsx tab 名中"
            )
