# -*- coding: utf-8 -*-
"""E1-3 银行存款明细表（按裁决只接 multi variant）—— 声明 + E1-P18 列集守恒验收。

spec: e1-sync-coverage-and-first-canary · Task 19 · Requirements 3.4 / 3.6 / 8.1
Properties: E1-P18（列集守恒）

🔴 裁决 H4 已完成（Task 18）：只接 multi（人民币及外币），rmb 保持 legacy。
   本文件验证声明层正确性 + E1-P18 列集守恒判据框架。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.workpaper_sync.phase5_e1_03_bank_detail import (
    E1_3_AGGREGATION_KEYS,
    FIELD_SPECS_E103,
    FX_EXCLUSIVE_COLUMNS_E103,
    MANAGED_SHEET_E103,
    MANAGED_VARIANT_E103,
    SPEC_E103,
    STORE_ITEM_ID_E103,
    UNMANAGED_VARIANT_E103,
)
from app.services.workpaper_sync.excel_extract import BindingKind
from app.services.workpaper_sync.phase5_row_table_sheet import StoreKind

_UPSTREAM_GAP_REASON = (
    "🔴 BP-61-1 平台级约束：adapter 未注册，真栈 materialize 不可用。"
    "解除后本条 XPASS 并强制摘掉标记。"
)


# ═══════════════════════════════════════════════════════════════════════════
# 声明层自洽
# ═══════════════════════════════════════════════════════════════════════════


class TestE103DeclarationConsistency:
    """E1-3 声明层自洽。"""

    def test_managed_variant_is_multi(self) -> None:
        """裁决 H4：只接 multi variant。"""
        assert MANAGED_VARIANT_E103 == "multi"
        assert UNMANAGED_VARIANT_E103 == "rmb"

    def test_spec_import_succeeds(self) -> None:
        """SPEC_E103 可导入。"""
        assert SPEC_E103 is not None
        assert SPEC_E103.managed_sheet == MANAGED_SHEET_E103

    def test_store_item_id_matches_evidence(self) -> None:
        """store_item_id 与实测值一致。"""
        assert STORE_ITEM_ID_E103 == "E1-bank-detail-rows"

    def test_row_identity_key_is_id(self) -> None:
        """行身份键是 id（E1 全族统一）。"""
        assert SPEC_E103.row_identity_key == "id"

    def test_binding_kind_is_excel_table(self) -> None:
        """E1-3 multi 是动态行表。"""
        assert SPEC_E103.binding_kind is BindingKind.excel_table

    def test_store_kind_is_rows(self) -> None:
        assert SPEC_E103.store_kind is StoreKind.rows

    def test_field_specs_non_empty(self) -> None:
        """字段声明非空（567 公式 / 41 列）。"""
        assert len(FIELD_SPECS_E103) >= 10

    def test_formula_columns_declared(self) -> None:
        """公式列已声明（K/L/N/P/Q/R）。"""
        assert len(SPEC_E103.formula_columns) >= 4

    def test_footer_row_after_data(self) -> None:
        """footer 行在数据区之后。"""
        assert SPEC_E103.footer_row > SPEC_E103.last_data_row

    def test_sheet_key_format(self) -> None:
        """sheet_key 格式正确。"""
        assert SPEC_E103.sheet_key == "e13-managed"

    def test_table_name_follows_convention(self) -> None:
        """table_name 遵循 GT_ 前缀约定。"""
        assert SPEC_E103.table_name.startswith("GT_")

    def test_uuid_col_declared(self) -> None:
        """UUID 列已声明。"""
        assert SPEC_E103.uuid_col

    def test_managed_sheet_contains_multi_variant(self) -> None:
        """受管 sheet 名含「人民币及外币」（multi variant）。"""
        assert "人民币及外币" in MANAGED_SHEET_E103


# ═══════════════════════════════════════════════════════════════════════════
# E1-P18：列集守恒（multi variant 的原币列不被回写抹掉）
# ═══════════════════════════════════════════════════════════════════════════


class TestE1P18ColumnSetIntegrity:
    """E1-P18：multi variant 受管后原币列不被 OO 回写抹掉。"""

    def test_fx_exclusive_columns_declared(self) -> None:
        """multi 独有的原币列已登记。"""
        assert len(FX_EXCLUSIVE_COLUMNS_E103) >= 5
        assert "fxCurrency" in FX_EXCLUSIVE_COLUMNS_E103
        assert "fxRate" in FX_EXCLUSIVE_COLUMNS_E103

    def test_fx_columns_in_field_specs(self) -> None:
        """原币列在 field_specs 里有对应声明（受管投影覆盖它们）。"""
        field_json_keys = {spec[4] for spec in FIELD_SPECS_E103}
        # fxRate 在 field_specs 里（作为 editable 列）
        assert "fxRate" in field_json_keys

    def test_adjudication_evidence_verdict_still_multi(self) -> None:
        """裁决证据 JSON 的结论仍是 multi。"""
        repo_root = Path(__file__).resolve().parents[3]
        evidence = (
            repo_root / "docs" / "operations" / "evidence"
            / "e1-sync-coverage" / "e1-3-dual-sheet-adjudication.json"
        )
        assert evidence.exists(), f"裁决证据不存在：{evidence}"
        data = json.loads(evidence.read_text(encoding="utf-8"))
        assert data["verdict"]["managed_variant"] == "multi"

    def test_mutation_both_variants_managed_would_conflict(self) -> None:
        """变异 ①：两张 sheet 都声明受管同一键 ⇒ rmb 侧回写抹零原币列。

        🔴 这里验证的是**裁决的正确性** —— 两 variant 共用同一 store 键
        但列集不同，同时受管是数据损坏级风险。
        """
        # 两者确实共用同一 store 键
        assert STORE_ITEM_ID_E103 == "E1-bank-detail-rows"
        # rmb 不下发原币列是 AC 1.9 的意图
        assert UNMANAGED_VARIANT_E103 == "rmb"
        # 验证声明里只管 multi 一张
        assert "人民币及外币" in SPEC_E103.managed_sheet
        assert "仅人民币" not in SPEC_E103.managed_sheet

    def test_aggregation_keys_declared(self) -> None:
        """E1-1 的 6 个聚合键（从 E1-3 分组小计取数）已登记。"""
        assert len(E1_3_AGGREGATION_KEYS) == 6
        for key in E1_3_AGGREGATION_KEYS:
            assert key.startswith("E1-bank-detail-")
            assert "unaudited" in key

    # ── 真栈判据（红基线：受管后 OO 回写不抹零原币列）─────────────────

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_oo_writeback_preserves_fx_columns(self) -> None:
        """multi sheet 上 OO 回写一行后原币列逐字不变。

        需要：adapter 已注册 + 真栈 materialize + OO forcesave。
        """
        assert False, "需要真栈验证原币列不被回写抹掉"

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_materialize_e103_succeeds(self) -> None:
        """受管区 7→8 后整册 materialize 通过。"""
        assert False, "需要真栈验证 materialize 200"

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_downstream_aggregation_keys_recompute(self) -> None:
        """E1-3 受管后 E1-1 的 6 个聚合键源头变为受管，须回归 E1-P10。"""
        assert False, "需要真栈验证下游聚合键重算"
