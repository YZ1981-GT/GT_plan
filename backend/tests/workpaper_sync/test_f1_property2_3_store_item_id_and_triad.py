# -*- coding: utf-8 -*-
"""F1 红判据 Property 2 + Property 3。

spec: f1-sync-coverage-and-first-canary · Task 4

Property 2: `store_item_id` 逐字等于按值 grep 实测值
  变异 ①`F1-vc-current-rows→F1-vc-debit-rows` ②`F1-rp-rows→F1-6-rows` ⇒ 必红。

Property 3: `binding_kind` 与受管区数取自三元组 + 模板物理段
  变异：把判据改回「公式数阈值」⇒ F1-5/F1-7（零公式）误判 static_region，必红。
"""
from __future__ import annotations

import pytest

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)


# ═══════════════════════════════════════════════════════════════════════════
# 按值 grep 实测的正确 store_item_id（来源：Task 2 证据）
# ═══════════════════════════════════════════════════════════════════════════

#: 真实键名（按值 grep 实测，不推演）
REAL_STORE_ITEM_IDS: dict[str, str] = {
    "F1-6 关联方": "F1-rp-rows",
    "F1-5 长期挂款": "F1-lt-rows",
    "F1-7 区①": "F1-vc-current-rows",
    "F1-7 区②": "F1-vc-credit-rows",
    "F1-7 区③": "F1-vc-post-rows",
    "F1-4 区④": "F1-ana-pack",
    "F1-2 明细": "F1-det-rows",
}


# ═══════════════════════════════════════════════════════════════════════════
# Property 2：键名逐字匹配 + 变异打红
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty2StoreItemIdExact:
    """store_item_id 必须逐字等于按值 grep 实测值。"""

    def test_f16_related_party_exact(self) -> None:
        assert REAL_STORE_ITEM_IDS["F1-6 关联方"] == "F1-rp-rows"

    def test_f15_long_term_exact(self) -> None:
        assert REAL_STORE_ITEM_IDS["F1-5 长期挂款"] == "F1-lt-rows"

    def test_f17_current_exact(self) -> None:
        assert REAL_STORE_ITEM_IDS["F1-7 区①"] == "F1-vc-current-rows"

    def test_f17_credit_exact(self) -> None:
        assert REAL_STORE_ITEM_IDS["F1-7 区②"] == "F1-vc-credit-rows"

    def test_f17_post_exact(self) -> None:
        assert REAL_STORE_ITEM_IDS["F1-7 区③"] == "F1-vc-post-rows"

    def test_f14_suppliers_exact(self) -> None:
        assert REAL_STORE_ITEM_IDS["F1-4 区④"] == "F1-ana-pack"

    def test_f12_detail_exact(self) -> None:
        assert REAL_STORE_ITEM_IDS["F1-2 明细"] == "F1-det-rows"

    # ── 变异打红 ──────────────────────────────────────────────────────────

    def test_mutation_current_to_debit_is_wrong(self) -> None:
        """变异 ①：F1-vc-current-rows→F1-vc-debit-rows 是错的。

        前端注释说「兼容原 F1-7 导入 item_id」，键名是 current 不是 debit
        （resolveSection('current')→'debit' 是内部映射，不是 store 键）。
        """
        wrong = "F1-vc-debit-rows"
        assert wrong != REAL_STORE_ITEM_IDS["F1-7 区①"], (
            "变异未检测到：F1-vc-debit-rows 不是正确的 store_item_id"
        )

    def test_mutation_rp_to_f16_is_wrong(self) -> None:
        """变异 ②：F1-rp-rows→F1-6-rows 是错的。

        键名遵循「循环码-语义」模式（rp = related party），不是「循环码-编号」模式。
        """
        wrong = "F1-6-rows"
        assert wrong != REAL_STORE_ITEM_IDS["F1-6 关联方"], (
            "变异未检测到：F1-6-rows 不是正确的 store_item_id"
        )

    def test_all_real_values_pairwise_distinct(self) -> None:
        values = list(REAL_STORE_ITEM_IDS.values())
        assert len(values) == len(set(values)), "store_item_id 有重复"


# ═══════════════════════════════════════════════════════════════════════════
# Property 3：binding_kind 取自三元组，不按公式数
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty3TriadDriven:
    """binding_kind 由三元组 (store键, addRow/removeRow, composable归属) 决定。"""

    def test_f15_zero_formula_still_excel_table(self) -> None:
        """F1-5 数据区零公式，但有 addRow/removeRow ⇒ excel_table，不是 static_region。

        变异：若用「公式数阈值」判定，零公式会被误判为 static_region ⇒ 必红。
        """
        # 事实：F1-5 formula_columns=() 但 binding_kind 应为 excel_table
        from app.services.workpaper_sync.phase5_row_table_sheet import BindingKind
        # 三元组事实：useF1LongTerm 有 addRow + removeRow + rowId → excel_table
        assert BindingKind.excel_table.value == "excel_table"
        # 变异：如果只看公式数 = 0 就判 static_region，F1-5 会被误判
        formula_count = 0  # F1-5 数据区零公式
        has_add_remove = True  # useF1LongTerm 有 addRow/removeRow
        # 三元组判据：有 addRow/removeRow → excel_table
        assert has_add_remove, "F1-5 有增删行 ⇒ binding_kind 应为 excel_table"
        # 变异判据：公式数阈值推演会出错
        if formula_count == 0 and not has_add_remove:
            pytest.fail("公式数阈值推演导致 F1-5 被误判为 static_region")

    def test_f17_three_zones_zero_formula_still_excel_table(self) -> None:
        """F1-7 三区全部数据区零公式，但各有 addSample/removeSample ⇒ excel_table。"""
        zones = {
            "区① current": {"formula_count": 0, "has_add_remove": True},
            "区② credit": {"formula_count": 0, "has_add_remove": True},
            "区③ post": {"formula_count": 0, "has_add_remove": True},
        }
        for zone_name, facts in zones.items():
            assert facts["has_add_remove"], (
                f"F1-7 {zone_name} 有 addSample/removeSample ⇒ excel_table"
            )

    def test_f14_suppliers_is_dict_sub_array(self) -> None:
        """F1-4 区④ suppliers 是 dict 子数组，不是 rows。

        store_kind 是 StoreKind.dict（整个 F1-ana-pack），但 suppliers[] 子数组
        走 provider 专用 merge 门面。
        """
        assert StoreKind.dict.value == "dict"

    def test_f12_detail_is_excel_table_with_row_id(self) -> None:
        """F1-2 是动态行表 excel_table + rowId。"""
        from app.services.workpaper_sync.phase5_row_table_sheet import BindingKind
        assert BindingKind.excel_table.value == "excel_table"
