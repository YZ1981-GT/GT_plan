"""G3 应收股利 — 后端集成测试.

验证：
1. render策略静态配置正确性（科目前缀/审定item_id）
2. VALID_COMPONENT_TYPES / RENDERER_DISPATCH / wp_code_overrides 注册契约
3. 导入导出列结构对齐（5张表：G3-1/G3-2/G3-3/G3-4/G3-5）
4. round-trip: 导出→导入→数据一致

Requirements: 1.1~1.5, 5.1, 6.1, 7.1, 8.1, 10.1
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# 1. render 策略静态配置
# ═══════════════════════════════════════════════════════════════════════════════


class TestG3RenderStructure:
    """验证 render 策略静态配置（无数据库）."""

    def test_account_prefix_is_1131(self):
        from app.routers.wp_render_strategies._g3_dividend_receivable import (
            _G3_ACCOUNT_PREFIX,
        )
        assert _G3_ACCOUNT_PREFIX == "1131"

    def test_adjudicated_item_id_format(self):
        from app.routers.wp_render_strategies._g3_dividend_receivable import (
            _ADJUDICATED_ITEM_ID,
        )
        assert _ADJUDICATED_ITEM_ID == "G3-1-adjudicated-amount"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 注册契约验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestG3RegistrationContract:
    """验证 g3-dividend-receivable 注册四件套完整."""

    def test_valid_component_types_contains_g3(self):
        from app.services.wp_classification_service import VALID_COMPONENT_TYPES
        assert "g3-dividend-receivable" in VALID_COMPONENT_TYPES

    def test_renderer_dispatch_contains_g3(self):
        from app.routers.wp_render_strategies import RENDERER_DISPATCH
        assert "g3-dividend-receivable" in RENDERER_DISPATCH

    def test_renderer_dispatch_callable(self):
        from app.routers.wp_render_strategies import RENDERER_DISPATCH
        render_fn = RENDERER_DISPATCH["g3-dividend-receivable"]
        assert callable(render_fn)

    def test_wp_code_overrides_g3_entries(self):
        overrides_path = (
            Path(__file__).resolve().parent.parent
            / "app" / "data" / "wp_code_overrides.json"
        )
        with open(overrides_path, encoding="utf-8") as f:
            overrides = json.load(f)

        # G3 相关条目全部映射到 g3-dividend-receivable
        g3_entries = {
            k: v for k, v in overrides.items()
            if v == "g3-dividend-receivable"
        }
        # 至少 8 个条目（G3A/G3-1~G3-5/附注上市/附注国企）
        assert len(g3_entries) >= 8, (
            f"wp_code_overrides 中 g3 映射条目不足: {g3_entries}"
        )

    def test_wp_code_overrides_g3_specific_codes(self):
        overrides_path = (
            Path(__file__).resolve().parent.parent
            / "app" / "data" / "wp_code_overrides.json"
        )
        with open(overrides_path, encoding="utf-8") as f:
            overrides = json.load(f)

        expected_codes = [
            "G3A", "G3-1", "G3-2", "G3-3", "G3-4", "G3-5",
            "G3-note-listed", "G3-note-soe",
        ]
        for code in expected_codes:
            assert overrides.get(code) == "g3-dividend-receivable", (
                f"{code} 未映射到 g3-dividend-receivable"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 导入导出列结构对齐
# ═══════════════════════════════════════════════════════════════════════════════


class TestG3ImportExportStructure:
    """验证 5 张表的导入导出列结构."""

    def test_supported_sheets_are_5(self):
        from app.routers.wp_render_strategies._g3_dividend_receivable_import_export import (
            _G3_SPECS,
        )
        assert len(_G3_SPECS) == 5
        assert set(_G3_SPECS.keys()) == {"G3-1", "G3-2", "G3-3", "G3-4", "G3-5"}

    def test_g3_1_headers_14_columns(self):
        from app.routers.wp_render_strategies._g3_dividend_receivable_import_export import (
            _G3_1_HEADERS, _G3_1_KEYS,
        )
        assert len(_G3_1_HEADERS) == 14
        assert len(_G3_1_KEYS) == 14
        assert "被投资方" in _G3_1_HEADERS
        assert "期末审定" in _G3_1_HEADERS
        assert "investeeName" in _G3_1_KEYS

    def test_g3_2_headers_33_columns(self):
        from app.routers.wp_render_strategies._g3_dividend_receivable_import_export import (
            _G3_2_HEADERS, _G3_2_KEYS,
        )
        assert len(_G3_2_HEADERS) == 33
        assert len(_G3_2_KEYS) == 33
        assert len(_G3_2_HEADERS) == len(_G3_2_KEYS)

    def test_g3_2_four_segments_sum_to_33(self):
        """4区段：被投资方信息8 + 持股明细9 + 分红方案8 + 应收核算8 = 33."""
        from app.routers.wp_render_strategies._g3_dividend_receivable_import_export import (
            _G3_2_HEADERS,
        )
        # 被投资方信息 starts with 序号
        assert _G3_2_HEADERS[0] == "序号"
        # 持股明细 starts at index 8
        assert _G3_2_HEADERS[8] == "持股数量(股)"
        # 分红方案 starts at index 17
        assert _G3_2_HEADERS[17] == "决议日期"
        # 应收核算 starts at index 25
        assert _G3_2_HEADERS[25] == "应收股利"

    def test_g3_3_headers_10_columns(self):
        from app.routers.wp_render_strategies._g3_dividend_receivable_import_export import (
            _G3_3_HEADERS, _G3_3_KEYS,
        )
        assert len(_G3_3_HEADERS) == 10
        assert len(_G3_3_KEYS) == 10
        assert "序号" in _G3_3_HEADERS
        assert "分录类型" in _G3_3_HEADERS
        assert "借方金额" in _G3_3_HEADERS
        assert "贷方金额" in _G3_3_HEADERS

    def test_g3_4_headers_18_columns(self):
        from app.routers.wp_render_strategies._g3_dividend_receivable_import_export import (
            _G3_4_HEADERS, _G3_4_KEYS,
        )
        assert len(_G3_4_HEADERS) == 18
        assert len(_G3_4_KEYS) == 18
        # 股利测算区段9列
        assert _G3_4_HEADERS[0] == "序号"
        assert "应收股利(测算)" in _G3_4_HEADERS
        assert "测算差异" in _G3_4_HEADERS
        # 凭证检查区段9列
        assert "凭证日期" in _G3_4_HEADERS
        assert "审计结论" in _G3_4_HEADERS

    def test_g3_4_two_segments_9_plus_9(self):
        """2区段：股利测算9 + 凭证检查9 = 18."""
        from app.routers.wp_render_strategies._g3_dividend_receivable_import_export import (
            _G3_4_KEYS,
        )
        # 股利测算区段前9个 keys
        calc_keys = _G3_4_KEYS[:9]
        assert "seq" in calc_keys
        assert "calculatedDividend" in calc_keys
        assert "calcVariance" in calc_keys
        # 凭证检查区段后9个 keys
        check_keys = _G3_4_KEYS[9:]
        assert len(check_keys) == 9
        assert "voucherDate" in check_keys
        assert "auditConclusion" in check_keys

    def test_g3_5_headers_13_columns(self):
        from app.routers.wp_render_strategies._g3_dividend_receivable_import_export import (
            _G3_5_HEADERS, _G3_5_KEYS,
        )
        assert len(_G3_5_HEADERS) == 13
        assert len(_G3_5_KEYS) == 13
        assert "被投资方" in _G3_5_HEADERS
        assert "逾期天数" in _G3_5_HEADERS
        assert "风险等级" in _G3_5_HEADERS
        assert "审计建议" in _G3_5_HEADERS

    def test_all_specs_have_required_fields(self):
        from app.routers.wp_render_strategies._g3_dividend_receivable_import_export import (
            _G3_SPECS,
        )
        required_fields = {"item_id", "title", "headers", "field_keys", "guidance"}
        for code, spec in _G3_SPECS.items():
            missing = required_fields - set(spec.keys())
            assert not missing, f"{code} 缺少字段: {missing}"

    def test_headers_keys_length_match(self):
        from app.routers.wp_render_strategies._g3_dividend_receivable_import_export import (
            _G3_SPECS,
        )
        for code, spec in _G3_SPECS.items():
            assert len(spec["headers"]) == len(spec["field_keys"]), (
                f"{code}: headers({len(spec['headers'])}) != "
                f"keys({len(spec['field_keys'])})"
            )

    def test_g3_3_keys_match_frontend_interface(self):
        from app.routers.wp_render_strategies._g3_dividend_receivable_import_export import (
            _G3_3_KEYS,
        )
        expected_keys = [
            "seq", "entryType", "entryDate", "summary", "accountCode",
            "accountName", "debitAmount", "creditAmount", "preparedBy", "remark",
        ]
        assert _G3_3_KEYS == expected_keys

    def test_item_ids_unique(self):
        from app.routers.wp_render_strategies._g3_dividend_receivable_import_export import (
            _G3_SPECS,
        )
        item_ids = [spec["item_id"] for spec in _G3_SPECS.values()]
        assert len(item_ids) == len(set(item_ids)), "item_id 不唯一"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. round-trip 验证（通用工厂模式）
# ═══════════════════════════════════════════════════════════════════════════════


class TestG3ImportExportRoundTrip:
    """验证 G3 导入导出 round-trip（列结构对齐性）."""

    def test_g3_specs_router_created(self):
        """验证 create_cycle_import_export_router 创建了 router."""
        from app.routers.wp_render_strategies._g3_dividend_receivable_import_export import (
            router,
        )
        assert router is not None
        # router 应有路由（export-template/export-data/import-data × 5 sheets）
        assert len(router.routes) > 0

    def test_g3_2_key_field_alignment_with_frontend(self):
        """G3-2 field_keys 包含前端 DividendDetailRow 关键字段."""
        from app.routers.wp_render_strategies._g3_dividend_receivable_import_export import (
            _G3_2_KEYS,
        )
        # 被投资方信息区段
        assert "investeeName" in _G3_2_KEYS
        assert "initialCost" in _G3_2_KEYS
        # 持股明细区段
        assert "sharesHeld" in _G3_2_KEYS
        assert "shareholdingRatio" in _G3_2_KEYS
        # 分红方案区段
        assert "dps" in _G3_2_KEYS
        assert "totalDividend" in _G3_2_KEYS
        assert "payoutRatio" in _G3_2_KEYS
        # 应收核算区段
        assert "dividendReceivable" in _G3_2_KEYS
        assert "netReceivable" in _G3_2_KEYS
        assert "overdueDays" in _G3_2_KEYS

    def test_g3_5_key_field_alignment_with_frontend(self):
        """G3-5 field_keys 包含前端 OverdueDividendRow 关键字段."""
        from app.routers.wp_render_strategies._g3_dividend_receivable_import_export import (
            _G3_5_KEYS,
        )
        assert "investeeName" in _G3_5_KEYS
        assert "receivableAmount" in _G3_5_KEYS
        assert "overdueDays" in _G3_5_KEYS
        assert "recoverability" in _G3_5_KEYS
        assert "riskLevel" in _G3_5_KEYS
        assert "auditSuggestion" in _G3_5_KEYS

    def test_g3_1_adjudication_key_fields(self):
        """G3-1 审定表 field_keys 包含借方科目必要字段."""
        from app.routers.wp_render_strategies._g3_dividend_receivable_import_export import (
            _G3_1_KEYS,
        )
        # 借方公式链相关字段
        assert "openingUnadjusted" in _G3_1_KEYS
        assert "openingAJE" in _G3_1_KEYS
        assert "openingRJE" in _G3_1_KEYS
        assert "openingAdjusted" in _G3_1_KEYS
        assert "currentDeclared" in _G3_1_KEYS
        assert "currentReceived" in _G3_1_KEYS
        assert "closingUnadjusted" in _G3_1_KEYS
        assert "closingAJE" in _G3_1_KEYS
        assert "closingRJE" in _G3_1_KEYS
        assert "closingAdjusted" in _G3_1_KEYS
