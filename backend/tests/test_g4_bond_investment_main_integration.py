"""G4 债权投资(main组) — 后端集成测试.

验证：
1. render_g4_bond_investment_main 返回正确结构（8 sheets配置 + TB取数 + 审定回读）
2. VALID_COMPONENT_TYPES / RENDERER_DISPATCH / wp_code_overrides 注册契约
3. 导入导出 round-trip（导出模板结构 → 数据字段对齐 → 导入解析正确）

Requirements: 1.1~1.5, 10.1~10.3
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

# ═══════════════════════════════════════════════════════════════════════════════
# 1. render 策略返回正确结构
# ═══════════════════════════════════════════════════════════════════════════════


class TestG4MainRenderStructure:
    """验证 render 策略返回结构（无数据库，验证静态配置）."""

    def test_g4_main_sheets_has_8_entries(self):
        from app.routers.wp_render_strategies._g4_bond_investment_main import G4_MAIN_SHEETS

        assert len(G4_MAIN_SHEETS) == 8

    def test_g4_main_sheets_codes_complete(self):
        from app.routers.wp_render_strategies._g4_bond_investment_main import G4_MAIN_SHEETS

        codes = [s["code"] for s in G4_MAIN_SHEETS]
        expected_codes = [
            "G4A", "G4-1", "G4-2", "G4-3", "G4-4",
            "附注披露信息（上市公司）", "附注披露信息（国企）", "底稿目录",
        ]
        assert sorted(codes) == sorted(expected_codes)

    def test_g4_main_sheets_all_have_required_keys(self):
        from app.routers.wp_render_strategies._g4_bond_investment_main import G4_MAIN_SHEETS

        required_keys = {"code", "sheetName", "componentType", "group", "columns", "rows"}
        for sheet in G4_MAIN_SHEETS:
            missing = required_keys - set(sheet.keys())
            assert not missing, f"Sheet {sheet.get('code')} 缺少字段: {missing}"

    def test_g4a_uses_a_program_console(self):
        from app.routers.wp_render_strategies._g4_bond_investment_main import G4_MAIN_SHEETS

        g4a = next(s for s in G4_MAIN_SHEETS if s["code"] == "G4A")
        assert g4a["componentType"] == "a-program-console"

    def test_other_sheets_use_main_component_type(self):
        from app.routers.wp_render_strategies._g4_bond_investment_main import G4_MAIN_SHEETS

        for sheet in G4_MAIN_SHEETS:
            if sheet["code"] != "G4A":
                assert sheet["componentType"] == "g4-bond-investment-main"

    def test_g4_main_sheets_group_assignment(self):
        from app.routers.wp_render_strategies._g4_bond_investment_main import G4_MAIN_SHEETS

        core_codes = {"G4A", "G4-1", "G4-2", "G4-3", "附注披露信息（上市公司）", "附注披露信息（国企）", "底稿目录"}
        measurement_codes = {"G4-4"}

        for sheet in G4_MAIN_SHEETS:
            if sheet["code"] in core_codes:
                assert sheet["group"] == "core", f"{sheet['code']} 应为 core 组"
            elif sheet["code"] in measurement_codes:
                assert sheet["group"] == "measurement", f"{sheet['code']} 应为 measurement 组"

    def test_account_spec_is_bond_investment_1504(self):
        """科目定位改走规格声明，不再有 `_G4_ACCOUNT_PREFIX` 常量。

        🔴 原断言 ``_G4_ACCOUNT_PREFIX == "1501"`` 钉死的是**错码**
        —— `1501` 是旧准则「持有至到期投资」，债权投资真值 `1504`
        （`account_chart` + `trial_balance.account_name` 双证）。
        """
        from app.routers.wp_render_strategies import _g4_bond_investment_main as mod

        assert not hasattr(mod, "_G4_ACCOUNT_PREFIX"), "旧硬编码前缀常量不得复活"
        assert mod.G4_ACCOUNT_SPEC.row_code == "BS-021"
        assert tuple(mod.G4_ACCOUNT_SPEC.fallback_gross) == ("1504",)
        assert "1501" not in tuple(mod.G4_ACCOUNT_SPEC.fallback_gross)

    def test_adjudicated_item_id_format(self):
        from app.routers.wp_render_strategies._g4_bond_investment_main import _ADJUDICATED_ITEM_ID

        assert _ADJUDICATED_ITEM_ID == "G4-1-adjudicated-amount"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 注册契约验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestG4MainRegistrationContract:
    """验证 g4-bond-investment-main 注册四件套完整."""

    def test_valid_component_types_contains_g4_main(self):
        from app.services.wp_classification_service import VALID_COMPONENT_TYPES

        assert "g4-bond-investment-main" in VALID_COMPONENT_TYPES

    def test_renderer_dispatch_contains_g4_main(self):
        from app.routers.wp_render_strategies import RENDERER_DISPATCH

        assert "g4-bond-investment-main" in RENDERER_DISPATCH

    def test_renderer_dispatch_callable(self):
        from app.routers.wp_render_strategies import RENDERER_DISPATCH

        render_fn = RENDERER_DISPATCH["g4-bond-investment-main"]
        assert callable(render_fn)

    def test_wp_code_overrides_g4_entries(self):
        overrides_path = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
        with open(overrides_path, encoding="utf-8") as f:
            overrides = json.load(f)

        # G4 prefix code 应映射为 g4-bond-investment-main
        assert overrides.get("G4") == "g4-bond-investment-main"

    def test_wp_code_overrides_g4_related_codes(self):
        overrides_path = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
        with open(overrides_path, encoding="utf-8") as f:
            overrides = json.load(f)

        # 至少有 G4 的映射条目
        g4_entries = {k: v for k, v in overrides.items() if v == "g4-bond-investment-main"}
        # 至少1个（G4前缀码），最多8个
        assert len(g4_entries) >= 1, f"wp_code_overrides 中 g4-bond-investment-main 映射条目不足: {g4_entries}"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 导入导出 round-trip
# ═══════════════════════════════════════════════════════════════════════════════


class TestG4MainImportExportRoundTrip:
    """验证 G4-1/2/3/4 导入导出列结构与当前 Excel 对齐契约."""

    def test_g4_2_segments_total_columns(self):
        from app.routers.wp_render_strategies._g4_bond_investment_main_import_export import (
            _G4_2_ALL_HEADERS,
            _G4_2_ALL_KEYS,
        )

        # 对齐 Excel：6+9+4+9+6 = 34
        assert len(_G4_2_ALL_HEADERS) == 34
        assert len(_G4_2_ALL_KEYS) == 34
        assert len(_G4_2_ALL_HEADERS) == len(_G4_2_ALL_KEYS)

    def test_g4_2_five_segments_defined(self):
        from app.routers.wp_render_strategies._g4_bond_investment_main_import_export import (
            _G4_2_SEGMENTS,
        )

        assert len(_G4_2_SEGMENTS) == 5
        seg_names = [s[0] for s in _G4_2_SEGMENTS]
        assert seg_names == ["基础信息", "期初余额", "本期变动", "期末余额+减值", "摊余成本+审定"]

    def test_g4_2_segment_column_counts(self):
        from app.routers.wp_render_strategies._g4_bond_investment_main_import_export import (
            _G4_2_SEG1_HEADERS,
            _G4_2_SEG2_HEADERS,
            _G4_2_SEG3_HEADERS,
            _G4_2_SEG4_HEADERS,
            _G4_2_SEG5_HEADERS,
        )

        assert len(_G4_2_SEG1_HEADERS) == 6   # 基础信息
        assert len(_G4_2_SEG2_HEADERS) == 9   # 期初余额
        assert len(_G4_2_SEG3_HEADERS) == 4   # 本期变动
        assert len(_G4_2_SEG4_HEADERS) == 9   # 期末余额+减值
        assert len(_G4_2_SEG5_HEADERS) == 6   # 摊余成本+审定

    def test_g4_3_headers_10_columns(self):
        from app.routers.wp_render_strategies._g4_bond_investment_main_import_export import (
            _G4_3_HEADERS,
            _G4_3_KEYS,
        )

        assert len(_G4_3_HEADERS) == 10
        assert len(_G4_3_KEYS) == 10
        assert "调整事项说明" in _G4_3_HEADERS
        assert "科目代码" in _G4_3_HEADERS
        assert "借方调整金额" in _G4_3_HEADERS
        assert "贷方调整金额" in _G4_3_HEADERS

    def test_g4_4_headers_18_columns(self):
        from app.routers.wp_render_strategies._g4_bond_investment_main_import_export import (
            _G4_4_HEADERS,
            _G4_4_KEYS,
        )

        assert len(_G4_4_HEADERS) == 18
        assert len(_G4_4_KEYS) == 18
        assert "投资项目" in _G4_4_HEADERS
        assert "面值总额" in _G4_4_HEADERS
        assert "初始入账价值" in _G4_4_HEADERS
        assert "截止日" in _G4_4_HEADERS
        assert "实际利息收入" in _G4_4_HEADERS
        assert "计息天数" in _G4_4_HEADERS

    def test_g4_2_headers_keys_alignment(self):
        from app.routers.wp_render_strategies._g4_bond_investment_main_import_export import (
            _G4_2_ALL_HEADERS,
            _G4_2_ALL_KEYS,
        )

        for i, (h, k) in enumerate(zip(_G4_2_ALL_HEADERS, _G4_2_ALL_KEYS)):
            assert h, f"第{i}列 header 为空"
            assert k, f"第{i}列 key 为空"

    def test_g4_3_keys_match_frontend_interface(self):
        from app.routers.wp_render_strategies._g4_bond_investment_main_import_export import (
            _G4_3_KEYS,
        )

        expected_keys = [
            "description", "category", "reportItem", "accountCode", "accountName",
            "noteItem", "debitAmount", "creditAmount", "indexRef", "remark",
        ]
        assert _G4_3_KEYS == expected_keys

    def test_g4_4_keys_match_frontend_interface(self):
        from app.routers.wp_render_strategies._g4_bond_investment_main_import_export import (
            _G4_4_KEYS,
        )

        initial_keys = _G4_4_KEYS[:9]
        interest_keys = _G4_4_KEYS[9:]
        assert "projectName" in initial_keys
        assert "initialCarryingAmount" in initial_keys
        assert "effectiveInterest" in interest_keys
        assert "days" in interest_keys
        assert len(initial_keys) == 9
        assert len(interest_keys) == 9

    def test_supported_sheets_include_g4_1_to_4(self):
        from app.routers.wp_render_strategies._g4_bond_investment_main_import_export import (
            _SUPPORTED_SHEETS,
        )

        assert _SUPPORTED_SHEETS == {"G4-1", "G4-2", "G4-3", "G4-4"}

    def test_item_ids_mapping(self):
        from app.routers.wp_render_strategies._g4_bond_investment_main_import_export import (
            _ITEM_IDS,
            _G4_4_PRIMARY_ITEM_ID,
        )

        assert _ITEM_IDS["G4-1"] == "G4-1-rows"
        assert _ITEM_IDS["G4-2"] == "G4-2-rows"
        assert _ITEM_IDS["G4-3"] == "G4-3-rows"
        assert _ITEM_IDS["G4-4"] == "G4-4-rows"
        assert _G4_4_PRIMARY_ITEM_ID == "G4-4-interest-calc"

    def test_g4_4_nest_flatten_roundtrip_rates(self):
        from app.routers.wp_render_strategies._g4_bond_investment_main_import_export import (
            _flatten_g4_4_groups,
            _nest_g4_4_flat_rows,
        )

        nested = [{
            "id": "g1",
            "projectName": "国债A",
            "initial": {
                "faceValueTotal": 100,
                "couponRate": 0.035,
                "effectiveRate": 0.04,
                "initialCarryingAmount": 98,
            },
            "periods": [{
                "cutoffDate": "2025-12-31",
                "openingBalance": 98,
                "effectiveInterest": 3.92,
                "days": 365,
            }],
        }]
        flat = _flatten_g4_4_groups(nested)
        assert len(flat) == 1
        assert flat[0]["couponRate"] == 3.5
        assert flat[0]["effectiveRate"] == 4.0
        restored = _nest_g4_4_flat_rows(flat)
        assert len(restored) == 1
        assert restored[0]["initial"]["couponRate"] == 0.035
        assert restored[0]["initial"]["effectiveRate"] == 0.04
        assert restored[0]["periods"][0]["cutoffDate"] == "2025-12-31"

    def test_g4_2_multi_sheet_workbook_structure(self):
        """验证G4-2多sheet导出的 workbook 结构."""
        from app.routers.wp_render_strategies._g4_bond_investment_main_import_export import (
            _build_g4_2_multi_sheet_workbook,
        )

        # 空数据模板导出
        wb = _build_g4_2_multi_sheet_workbook([], template_only=True)
        sheet_names = wb.sheetnames

        # 5个区段sheet + 1个编制说明
        assert len(sheet_names) == 6
        assert "基础信息" in sheet_names
        assert "期初余额" in sheet_names
        assert "本期变动" in sheet_names
        assert "期末余额+减值" in sheet_names
        assert "摊余成本+审定" in sheet_names
        assert "编制说明" in sheet_names

    def test_g4_2_multi_sheet_export_with_data(self):
        """验证G4-2带数据导出."""
        from app.routers.wp_render_strategies._g4_bond_investment_main_import_export import (
            _build_g4_2_multi_sheet_workbook,
        )

        test_rows = [
            {
                "investCategory": "国债",
                "investProject": "国开行2025-01",
                "faceValue": 10000000,
                "couponRate": 3.5,
                "effectiveRate": 4.0,
                "maturityDate": "2030-06-15",
                "openingCost": 9800000,
                "openingInterestAdj": 150000,
                "openingAccruedInterest": 87500,
            },
        ]

        wb = _build_g4_2_multi_sheet_workbook(test_rows, template_only=False)

        # 基础信息sheet应有3行（标题+表头+数据）
        ws = wb["基础信息"]
        row_count = ws.max_row
        assert row_count >= 3  # 至少有标题+表头+1数据行

    def test_g4_2_import_parse_multi_sheet(self):
        """验证G4-2多sheet格式导入解析."""
        from app.routers.wp_render_strategies._g4_bond_investment_main_import_export import (
            _parse_g4_2_import,
            _G4_2_SEG1_HEADERS,
            _G4_2_SEG2_HEADERS,
            _G4_2_SEG3_HEADERS,
            _G4_2_SEG4_HEADERS,
            _G4_2_SEG5_HEADERS,
        )

        # 构造多sheet workbook
        wb = Workbook()
        wb.remove(wb.active)

        # 区段1: 基础信息
        ws1 = wb.create_sheet("基础信息")
        ws1.append(["G4-2 明细表 — 基础信息"])
        ws1.append(_G4_2_SEG1_HEADERS)
        ws1.append(["企业债", "工商银行2025", 10000000, 3.5, 4.0, "2030-01-01"])

        # 区段2: 期初余额
        ws2 = wb.create_sheet("期初余额")
        ws2.append(["G4-2 明细表 — 期初余额"])
        ws2.append(_G4_2_SEG2_HEADERS)
        ws2.append([9800000, 150000, 87500, 10037500, 50000, 9987500, 0, 0, 9987500, ""])

        # 区段3: 本期变动
        ws3 = wb.create_sheet("本期变动")
        ws3.append(["G4-2 明细表 — 本期变动"])
        ws3.append(_G4_2_SEG3_HEADERS)
        ws3.append([0, 20000, 175000, 195000])

        # 区段4: 期末余额+减值
        ws4 = wb.create_sheet("期末余额+减值")
        ws4.append(["G4-2 明细表 — 期末余额+减值"])
        ws4.append(_G4_2_SEG4_HEADERS)
        ws4.append([9800000, 170000, 262500, 10232500, 80000, "Stage1", "", "", 80000, ""])

        # 区段5: 摊余成本+审定
        ws5 = wb.create_sheet("摊余成本+审定")
        ws5.append(["G4-2 明细表 — 摊余成本+审定"])
        ws5.append(_G4_2_SEG5_HEADERS)
        ws5.append([10152500, 2000000, 10000, 1990000, 8162500, "", 0, ""])

        # 保存到 bytes
        buf = io.BytesIO()
        wb.save(buf)
        content = buf.getvalue()

        rows, errors = _parse_g4_2_import(content)
        assert len(rows) == 1
        assert not errors or all("缺少" not in e for e in errors)

        row = rows[0]
        assert row.get("investCategory") == "企业债"
        assert row.get("investProject") == "工商银行2025"
        assert row.get("openingCost") == 9800000

    def test_round_trip_g4_2_export_then_import(self):
        """G4-2 round-trip: 导出→导入→数据一致."""
        from app.routers.wp_render_strategies._g4_bond_investment_main_import_export import (
            _build_g4_2_multi_sheet_workbook,
            _parse_g4_2_import,
        )

        original_rows = [
            {
                "id": "test-001",
                "investCategory": "金融债",
                "investProject": "农发行2025-03",
                "faceValue": 5000000.0,
                "couponRate": 3.2,
                "effectiveRate": 3.8,
                "maturityDate": "2028-12-31",
                "openingCost": 4900000.0,
                "openingInterestAdj": 80000.0,
                "openingAccruedInterest": 43000.0,
                "openingSubtotal": 5023000.0,
                "openingImpairment": 0.0,
                "openingAmortizedCost": 5023000.0,
                "openingOneYearDeduct": 0.0,
                "openingAdjustment": 0.0,
                "openingAdjusted": 5023000.0,
                "openingRemark": "",
                "periodCostChange": 0.0,
                "periodInterestAdjChange": 15000.0,
                "periodAccruedInterestChange": 80000.0,
                "periodChangeSubtotal": 95000.0,
                "closingCost": 4900000.0,
                "closingInterestAdj": 95000.0,
                "closingAccruedInterest": 123000.0,
                "closingSubtotal": 5118000.0,
                "closingImpairment": 30000.0,
                "stageClassification": "Stage1",
                "creditCombineMethod": "",
                "creditCombineName": "",
                "impairmentAdjusted": 30000.0,
                "closingRemark": "",
                "amortizedCost": 5088000.0,
                "oneYearBalance": 0.0,
                "oneYearImpairment": 0.0,
                "oneYearSubtotal": 0.0,
                "bookValue": 5088000.0,
                "correspondenceStatus": "",
                "auditAdjustment": 0.0,
                "indexRef": "",
            },
        ]

        # Export
        wb = _build_g4_2_multi_sheet_workbook(original_rows, template_only=False)
        buf = io.BytesIO()
        wb.save(buf)
        exported_bytes = buf.getvalue()

        # Import
        imported_rows, errors = _parse_g4_2_import(exported_bytes)
        assert len(imported_rows) == 1

        row = imported_rows[0]
        # 关键字段一致性
        assert row["investCategory"] == "金融债"
        assert row["investProject"] == "农发行2025-03"
        assert row["faceValue"] == 5000000.0
        assert row["openingCost"] == 4900000.0
        assert row["stageClassification"] == "Stage1"
