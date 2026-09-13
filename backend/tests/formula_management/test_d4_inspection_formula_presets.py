# -*- coding: utf-8 -*-
"""D4-14/15/16 检查表 F-SHELL 公式预设契约测试 + 后端执行同定义验证 + 解析失败保留原值。

Spec: d4-inspection-writeback-formula-io Task 2
Requirements: 2.1, 2.2, 2.3, 2.4, 5.2

验证：
  1. 预设定义合法且可通过 effective_formula 解析（Req 2.1）
  2. 后端执行与前端同定义产出同结果（Req 2.2）
  3. 解析失败保留原值（Req 2.3 / 不转零）
  4. 双模式 gate 正确标记阻塞态（Req 2.3）
  5. 变异检验：至少 2 处变异 RED
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.services.formula_management.effective_formula import (
    EffectiveFormula,
    make_formula_key,
    resolve_effective_formula,
    validate_expression,
)
from app.services.formula_management.d4_formula_cell_verdict import (
    FormulaCellVerdict,
    verdict_from_evaluation,
)
from app.services.formula_management.d4_inspection_formula_verdict import (
    InspectionFormulaResult,
    d4_14_sum_amounts,
    d4_14_coverage_rate,
    d4_14_occurrence_diff,
    d4_15_completeness_diff,
    d4_15_sum_completeness,
    d4_16_ports_diff,
    d4_16_tax_diff,
    d4_16_sum_diffs,
    resolve_and_execute,
    check_dual_mode_gate,
    DUAL_MODE_STATUS,
)
from app.services.formula_management.preset_library import (
    load_seed_presets,
    build_preset_index,
    find_presets_for_page,
)

# ══════════════════════════════════════════════════════════════════════════════
# 1. 预设定义有效性（Req 2.1）
# ══════════════════════════════════════════════════════════════════════════════

# D4-14/15/16 预设 target_cell 列表
_D4_INSPECTION_TARGETS = [
    "D4-14-凭证金额合计",
    "D4-14-出库金额合计",
    "D4-14-发票金额合计",
    "D4-14-检查比例",
    "D4-14-发生一致性判定",
    "D4-15-isConsistent",
    "D4-15-发货单金额合计",
    "D4-15-发票金额合计",
    "D4-15-记账凭证金额合计",
    "D4-16-portsDiff",
    "D4-16-taxDiff",
    "D4-16-portsDiff-total",
    "D4-16-taxDiff-total",
]


@pytest.fixture(scope="module")
def all_presets():
    return load_seed_presets()


@pytest.fixture(scope="module")
def preset_index(all_presets):
    return build_preset_index(all_presets)


@pytest.fixture(scope="module")
def d4_page_presets(all_presets):
    return [p for p in all_presets if p.page_key == "workpaper:D4"]


class TestPresetDefinitionsValid:
    """每条 D4-14/15/16 预设有 expression/refs，expression 全过白名单。"""

    def test_all_inspection_targets_exist(self, d4_page_presets):
        """Validates: Requirements 2.1 — 每个检查表公式预设均已注册。"""
        existing_targets = {p.target_cell for p in d4_page_presets}
        for target in _D4_INSPECTION_TARGETS:
            assert target in existing_targets, (
                f"预设 target_cell={target!r} 未在 seed 中找到"
            )

    def test_no_duplicate_targets(self, d4_page_presets):
        """Validates: Requirements 2.1 — 同 page_key 下 target_cell 唯一。"""
        seen: set[str] = set()
        for p in d4_page_presets:
            key = p.target_cell
            assert key not in seen, f"重复 target_cell: {key}"
            seen.add(key)

    @pytest.mark.parametrize("target", _D4_INSPECTION_TARGETS)
    def test_expression_passes_whitelist(self, target, d4_page_presets):
        """Validates: Requirements 2.1 — expression 全过白名单（禁 eval/外链）。"""
        preset = next(
            (p for p in d4_page_presets if p.target_cell == target), None
        )
        assert preset is not None, f"target={target} 未找到"
        assert preset.expression, f"target={target} expression 为空"
        ok, reason = validate_expression(preset.expression)
        assert ok, f"target={target} 表达式校验失败：{reason}"

    @pytest.mark.parametrize("target", _D4_INSPECTION_TARGETS)
    def test_preset_has_refs(self, target, d4_page_presets):
        """Validates: Requirements 2.1 — 预设包含 refs。"""
        preset = next(
            (p for p in d4_page_presets if p.target_cell == target), None
        )
        assert preset is not None
        assert isinstance(preset.refs, list) and len(preset.refs) > 0, (
            f"target={target} refs 为空"
        )

    @pytest.mark.parametrize("target", _D4_INSPECTION_TARGETS)
    def test_preset_has_source(self, target, d4_page_presets):
        """Validates: Requirements 2.1 — 预设标注来源 d4_inspection_formula。"""
        preset = next(
            (p for p in d4_page_presets if p.target_cell == target), None
        )
        assert preset is not None
        assert preset.source == "d4_inspection_formula", (
            f"target={target} source={preset.source}，expected d4_inspection_formula"
        )

    @pytest.mark.parametrize("target", _D4_INSPECTION_TARGETS)
    def test_resolvable_through_effective_formula(self, target, preset_index):
        """Validates: Requirements 2.1 — 预设可通过 effective_formula resolve。"""
        key = make_formula_key(
            wp_id="test-wp",
            stable_sheet_key="workpaper:D4",
            row_key=target,
            field_key=target,
        )
        eff = resolve_effective_formula(key, preset_index=preset_index)
        assert eff.state == "preset", (
            f"target={target} resolve state={eff.state}, expected 'preset'"
        )
        assert eff.expression is not None


# ══════════════════════════════════════════════════════════════════════════════
# 2. 后端执行与前端同定义产出同结果（Req 2.2）
# ══════════════════════════════════════════════════════════════════════════════

class TestBackendFrontendSameDefinition:
    """后端纯函数 vs 前端 calc* 函数同定义验证。"""

    def test_d4_14_sum_voucher(self):
        """Validates: Requirements 2.2 — D4-14 凭证金额合计 = SUM(item.voucher.amount)。"""
        items = [
            {"voucher": {"amount": 100}},
            {"voucher": {"amount": 250.5}},
            {"voucher": {"amount": 0}},
        ]
        result = d4_14_sum_amounts(items, "voucher")
        assert result == Decimal("350.5")

    def test_d4_14_sum_delivery(self):
        """Validates: Requirements 2.2 — D4-14 出库金额合计。"""
        items = [
            {"delivery": {"amount": 200}},
            {"delivery": {"amount": 300}},
        ]
        result = d4_14_sum_amounts(items, "delivery")
        assert result == Decimal("500")

    def test_d4_14_coverage_rate(self):
        """Validates: Requirements 2.2 — 检查比例 = 凭证合计 / 审定合计。"""
        rate = d4_14_coverage_rate(Decimal("500"), Decimal("10000"))
        assert rate == Decimal("0.05")

    def test_d4_14_coverage_rate_zero_revenue(self):
        """Validates: Requirements 2.2 — 审定合计=0 时返回 0（除零保护）。"""
        rate = d4_14_coverage_rate(Decimal("500"), Decimal("0"))
        assert rate == Decimal("0")

    def test_d4_14_occurrence_diff_zero(self):
        """Validates: Requirements 2.2 — 凭证=出库 → 差异 0（一致）。"""
        diff = d4_14_occurrence_diff(Decimal("1000"), Decimal("1000"))
        assert diff == Decimal("0")

    def test_d4_14_occurrence_diff_nonzero(self):
        """Validates: Requirements 2.2 — 凭证≠出库 → 差异非零（不一致）。"""
        diff = d4_14_occurrence_diff(Decimal("1000"), Decimal("800"))
        assert diff == Decimal("200")

    def test_d4_15_completeness_diff_consistent(self):
        """Validates: Requirements 2.2 — 发货=发票 → 差异 0（一致）。"""
        diff = d4_15_completeness_diff(Decimal("500"), Decimal("500"))
        assert diff == Decimal("0")

    def test_d4_15_completeness_diff_inconsistent(self):
        """Validates: Requirements 2.2 — 发货≠发票 → 差异非零。"""
        diff = d4_15_completeness_diff(Decimal("500"), Decimal("300"))
        assert diff == Decimal("200")

    def test_d4_15_sum_completeness(self):
        """Validates: Requirements 2.2 — D4-15 维度合计。"""
        items = [
            {"delivery": {"amount": 100}},
            {"delivery": {"amount": 200}},
        ]
        total = d4_15_sum_completeness(items, "delivery")
        assert total == Decimal("300")

    def test_d4_16_ports_diff(self):
        """Validates: Requirements 2.2 — portsDiff = bookAmount - portsAmount。"""
        diff = d4_16_ports_diff(Decimal("10000"), Decimal("9500"))
        assert diff == Decimal("500")

    def test_d4_16_tax_diff(self):
        """Validates: Requirements 2.2 — taxDiff = bookAmount - taxReportAmount。"""
        diff = d4_16_tax_diff(Decimal("10000"), Decimal("10200"))
        assert diff == Decimal("-200")

    def test_d4_16_sum_diffs(self):
        """Validates: Requirements 2.2 — 差异合计 SUM。"""
        rows = [
            {"portsDiff": 100, "taxDiff": -50},
            {"portsDiff": 200, "taxDiff": 30},
        ]
        ports_total = d4_16_sum_diffs(rows, "portsDiff")
        tax_total = d4_16_sum_diffs(rows, "taxDiff")
        assert ports_total == Decimal("300")
        assert tax_total == Decimal("-20")


# ══════════════════════════════════════════════════════════════════════════════
# 3. 解析失败保留原值（Req 2.3 / 不转零）
# ══════════════════════════════════════════════════════════════════════════════

class TestParseFailurePreservesOriginal:
    """解析失败 → verdict outcome='failed', value=None, applied=False。"""

    def test_errors_produce_failed_verdict(self, preset_index):
        """Validates: Requirements 2.3 — 求值错误 → 失败裁决、不转零。"""
        result = resolve_and_execute(
            wp_id="test-wp",
            stable_sheet_key="workpaper:D4",
            row_key="D4-14-凭证金额合计",
            field_key="D4-14-凭证金额合计",
            computed_value=Decimal("0"),  # 底层可能转零
            errors=["依赖项 D4-1 未找到"],
            preset_index=preset_index,
        )
        assert result.verdict.outcome == "failed"
        assert result.verdict.value is None  # 不转零
        assert result.verdict.applied is False

    def test_corrupt_expression_blocked(self, preset_index):
        """Validates: Requirements 2.3 — 非法 custom expression → corrupt → failed。"""
        result = resolve_and_execute(
            wp_id="test-wp",
            stable_sheet_key="workpaper:D4",
            row_key="D4-14-凭证金额合计",
            field_key="D4-14-凭证金额合计",
            computed_value=Decimal("999"),
            custom_expression="eval('hack')",  # 非法
            preset_index=preset_index,
        )
        assert result.verdict.outcome == "failed"
        assert result.verdict.value is None
        assert "eval" in result.verdict.reason.lower() or "禁止" in result.verdict.reason

    def test_successful_execution_writes_value(self, preset_index):
        """Validates: Requirements 2.2 — 成功执行 → ok → 写值。"""
        result = resolve_and_execute(
            wp_id="test-wp",
            stable_sheet_key="workpaper:D4",
            row_key="D4-14-凭证金额合计",
            field_key="D4-14-凭证金额合计",
            computed_value=Decimal("350.5"),
            preset_index=preset_index,
        )
        assert result.verdict.outcome == "ok"
        assert result.verdict.value == Decimal("350.5")
        assert result.verdict.applied is True

    def test_none_value_with_no_errors_writes_none(self, preset_index):
        """Validates: Requirements 2.3 — computed_value=None 无错误也写 None。"""
        result = resolve_and_execute(
            wp_id="test-wp",
            stable_sheet_key="workpaper:D4",
            row_key="D4-14-凭证金额合计",
            field_key="D4-14-凭证金额合计",
            computed_value=None,
            preset_index=preset_index,
        )
        assert result.verdict.outcome == "ok"
        assert result.verdict.value is None


# ══════════════════════════════════════════════════════════════════════════════
# 4. 双模式 gate（Req 2.3）
# ══════════════════════════════════════════════════════════════════════════════

class TestDualModeGate:
    """双模式 gate 正确标记阻塞态。"""

    def test_gate_status_blocking(self):
        """Validates: Requirements 2.3 — 当前双模式 gate = blocking。"""
        gate = check_dual_mode_gate()
        assert gate["status"] == "blocking"

    def test_gate_has_reason(self):
        """Validates: Requirements 2.3 — gate 必须给出阻塞原因。"""
        gate = check_dual_mode_gate()
        assert gate["reason"]
        assert "d4:save-items" in gate["reason"]

    def test_result_includes_gate(self, preset_index):
        """Validates: Requirements 2.3 — 执行结果包含 dual_mode_gate。"""
        result = resolve_and_execute(
            wp_id="test-wp",
            stable_sheet_key="workpaper:D4",
            row_key="D4-14-凭证金额合计",
            field_key="D4-14-凭证金额合计",
            computed_value=Decimal("100"),
            preset_index=preset_index,
        )
        assert result.dual_mode_gate == "blocking"

    def test_result_to_dict(self, preset_index):
        """Validates: Requirements 2.3 — 序列化格式正确。"""
        result = resolve_and_execute(
            wp_id="test-wp",
            stable_sheet_key="workpaper:D4",
            row_key="D4-16-portsDiff",
            field_key="D4-16-portsDiff",
            computed_value=Decimal("500"),
            preset_index=preset_index,
        )
        d = result.to_dict()
        assert "verdict" in d
        assert "dualModeGate" in d
        assert d["dualModeGate"] == "blocking"
        assert d["verdict"]["outcome"] == "ok"


# ══════════════════════════════════════════════════════════════════════════════
# 5. 变异检验（Req 5.2）— 至少 2 处变异证 RED
# ══════════════════════════════════════════════════════════════════════════════

class TestMutationRed:
    """变异能打红对应守卫。"""

    def test_mutation_red_ports_diff_wrong_formula(self):
        """Validates: Requirements 5.2 — 变异: portsDiff 改为加法 → 结果错误。

        正确: bookAmount - portsAmount
        变异: bookAmount + portsAmount → 值不同 → 此测试 RED。
        """
        correct = d4_16_ports_diff(Decimal("10000"), Decimal("9500"))
        # 如果变异把减法改成加法，结果会是 19500，不等于 500
        assert correct == Decimal("500"), "正确公式 10000-9500=500"
        # 变异公式（模拟）：book + ports = 19500
        mutated = Decimal("10000") + Decimal("9500")
        assert correct != mutated, "变异公式结果与正确公式不同 → RED"

    def test_mutation_red_verdict_errors_should_not_write_value(self):
        """Validates: Requirements 5.2 — 变异: 如果 verdict 忽略 errors 仍写值 → 会被捕获。

        正确: errors 非空 → value=None, applied=False
        变异: 忽略 errors 直接写值 → applied=True → 此测试 RED。
        """
        eff = EffectiveFormula(
            key="test",
            state="preset",
            expression="SUM(WP('D4','test','amount'))",
            source="preset:d4_inspection_formula",
            formula_type="auto_calc",
            refs=[],
        )
        verdict = verdict_from_evaluation(
            eff,
            value=Decimal("0"),
            errors=["解析失败：引用未找到"],
        )
        # 正确行为：errors 非空 → failed → 不写值
        assert verdict.outcome == "failed"
        assert verdict.value is None
        assert verdict.applied is False
        # 如果变异把 errors 检查去掉，verdict 会是 ok/applied=True → 打红
