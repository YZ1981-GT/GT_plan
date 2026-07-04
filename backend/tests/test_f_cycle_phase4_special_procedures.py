"""F 类底稿 Phase 4 特殊程序验证（Tasks 32-41）。

验证:
  Task 32: F2-21~F2-26 存货监盘系列 f2-stocktake-bundle schema
  Task 33: F2-38~F2-44 计价测试 f2-inventory-valuation-impairment schema
  Task 34: F2-47~F2-49 跌价准备测试 f2-inventory-valuation-impairment schema
  Task 35: accounting_estimate_b51 auto_data_source resolver
  Task 36: F2-61~F2-72 适用性控制（applicable_when）
  Task 37: F2-16 会计政策检查 d-form-table schema
  Task 38: F2-52 关联交易检查 d-form-table schema + related_party_transactions
  Task 39: F2-55~F2-58 合同履约成本 f2-inventory-special schema
  Task 40: F1-4/F3-4/F4-4 调整分录/坏账 d-form-table schema
  Task 41: F 全系列底稿在前端正确打开（componentType 路由无 404）
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.wp_classification_service import (
    VALID_COMPONENT_TYPES,
    _WP_CODE_OVERRIDE,
)
from tests.f_cycle_f2_html_contract import (
    F2_MAIN,
    F2_SPE,
    F2_STOCKTAKE,
    F2_VAL,
    F1_PREPAYMENT,
    F3_NOTES,
    F4_PAYABLE,
    F5_COST,
    F_CYCLE_HTML_TYPES,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

_MAPPING_PATH = Path(__file__).resolve().parent.parent / "data" / "wp_account_mapping.json"


@pytest.fixture(scope="module")
def wp_mapping() -> list[dict]:
    """加载 wp_account_mapping.json 全量数据。"""
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mappings", data) if isinstance(data, dict) else data


@pytest.fixture(scope="module")
def f_class_entries(wp_mapping) -> list[dict]:
    """筛选 cycle == 'F' 的全部条目。"""
    return [e for e in wp_mapping if e.get("cycle") == "F"]


# ═══════════════════════════════════════════════════════════════════════════════
# Task 32: F2-21~F2-26 存货监盘系列 f2-stocktake-bundle schema 确认
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask32InventoryCountSchema:
    """验证 F2-21~F2-26 存货监盘系列正确映射为 f2-stocktake-bundle。"""

    _INVENTORY_COUNT_CODES = ["F2-21", "F2-22", "F2-23", "F2-24", "F2-25", "F2-26"]
    _INVENTORY_COUNT_NAMES = {
        "F2-21": "存货监盘计划",
        "F2-22": "盘点观察记录",
        "F2-23": "盘点抽盘测试",
        "F2-24": "存货截止测试",
        "F2-25": "盘点差异汇总",
        "F2-26": "监盘结论",
    }

    @pytest.mark.parametrize("wp_code", _INVENTORY_COUNT_CODES)
    def test_inventory_count_is_stocktake_bundle(self, wp_code):
        """F2-21~F2-26 监盘系列全部映射为 f2-stocktake-bundle。"""
        assert wp_code in _WP_CODE_OVERRIDE, (
            f"存货监盘 '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册"
        )
        assert _WP_CODE_OVERRIDE[wp_code] == F2_STOCKTAKE, (
            f"存货监盘 '{wp_code}' 应为 {F2_STOCKTAKE}，"
            f"实际为 {_WP_CODE_OVERRIDE[wp_code]}"
        )

    @pytest.mark.parametrize("wp_code", _INVENTORY_COUNT_CODES)
    def test_inventory_count_in_mapping(self, wp_code, f_class_entries):
        """F2-21~F2-26 在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in f_class_entries}
        assert wp_code in mapping_codes, (
            f"存货监盘 '{wp_code}' 未在 wp_account_mapping.json 注册"
        )

    def test_inventory_count_complete_series(self):
        """监盘系列包含完整6个底稿（计划/观察/抽盘/截止/差异/结论）。"""
        registered = [
            code for code in self._INVENTORY_COUNT_CODES
            if code in _WP_CODE_OVERRIDE
        ]
        assert len(registered) == 6, (
            f"监盘系列应有6个底稿，实际注册{len(registered)}个: {registered}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 33: F2-38~F2-44 计价测试 f2-inventory-valuation-impairment schema 确认
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask33ValuationTestSchema:
    """验证 F2-38~F2-44 计价测试正确映射为 f2-inventory-valuation-impairment。"""

    _VALUATION_TEST_CODES = [
        "F2-38", "F2-39", "F2-40", "F2-41", "F2-42", "F2-43", "F2-44",
    ]

    @pytest.mark.parametrize("wp_code", _VALUATION_TEST_CODES)
    def test_valuation_test_is_f2_val(self, wp_code):
        """F2-38~F2-44 计价测试全部映射为 f2-inventory-valuation-impairment。"""
        assert wp_code in _WP_CODE_OVERRIDE, (
            f"计价测试 '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册"
        )
        assert _WP_CODE_OVERRIDE[wp_code] == F2_VAL, (
            f"计价测试 '{wp_code}' 应为 {F2_VAL}，"
            f"实际为 {_WP_CODE_OVERRIDE[wp_code]}"
        )

    @pytest.mark.parametrize("wp_code", _VALUATION_TEST_CODES)
    def test_valuation_test_in_mapping(self, wp_code, f_class_entries):
        """F2-38~F2-44 在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in f_class_entries}
        assert wp_code in mapping_codes, (
            f"计价测试 '{wp_code}' 未在 wp_account_mapping.json 注册"
        )

    def test_valuation_test_complete_series(self):
        """计价测试系列包含完整7个底稿。"""
        registered = [
            code for code in self._VALUATION_TEST_CODES
            if code in _WP_CODE_OVERRIDE
        ]
        assert len(registered) == 7, (
            f"计价测试系列应有7个底稿，实际注册{len(registered)}个"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 34: F2-47~F2-49 跌价准备测试 f2-inventory-valuation-impairment schema 确认
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask34ImpairmentTestSchema:
    """验证 F2-47~F2-49 跌价准备测试正确映射为 f2-inventory-valuation-impairment。"""

    _IMPAIRMENT_TEST_CODES = ["F2-47", "F2-48", "F2-49"]

    @pytest.mark.parametrize("wp_code", _IMPAIRMENT_TEST_CODES)
    def test_impairment_test_is_f2_val(self, wp_code):
        """F2-47~F2-49 跌价准备测试全部映射为 f2-inventory-valuation-impairment。"""
        assert wp_code in _WP_CODE_OVERRIDE, (
            f"跌价准备测试 '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册"
        )
        assert _WP_CODE_OVERRIDE[wp_code] == F2_VAL, (
            f"跌价准备测试 '{wp_code}' 应为 {F2_VAL}，"
            f"实际为 {_WP_CODE_OVERRIDE[wp_code]}"
        )

    @pytest.mark.parametrize("wp_code", _IMPAIRMENT_TEST_CODES)
    def test_impairment_test_in_mapping(self, wp_code, f_class_entries):
        """F2-47~F2-49 在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in f_class_entries}
        assert wp_code in mapping_codes, (
            f"跌价准备测试 '{wp_code}' 未在 wp_account_mapping.json 注册"
        )

    def test_impairment_test_complete_series(self):
        """跌价准备测试系列包含完整3个底稿。"""
        registered = [
            code for code in self._IMPAIRMENT_TEST_CODES
            if code in _WP_CODE_OVERRIDE
        ]
        assert len(registered) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# Task 35: accounting_estimate_b51 auto_data_source resolver
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask35AccountingEstimateB51Resolver:
    """验证 accounting_estimate_b51 resolver 正确注册并返回预期结构。"""

    def test_resolver_registered(self):
        """accounting_estimate_b51 已注册到 auto_data_source 注册表。"""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "accounting_estimate_b51" in sources, (
            "accounting_estimate_b51 未在 auto_data_resolvers 中注册"
        )

    @pytest.mark.asyncio
    async def test_resolver_returns_correct_structure_when_no_data(self):
        """无数据时返回正确的降级结构（summary + 三因素 None）。"""
        from unittest.mock import AsyncMock, MagicMock, patch
        from uuid import uuid4

        from app.services.auto_data_resolvers import resolve_auto_data_source

        # Mock FieldOverrideService.get_batch 返回空
        mock_db = MagicMock()
        with patch(
            "app.services.field_override_service.FieldOverrideService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.get_batch = AsyncMock(return_value={})

            result = await resolve_auto_data_source(
                mock_db, uuid4(), 2025, source="accounting_estimate_b51"
            )

        assert result is not None
        assert "summary" in result
        assert "fraud_incentive" in result
        assert "fraud_opportunity" in result
        assert "fraud_attitude" in result
        assert "overall_risk_level" in result
        # 无数据时为降级摘要
        assert "尚未完成" in result["summary"]
        assert result["fraud_incentive"] is None
        assert result["overall_risk_level"] is None

    @pytest.mark.asyncio
    async def test_resolver_returns_data_when_available(self):
        """有数据时返回三因素评估结果。"""
        from unittest.mock import AsyncMock, MagicMock, patch
        from uuid import uuid4

        from app.services.auto_data_resolvers import resolve_auto_data_source

        mock_db = MagicMock()
        mock_data = {
            "fraud_assessment": {
                "incentive": "存在业绩压力",
                "opportunity": "内部控制薄弱",
                "attitude": "管理层激进",
                "overall_risk_level": "high",
            }
        }
        with patch(
            "app.services.field_override_service.FieldOverrideService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.get_batch = AsyncMock(return_value=mock_data)

            result = await resolve_auto_data_source(
                mock_db, uuid4(), 2025, source="accounting_estimate_b51"
            )

        assert result is not None
        assert result["fraud_incentive"] == "存在业绩压力"
        assert result["fraud_opportunity"] == "内部控制薄弱"
        assert result["fraud_attitude"] == "管理层激进"
        assert result["overall_risk_level"] == "high"
        assert "高" in result["summary"]


# ═══════════════════════════════════════════════════════════════════════════════
# Task 36: F2-61~F2-72 IPO 适用性控制
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask36IPOApplicableWhen:
    """验证 F2-61~F2-72 IPO 底稿设置了 applicable_when 适用性控制。"""

    _IPO_CODES = [f"F2-{i}" for i in range(61, 73)]

    @pytest.mark.parametrize("wp_code", [f"F2-{i}" for i in range(61, 73)])
    def test_ipo_code_is_f2_special(self, wp_code):
        """F2-61~F2-72 全部映射为 f2-inventory-special。"""
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == F2_SPE

    def test_ipo_applicable_when_in_mapping(self, f_class_entries):
        """F2-61~F2-72 在 wp_account_mapping.json 中设置了 applicable_when。"""
        ipo_entries = [
            e for e in f_class_entries
            if e["wp_code"] in self._IPO_CODES
        ]
        assert len(ipo_entries) == 12, (
            f"应有12个 IPO 底稿条目，实际{len(ipo_entries)}个"
        )
        for entry in ipo_entries:
            assert "applicable_when" in entry, (
                f"{entry['wp_code']} 缺少 applicable_when 字段"
            )
            aw = entry["applicable_when"]
            assert "business_category" in aw, (
                f"{entry['wp_code']} applicable_when 缺少 business_category"
            )
            categories = aw["business_category"]
            assert "ipo" in categories, f"{entry['wp_code']} 缺少 'ipo'"
            assert "listed" in categories, f"{entry['wp_code']} 缺少 'listed'"
            assert "neeq" in categories, f"{entry['wp_code']} 缺少 'neeq'"
            assert "restructuring" in categories, (
                f"{entry['wp_code']} 缺少 'restructuring'"
            )

    def test_ipo_not_applicable_for_annual_audit(self, f_class_entries):
        """普通年审项目（无特殊 business_category）不适用 F2-61~F2-72。"""
        ipo_entries = [
            e for e in f_class_entries
            if e["wp_code"] in self._IPO_CODES
        ]
        # 模拟普通年审项目 business_category = "annual"
        project_category = "annual"
        for entry in ipo_entries:
            aw = entry.get("applicable_when", {})
            categories = aw.get("business_category", [])
            assert project_category not in categories, (
                f"{entry['wp_code']} 不应对 'annual' 适用"
            )

    def test_ipo_consistent_with_d4_22_pattern(self, wp_mapping):
        """F2-61~F2-72 的 applicable_when 与 D4-22 使用相同模式。"""
        d4_22 = next(
            (e for e in wp_mapping if e.get("wp_code") == "D4-22"), None
        )
        if d4_22 is None:
            pytest.skip("D4-22 未在 wp_account_mapping 中注册")

        d4_categories = set(d4_22["applicable_when"]["business_category"])

        f_ipo_entries = [
            e for e in wp_mapping
            if e.get("wp_code", "").startswith("F2-6")
            and int(e.get("wp_code", "F2-0").split("-")[1]) >= 61
            and e.get("cycle") == "F"
        ]
        for entry in f_ipo_entries:
            if "applicable_when" in entry:
                f_categories = set(entry["applicable_when"]["business_category"])
                assert f_categories == d4_categories, (
                    f"{entry['wp_code']} applicable_when 应与 D4-22 一致"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 37: F2-16 会计政策检查 d-form-table schema 确认
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask37AccountingPolicyCheck:
    """验证 F2-16 会计政策检查正确映射为 f2-inventory-main。"""

    def test_f2_16_is_f2_main(self):
        """F2-16 会计政策检查映射为 f2-inventory-main。"""
        assert "F2-16" in _WP_CODE_OVERRIDE, (
            "F2-16 会计政策检查未在 _WP_CODE_OVERRIDE 中注册"
        )
        assert _WP_CODE_OVERRIDE["F2-16"] == F2_MAIN, (
            f"F2-16 应为 {F2_MAIN}，实际为 {_WP_CODE_OVERRIDE['F2-16']}"
        )

    def test_f2_16_in_mapping(self, f_class_entries):
        """F2-16 在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in f_class_entries}
        assert "F2-16" in mapping_codes, (
            "F2-16 未在 wp_account_mapping.json 中注册"
        )

    def test_f2_16_has_correct_name(self, f_class_entries):
        """F2-16 的名称包含'会计政策'关键词。"""
        entry = next(
            (e for e in f_class_entries if e["wp_code"] == "F2-16"), None
        )
        assert entry is not None
        assert "会计政策" in entry["wp_name"], (
            f"F2-16 名称应包含'会计政策'，实际为 '{entry['wp_name']}'"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 38: F2-52 关联交易检查 d-form-table schema + related_party_transactions
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask38RelatedPartyCheck:
    """验证 F2-52 关联交易检查映射为 f2-inventory-valuation-impairment。"""

    def test_f2_52_is_f2_val(self):
        """F2-52 关联交易检查映射为 f2-inventory-valuation-impairment。"""
        assert "F2-52" in _WP_CODE_OVERRIDE, (
            "F2-52 关联交易检查未在 _WP_CODE_OVERRIDE 中注册"
        )
        assert _WP_CODE_OVERRIDE["F2-52"] == F2_VAL, (
            f"F2-52 应为 {F2_VAL}，实际为 {_WP_CODE_OVERRIDE['F2-52']}"
        )

    def test_f2_52_in_mapping(self, f_class_entries):
        """F2-52 在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in f_class_entries}
        assert "F2-52" in mapping_codes

    def test_f2_52_has_correct_name(self, f_class_entries):
        """F2-52 的名称包含'关联交易'关键词。"""
        entry = next(
            (e for e in f_class_entries if e["wp_code"] == "F2-52"), None
        )
        assert entry is not None
        assert "关联交易" in entry["wp_name"], (
            f"F2-52 名称应包含'关联交易'，实际为 '{entry['wp_name']}'"
        )

    def test_related_party_transactions_resolver_exists(self):
        """related_party_transactions resolver 已注册（F2-52 使用）。"""
        from app.services.auto_data_resolvers import get_registered_sources
        sources = get_registered_sources()
        assert "related_party_transaction_count" in sources, (
            "related_party_transaction_count resolver 未注册"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 39: F2-55~F2-58 合同履约成本 f2-inventory-special schema 确认
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask39ContractPerformanceCost:
    """验证 F2-55~F2-58 合同履约成本正确映射为 f2-inventory-special。"""

    _CONTRACT_COST_CODES = ["F2-55", "F2-56", "F2-57", "F2-58"]

    @pytest.mark.parametrize("wp_code", ["F2-55", "F2-56", "F2-57", "F2-58"])
    def test_contract_cost_is_f2_special(self, wp_code):
        """F2-55~F2-58 合同履约成本全部映射为 f2-inventory-special。"""
        assert wp_code in _WP_CODE_OVERRIDE, (
            f"合同履约成本 '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册"
        )
        assert _WP_CODE_OVERRIDE[wp_code] == F2_SPE, (
            f"合同履约成本 '{wp_code}' 应为 {F2_SPE}，"
            f"实际为 {_WP_CODE_OVERRIDE[wp_code]}"
        )

    @pytest.mark.parametrize("wp_code", ["F2-55", "F2-56", "F2-57", "F2-58"])
    def test_contract_cost_in_mapping(self, wp_code, f_class_entries):
        """F2-55~F2-58 在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in f_class_entries}
        assert wp_code in mapping_codes

    def test_contract_cost_complete_series(self):
        """合同履约成本系列包含完整4个底稿。"""
        registered = [
            code for code in self._CONTRACT_COST_CODES
            if code in _WP_CODE_OVERRIDE
        ]
        assert len(registered) == 4


# ═══════════════════════════════════════════════════════════════════════════════
# Task 40: F1-4/F3-4/F4-4 调整分录/坏账 d-form-table schema 确认
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask40AdjustmentEntriesSchema:
    """验证 F1-4/F3-4/F4-4 调整分录/坏账映射为各 cycle HTML 入口。"""

    _ADJUSTMENT_CODES = {
        "F1-4": F1_PREPAYMENT,
        "F3-4": F3_NOTES,
        "F4-4": F4_PAYABLE,
    }

    @pytest.mark.parametrize("wp_code,expected", list(_ADJUSTMENT_CODES.items()))
    def test_adjustment_is_cycle_html(self, wp_code, expected):
        """F1-4/F3-4/F4-4 调整分录/坏账映射为 cycle HTML componentType。"""
        assert wp_code in _WP_CODE_OVERRIDE, (
            f"调整分录 '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册"
        )
        assert _WP_CODE_OVERRIDE[wp_code] == expected, (
            f"调整分录 '{wp_code}' 应为 {expected}，"
            f"实际为 {_WP_CODE_OVERRIDE[wp_code]}"
        )

    @pytest.mark.parametrize("wp_code", ["F1-4", "F3-4", "F4-4"])
    def test_adjustment_in_mapping(self, wp_code, f_class_entries):
        """F1-4/F3-4/F4-4 在 wp_account_mapping.json 中注册。"""
        mapping_codes = {e["wp_code"] for e in f_class_entries}
        assert wp_code in mapping_codes

    def test_f1_4_is_bad_debt(self, f_class_entries):
        """F1-4 名称包含'坏账'关键词。"""
        entry = next(
            (e for e in f_class_entries if e["wp_code"] == "F1-4"), None
        )
        assert entry is not None
        assert "坏账" in entry["wp_name"], (
            f"F1-4 名称应包含'坏账'，实际为 '{entry['wp_name']}'"
        )

    def test_f3_4_is_adjustment(self, f_class_entries):
        """F3-4 名称包含'调整分录'关键词。"""
        entry = next(
            (e for e in f_class_entries if e["wp_code"] == "F3-4"), None
        )
        assert entry is not None
        assert "调整分录" in entry["wp_name"], (
            f"F3-4 名称应包含'调整分录'，实际为 '{entry['wp_name']}'"
        )

    def test_f4_4_is_adjustment(self, f_class_entries):
        """F4-4 名称包含'调整分录'关键词。"""
        entry = next(
            (e for e in f_class_entries if e["wp_code"] == "F4-4"), None
        )
        assert entry is not None
        assert "调整分录" in entry["wp_name"], (
            f"F4-4 名称应包含'调整分录'，实际为 '{entry['wp_name']}'"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 41: F 全系列底稿 componentType 路由无 404
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask41FullSeriesRouting:
    """验证 F 全系列底稿在前端正确打开（componentType 路由无 404）。"""

    # 前端路由支持的合法 componentType 集合（所有能在前端路由到组件的类型）
    _FRONTEND_ROUTABLE_TYPES = {
        "a-program-console",
        "d-form-table",
        "d-form-paragraph",
        "d-form-qa",
        "d-form-confirmation",
        "d-form-review",
        "audit-sheet",
        "c-note-table",
        "confirmation-hub",
        "b-index",
        "e-control-test",
        "h-static-doc",
        "custom",
        "bad-debt-sheet",
        "misstatement-summary",
        "review-checklist",
        "word-template",
        "independence-signing",
        "audit-legend",
        "univer",
        "checklist-table",
        "analytical-review",
        "misstatement-workpaper",
        "a14-3-workbook",
        "a17-summary",
        "kam-workpaper",
        "regulatory-letter",
        "a11-bundle",
        "a15-bundle",
        "redirect-materiality",
        "a1-dashboard",
        "a2-adjustment-console",
        "a3-consolidation-console",
        "cf-verification",
        "skip",
        "f2-inventory-main",
        "f2-inventory-valuation-impairment",
        "f2-inventory-special",
        "f2-stocktake-bundle",
        "f1-prepayment",
        "f3-notes-payable",
        "f4-accounts-payable",
        "f5-cost-of-sales",
        "confirmation-summary",
        "confirmation-entity-verify",
        "confirmation-followup",
        "confirmation-diff-reconcile",
        "confirmation-diff-checklist",
        "confirmation-alternative-f05",
        "confirmation-alternative-f06",
        "confirmation-reliability",
        "confirmation-fraud-risk",
    }

    def test_all_f_codes_in_override(self, f_class_entries):
        """所有 F 类 wp_code 在 _WP_CODE_OVERRIDE 中都有映射。"""
        for entry in f_class_entries:
            wp_code = entry["wp_code"]
            assert wp_code in _WP_CODE_OVERRIDE, (
                f"F 类 wp_code '{wp_code}' 未在 _WP_CODE_OVERRIDE 中注册，"
                f"前端将 404"
            )

    def test_all_f_component_types_valid(self, f_class_entries):
        """所有 F 类 componentType 是合法的前端可路由类型。"""
        for entry in f_class_entries:
            wp_code = entry["wp_code"]
            ct = _WP_CODE_OVERRIDE.get(wp_code, "")
            assert ct in self._FRONTEND_ROUTABLE_TYPES, (
                f"F 类 wp_code '{wp_code}' 的 componentType '{ct}' "
                f"不在前端可路由类型集合中，将 404"
            )

    def test_all_f_component_types_in_whitelist(self, f_class_entries):
        """所有 F 类 componentType 在 VALID_COMPONENT_TYPES 白名单内。"""
        for entry in f_class_entries:
            wp_code = entry["wp_code"]
            ct = _WP_CODE_OVERRIDE.get(wp_code, "")
            assert ct in VALID_COMPONENT_TYPES, (
                f"F 类 wp_code '{wp_code}' 的 componentType '{ct}' "
                f"不在 VALID_COMPONENT_TYPES 白名单内"
            )

    def test_f_class_override_covers_mapping(self, f_class_entries):
        """wp_account_mapping 中每个 F 类 wp_code 均在 _WP_CODE_OVERRIDE 注册。"""
        mapping_codes = {e["wp_code"] for e in f_class_entries}
        missing = mapping_codes - set(_WP_CODE_OVERRIDE.keys())
        assert not missing, f"F 类 mapping 未在 override 注册: {sorted(missing)}"

    def test_f_class_expected_type_distribution(self):
        """F 类 componentType 分布合理。"""
        f_codes = {
            code: ct for code, ct in _WP_CODE_OVERRIDE.items()
            if code.startswith("F")
        }
        type_counts: dict[str, int] = {}
        for ct in f_codes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1

        # 基本分布检查
        assert type_counts.get("confirmation-hub", 0) == 1, (
            "应有 1 个 confirmation-hub (F0)"
        )
        assert type_counts.get(F2_MAIN, 0) >= 20, (
            f"应有至少 20 个 {F2_MAIN}，实际 {type_counts.get(F2_MAIN, 0)}"
        )
        assert type_counts.get(F1_PREPAYMENT, 0) >= 7, (
            f"应有至少 7 个 {F1_PREPAYMENT}"
        )
        assert type_counts.get(F3_NOTES, 0) >= 7, (
            f"应有至少 7 个 {F3_NOTES}"
        )
        assert type_counts.get("audit-sheet", 0) == 0, (
            "F 类不应再使用 audit-sheet"
        )
        assert type_counts.get("d-form-table", 0) == 0, (
            "F 类不应再使用 d-form-table"
        )

    def test_f0_is_confirmation_hub(self):
        """F0 函证底稿映射为 confirmation-hub。"""
        assert _WP_CODE_OVERRIDE.get("F0") == "confirmation-hub"

    def test_f_program_tables_use_cycle_html_or_a_program(self):
        """F{n}A 程序表映射为 a-program-console 或 cycle HTML bundle。"""
        cycle_html_program = {
            "F2A": F2_MAIN,
            "F3A": F3_NOTES,
            "F1A": F1_PREPAYMENT,
            "F4A": F4_PAYABLE,
            "F5A": F5_COST,
        }
        for code in ["F0A", "F1A", "F2A", "F3A", "F4A", "F5A"]:
            if code not in _WP_CODE_OVERRIDE:
                continue
            expected = cycle_html_program.get(code, "a-program-console")
            assert _WP_CODE_OVERRIDE[code] == expected, (
                f"程序表 {code} 应映射为 {expected}，实际 {_WP_CODE_OVERRIDE[code]}"
            )

    def test_f_audit_determination_tables(self):
        """F{n}-1 审定表映射为各 cycle HTML 入口。"""
        expected_map = {
            "F1-1": F1_PREPAYMENT,
            "F2-1": F2_MAIN,
            "F3-1": F3_NOTES,
            "F4-1": F4_PAYABLE,
            "F5-1": F5_COST,
        }
        for code, expected in expected_map.items():
            assert code in _WP_CODE_OVERRIDE, f"审定表 {code} 未注册"
            assert _WP_CODE_OVERRIDE[code] == expected, (
                f"审定表 {code} 应为 {expected}，实际 {_WP_CODE_OVERRIDE[code]}"
            )

    def test_f2_html_migrated_codes_match_override(self):
        """F2 HTML 化 wp_code 与 _WP_CODE_OVERRIDE 一致。"""
        for wp_code, expected in (
            ("F2-1", F2_MAIN),
            ("F2-47", F2_VAL),
            ("F2-55", F2_SPE),
            ("F2-21", F2_STOCKTAKE),
        ):
            assert _WP_CODE_OVERRIDE.get(wp_code) == expected

    def test_no_f_code_maps_to_skip(self):
        """F 类底稿不应有 'skip' componentType（所有 F 底稿都应渲染）。"""
        for code, ct in _WP_CODE_OVERRIDE.items():
            if code.startswith("F"):
                assert ct != "skip", (
                    f"F 类 wp_code '{code}' 不应为 'skip'，F 类底稿都需要渲染"
                )

    def test_all_expected_f_codes_present(self, f_class_entries):
        """验证 F 类全部 93 个预期 wp_code 都已注册。"""
        expected_codes = {
            # F0 函证
            "F0", "F0-1", "F0-2", "F0-3", "F0-4", "F0-5",
            # F1 预付账款
            "F1", "F1-1", "F1-2", "F1-3", "F1-4", "F1-5", "F1-6",
            # F2 存货
            "F2", "F2-1", "F2-2", "F2-3", "F2-4", "F2-5", "F2-6",
            "F2-7", "F2-8", "F2-9", "F2-10", "F2-11", "F2-12",
            "F2-13", "F2-14", "F2-16",
            "F2-18", "F2-19", "F2-20",
            "F2-21", "F2-22", "F2-23", "F2-24", "F2-25", "F2-26",
            "F2-29", "F2-30", "F2-31", "F2-32", "F2-33", "F2-34", "F2-35",
            "F2-38", "F2-39", "F2-40", "F2-41", "F2-42", "F2-43", "F2-44",
            "F2-47", "F2-48", "F2-49",
            "F2-52",
            "F2-55", "F2-56", "F2-57", "F2-58",
            "F2-61", "F2-62", "F2-63", "F2-64", "F2-65", "F2-66",
            "F2-67", "F2-68", "F2-69", "F2-70", "F2-71", "F2-72",
            # F3 应付票据
            "F3", "F3-1", "F3-2", "F3-3", "F3-4", "F3-5", "F3-6",
            # F4 应付账款
            "F4", "F4-1", "F4-2", "F4-3", "F4-4", "F4-5", "F4-6",
            # F5 营业成本
            "F5", "F5-1", "F5-2", "F5-3", "F5-4", "F5-5", "F5-6",
        }
        mapping_codes = {e["wp_code"] for e in f_class_entries}
        missing = expected_codes - mapping_codes
        assert not missing, f"F 类缺少 wp_code: {sorted(missing)}"
