# -*- coding: utf-8 -*-
"""D4-33/34/35/36 item_id 映射 + 死配置清理守卫（源码结构级）。

锁定 spec d4-33-36-writeback-formula-and-io-closure：
- sheet → item_id 六条字面量映射到 -data 键（Requirement 1.5 / Property 2）
- 四表任一 sheet 不得回退到 f"{sheet}-rows" 兜底
- _SUPPORTED_SHEETS / _SHEET_HEADERS 不含 D4-34 / D4-36 主键（Requirement 1.6 / Property 12）
"""
from pathlib import Path

from app.routers.wp_render_strategies import _d4_import_export as m

_SRC = Path(m.__file__).read_text(encoding="utf-8")


# ─── Property 2: item_id 映射到 -data 键（export + import 两处）──────────────

def test_item_id_maps_to_data_keys_both_ends():
    """四表 sheet → item_id 必须映到 -data 键，export 与 import 两处都要有。"""
    # D4-33 → D4-33-data（export + import 两处）
    assert _SRC.count('item_id = "D4-33-data"') >= 2
    # D4-35 → D4-35-data（export + import 两处）
    assert _SRC.count('item_id = "D4-35-data"') >= 2
    # D4-34 子键 → D4-34-data（elif sheet in (...) 形态，export + import 各一处）
    assert _SRC.count('item_id = "D4-34-data"') >= 2
    assert _SRC.count('elif sheet in ("D4-34-rental", "D4-34-consult"):') >= 2
    # D4-36 子键 → D4-36-data
    assert _SRC.count('item_id = "D4-36-data"') >= 2
    assert _SRC.count('elif sheet in ("D4-36-forward", "D4-36-backward"):') >= 2


def test_no_rows_fallback_for_d4_33_36():
    """🔴 四表任一 sheet 不得残留把它映到 f"{sheet}-rows" 的显式 elif（默认 fallback 不算）。"""
    for iid in ("D4-33-rows", "D4-34-rows", "D4-34-rental-rows", "D4-34-consult-rows",
                "D4-35-rows", "D4-36-rows", "D4-36-forward-rows", "D4-36-backward-rows"):
        assert f'item_id = "{iid}"' not in _SRC, f"{iid} 是错位键，不得出现"


# ─── Property 12: 死配置清理 ─────────────────────────────────────────────────

def test_d4_34_36_master_keys_removed_from_supported():
    """D4-34 / D4-36 主键（组件无入口）必须已从 _SUPPORTED_SHEETS 删除。"""
    assert "D4-34" not in m._SUPPORTED_SHEETS, "D4-34 主键是死配置，应删"
    assert "D4-36" not in m._SUPPORTED_SHEETS, "D4-36 主键是死配置，应删"
    # 子键仍保留
    assert "D4-34-rental" in m._SUPPORTED_SHEETS
    assert "D4-34-consult" in m._SUPPORTED_SHEETS
    assert "D4-36-forward" in m._SUPPORTED_SHEETS
    assert "D4-36-backward" in m._SUPPORTED_SHEETS


def test_d4_34_36_master_keys_removed_from_headers():
    """D4-34 / D4-36 主键必须已从 _SHEET_HEADERS 删除。"""
    assert "D4-34" not in m._SHEET_HEADERS, "D4-34 主键列头是死配置，应删"
    assert "D4-36" not in m._SHEET_HEADERS, "D4-36 主键列头是死配置，应删"
    # 子键列头仍在
    assert "D4-34-rental" in m._SHEET_HEADERS
    assert "D4-36-forward" in m._SHEET_HEADERS


def test_d4_33_still_registered():
    """D4-33 单键仍登记（它有前端下拉入口）。"""
    assert "D4-33" in m._SUPPORTED_SHEETS
    assert "D4-33" in m._SHEET_HEADERS


def test_supported_sheets_have_frontend_entry():
    """Property 12：D4-33~36 相关的每个 supported sheet 都是前端真实消费的子键。"""
    d4_33_36 = {s for s in m._SUPPORTED_SHEETS if s.startswith(("D4-33", "D4-34", "D4-35", "D4-36"))}
    # 只应有这 6 个（无主键 D4-34/D4-36）
    assert d4_33_36 == {"D4-33", "D4-34-rental", "D4-34-consult", "D4-35", "D4-36-forward", "D4-36-backward"}
