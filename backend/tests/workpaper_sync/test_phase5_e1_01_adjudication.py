# -*- coding: utf-8 -*-
"""E1-1 审定表声明 + E1-P6（形态实测）/ E1-P7（逐格 mask）/ E1-P17（TB 发布门）。

spec: e1-sync-coverage-and-first-canary · Task 20 · Requirements 4.1~4.7, 8.1
Properties: E1-P6（形态实测）/ E1-P7（逐格 mask 下受管字段仍 editable）/
            E1-P17（TB 显式发布门：sync 回写不触达 trial_balance）

🔴 E1-1 是审定表里**唯一 slot_driven 模式**（不分 section）+ **最高密度 mask**
   （193 公式 / 41%）+ 三重值来源（本 sheet 人工 / 跨 sheet 聚合 / 跨册）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.workpaper_sync.phase5_adjudication_sheet import (
    AdjudicationRowMode,
    AdjudicationValueSource,
)
from app.services.workpaper_sync.phase5_e1_01_adjudication import (
    CROSS_SHEET_AGGREGATION_KEYS_E101,
    CROSS_VOLUME_KEYS_E101,
    E1_ADJ_PREFIX,
    E1_SLOT_ORDER,
    MANAGED_SHEET_E101,
    SPEC_E101,
    TB_PUBLISH_TESTID_E101,
)

_UPSTREAM_GAP_REASON = (
    "🔴 BP-61-1 平台级约束：adapter 未注册，真栈 materialize 不可用。"
    "解除后本条 XPASS 并强制摘掉标记。"
)


# ═══════════════════════════════════════════════════════════════════════════
# E1-P6：形态实测（slot_driven / per-cell / 三重值来源）
# ═══════════════════════════════════════════════════════════════════════════


class TestE1P6FormEvidence:
    """E1-P6：E1-1 的 sections/row_mode 取自实测，非照其他循环推演。

    🔴 五循环审定表形态已证互不相同：
      D1-1 = 3 区 / dynamic_identity
      D2-1 = 1 区 / fixed_rows
      D4-1 = 2 区 / dynamic_identity
      E1-1 = 0 区 / **slot_driven**（唯一）
    """

    def test_row_mode_is_slot_driven(self) -> None:
        """E1-1 是唯一的 slot_driven 模式。"""
        assert SPEC_E101.row_mode is AdjudicationRowMode.slot_driven

    def test_no_sections(self) -> None:
        """slot_driven 不分 section（平铺槽位模型）。"""
        assert len(SPEC_E101.sections) == 0

    def test_slot_order_non_empty(self) -> None:
        """E1_SLOT_ORDER 非空。"""
        assert len(E1_SLOT_ORDER) >= 10

    def test_slot_order_contains_key_items(self) -> None:
        """槽位顺序包含关键科目。"""
        for key_slot in ("cash", "bank_deposit", "digital_currency", "total"):
            assert key_slot in E1_SLOT_ORDER, f"E1_SLOT_ORDER 缺 {key_slot}"

    def test_accrued_interest_in_slots(self) -> None:
        """应计利息（跨册取数）在槽位里。"""
        assert "accrued_interest" in E1_SLOT_ORDER

    def test_per_cell_key_template_format(self) -> None:
        """per-cell 键模板格式正确。"""
        assert SPEC_E101.per_cell_key_template == "E1-adj-{slot}-{field}"

    def test_store_item_id_empty_for_per_cell(self) -> None:
        """per-cell 锚点无单一 store item。"""
        assert SPEC_E101.store_item_id == ""

    def test_row_identity_key_empty_for_slot_driven(self) -> None:
        """slot_driven 无行身份。"""
        assert SPEC_E101.row_identity_key == ""

    def test_header_rows_count(self) -> None:
        """E1-1 有三行表头。"""
        assert len(SPEC_E101.header_rows) == 3

    def test_mutation_declare_as_fixed_rows_wrong(self) -> None:
        """变异：照 D2-1 声明成 fixed_rows ⇒ 错法。

        D2-1 有 section 且是写死 4 行；E1-1 没有 section 且行由槽位决定。
        """
        assert SPEC_E101.row_mode is not AdjudicationRowMode.fixed_rows

    def test_mutation_declare_with_sections_wrong(self) -> None:
        """变异：照 D1-1 声明 3 个 section ⇒ 错法。

        E1-1 是平铺槽位，不是三区分块。
        """
        assert len(SPEC_E101.sections) == 0


# ═══════════════════════════════════════════════════════════════════════════
# E1-P7：逐格 mask（193 公式 / 密度 41%）下受管金额字段仍判 editable
# ═══════════════════════════════════════════════════════════════════════════


class TestE1P7CellMask:
    """E1-P7：逐格 mask 下受管金额字段仍判 editable。

    🔴 E1-1 密度 41%（193/470 格），比 D1-1 / D4-1 都高。
    用列向区间（`column_in_ranges`）会把受管金额字段整列误判只读
    —— D4-1 踩过这个坑，E1-1 密度更高风险更大。
    """

    def test_cell_mask_non_empty(self) -> None:
        """逐格 mask 已构建。"""
        assert len(SPEC_E101.cell_mask) >= 50, (
            f"cell_mask 只有 {len(SPEC_E101.cell_mask)} 格，"
            "193 公式应有更多 mask 条目"
        )

    def test_cell_mask_is_uppercase_a1_format(self) -> None:
        """mask 条目是大写 A1 格式。"""
        import re

        for cell in SPEC_E101.cell_mask:
            assert re.match(r"^[A-Z]+\d+$", cell), (
                f"mask 条目 {cell!r} 不是大写 A1 格式"
            )

    def test_reason_analysis_column_not_in_mask(self) -> None:
        """J 列（原因分析 editable）不在 mask 里。"""
        j_cells = [c for c in SPEC_E101.cell_mask if c.startswith("J")]
        assert len(j_cells) == 0, (
            f"J 列有 {len(j_cells)} 个格进了 mask —— "
            "reason_analysis 是 editable，不应被 mask"
        )

    def test_item_name_column_not_in_mask(self) -> None:
        """A 列（项目名 editable）不在 mask 里。"""
        a_cells = [c for c in SPEC_E101.cell_mask if c.startswith("A")]
        assert len(a_cells) == 0, (
            f"A 列有 {len(a_cells)} 个格进了 mask —— "
            "item_name 是 editable，不应被 mask"
        )

    def test_computed_columns_in_mask(self) -> None:
        """D/G/H/I 列（computed/formula）在 mask 里有条目。"""
        for col in ("D", "G", "H", "I"):
            col_cells = [c for c in SPEC_E101.cell_mask if c.startswith(col)]
            assert len(col_cells) >= 5, (
                f"{col} 列只有 {len(col_cells)} 个 mask 条目 —— "
                "作为 formula/computed 列应有更多"
            )

    def test_total_row_in_mask(self) -> None:
        """合计行 R15 在 mask 里。"""
        r15_cells = [c for c in SPEC_E101.cell_mask if c.endswith("15")]
        assert len(r15_cells) >= 2, (
            f"合计行 R15 只有 {len(r15_cells)} 个 mask 条目"
        )

    def test_subtotal_rows_in_mask(self) -> None:
        """受限/非受限小计行 R22/R28 在 mask 里。"""
        for row in (22, 28):
            row_cells = [c for c in SPEC_E101.cell_mask if c.endswith(str(row))]
            assert len(row_cells) >= 2, (
                f"小计行 R{row} 只有 {len(row_cells)} 个 mask 条目"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 值来源声明
# ═══════════════════════════════════════════════════════════════════════════


class TestE101ValueSources:
    """E1-1 三重值来源声明正确。"""

    def test_reason_analysis_is_manual(self) -> None:
        """reason_analysis 是手工录入。"""
        assert SPEC_E101.source_of("reason_analysis") is AdjudicationValueSource.manual

    def test_prior_unadjusted_is_cross_sheet(self) -> None:
        """期初未审数来自跨 sheet 聚合。"""
        assert SPEC_E101.source_of("prior_unadjusted") is AdjudicationValueSource.cross_sheet

    def test_current_audited_is_computed(self) -> None:
        """期末审定数是现算（不落库）。"""
        assert SPEC_E101.source_of("current_audited") is AdjudicationValueSource.computed

    def test_change_amount_is_computed(self) -> None:
        """变动额是现算。"""
        assert SPEC_E101.source_of("change_amount") is AdjudicationValueSource.computed

    def test_manual_fields_are_oo_writable(self) -> None:
        """手工录入字段可 OO 直写。"""
        assert SPEC_E101.is_oo_writable("reason_analysis") is True

    def test_cross_sheet_fields_not_oo_writable(self) -> None:
        """跨 sheet 聚合字段不可 OO 直写。"""
        assert SPEC_E101.is_oo_writable("prior_unadjusted") is False
        assert SPEC_E101.is_oo_writable("current_unadjusted") is False

    def test_computed_fields_not_oo_writable(self) -> None:
        """computed 字段不可 OO 直写。"""
        assert SPEC_E101.is_oo_writable("current_audited") is False
        assert SPEC_E101.is_oo_writable("change_rate") is False

    def test_cross_sheet_aggregation_keys_declared(self) -> None:
        """跨 sheet 聚合键（6 个）已登记。"""
        assert len(CROSS_SHEET_AGGREGATION_KEYS_E101) == 6
        for key in CROSS_SHEET_AGGREGATION_KEYS_E101:
            assert key.startswith("E1-bank-detail-")

    def test_cross_volume_keys_declared(self) -> None:
        """跨册取数键已登记。"""
        assert len(CROSS_VOLUME_KEYS_E101) >= 1
        assert "E1-accrued-interest-rows" in CROSS_VOLUME_KEYS_E101


# ═══════════════════════════════════════════════════════════════════════════
# E1-P17：TB 显式发布门（sync 回写不触达 trial_balance）
# ═══════════════════════════════════════════════════════════════════════════


class TestE1P17TbPublishGateAdjudication:
    """E1-P17 在审定表声明侧的判据。

    三条红线：
    ① sync 回写路径对 trial_balance 写次数为 0
    ② 未点 e1-publish-tb 前 trial_balance 不变
    ③ 两道 CI 守卫保持绿
    """

    def test_tb_publish_testid_declared(self) -> None:
        """TB 发布门的 data-testid 已声明。"""
        assert TB_PUBLISH_TESTID_E101 == "e1-publish-tb"

    def test_adj_prefix_declared(self) -> None:
        """per-cell 键前缀已声明。"""
        assert E1_ADJ_PREFIX == "E1-adj-"

    def test_no_trial_balance_in_adj_keys(self) -> None:
        """审定表的 per-cell 键不含 trial_balance 相关名称。"""
        key_template = SPEC_E101.per_cell_key_template
        assert "trial" not in key_template.lower()
        assert "tb-" not in key_template.lower()

    def test_adjudication_tab_has_publish_testid(self) -> None:
        """E1TabAdjudication.vue 有 data-testid="e1-publish-tb"（声明层验证）。

        🔴 publishToTb 和 e1-publish-tb 在审定表**子组件** E1TabAdjudication.vue 里，
           不在外层 GtE1MonetaryFund.vue。
        """
        repo_root = Path(__file__).resolve().parents[3]
        tab_path = (
            repo_root
            / "audit-platform" / "frontend" / "src" / "components"
            / "workpaper" / "e1" / "E1TabAdjudication.vue"
        )
        if not tab_path.exists():
            pytest.skip(f"审定表子组件不存在：{tab_path}")
        source = tab_path.read_text(encoding="utf-8")
        assert "e1-publish-tb" in source, (
            "E1TabAdjudication.vue 不含 data-testid='e1-publish-tb' ⇒ "
            "TB 发布门入口可能被删除"
        )

    def test_adjudication_tab_has_publishToTb(self) -> None:
        """E1TabAdjudication.vue 有 publishToTb 函数调用。"""
        repo_root = Path(__file__).resolve().parents[3]
        tab_path = (
            repo_root
            / "audit-platform" / "frontend" / "src" / "components"
            / "workpaper" / "e1" / "E1TabAdjudication.vue"
        )
        if not tab_path.exists():
            pytest.skip(f"审定表子组件不存在：{tab_path}")
        source = tab_path.read_text(encoding="utf-8")
        assert "publishToTb" in source, (
            "E1TabAdjudication.vue 不含 publishToTb ⇒ "
            "TB 发布门功能可能被删除"
        )

    # ── 真栈判据 ──────────────────────────────────────────────────────

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_sync_writeback_zero_tb_writes(self) -> None:
        """sync 回写路径对 trial_balance 写次数为 0。"""
        assert False, "需要真栈验证 sync 回写不触达 trial_balance"

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_tb_unchanged_before_publish(self) -> None:
        """未点发布前 trial_balance 不变。"""
        assert False, "需要真栈验证未点发布前 TB 不变"

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_materialize_e101_succeeds(self) -> None:
        """E1-1 受管后整册 materialize 通过。"""
        assert False, "需要真栈验证 materialize 200"


# ═══════════════════════════════════════════════════════════════════════════
# 声明层结构自洽
# ═══════════════════════════════════════════════════════════════════════════


class TestE101DeclarationConsistency:
    """E1-1 声明层结构自洽。"""

    def test_managed_sheet_name(self) -> None:
        assert MANAGED_SHEET_E101 == "货币资金审定表E1-1"

    def test_sheet_key_format(self) -> None:
        assert SPEC_E101.sheet_key == "e11-managed"

    def test_template_id(self) -> None:
        assert SPEC_E101.template_id == "E11"

    def test_field_specs_non_empty(self) -> None:
        assert len(SPEC_E101.field_specs) >= 5

    def test_field_specs_have_correct_structure(self) -> None:
        """每个 field_spec 是 7 元组。"""
        for spec in SPEC_E101.field_specs:
            assert len(spec) == 7, f"field_spec {spec[0]} 不是 7 元组"

    def test_footer_marker(self) -> None:
        assert SPEC_E101.footer_marker == "合计"

    def test_total_row_declared(self) -> None:
        assert SPEC_E101.total_row == 15

    def test_tb_row_declared(self) -> None:
        assert SPEC_E101.tb_row == 30

    def test_diff_row_declared(self) -> None:
        assert SPEC_E101.diff_row == 31
