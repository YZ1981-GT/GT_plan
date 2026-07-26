"""N1 递延所得税资产 — 后端集成测试 (Task 7.2).

覆盖：
1. 模块导入测试：renderer / router / service 均可导入
2. RENDERER_DISPATCH 注册验证
3. wp_code_overrides 覆盖(9条目: N1/N1-1~N1-5/N1A)
4. 路由注册(3端点存在)
5. 资产类取数逻辑（期末=期初+借方-贷方）
6. 递延所得税测算引擎（差异×税率+分类）
7. 可弥补亏损确认引擎（谨慎性限额）
8. 跨底稿合计（N1+N3→N5递延所得税费用）

Spec: .kiro/specs/n1-deferred-tax-assets/ Task 7.2
Requirements: 2.5-2.6, 4.4, 5.5, 7.1-7.5, 8.1-8.4

科目：1811 递延所得税资产（**借方/资产类！期末=期初+借方-贷方**）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1: 模块导入测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestN1Imports:
    """renderer, router, service 均可导入（无语法错误/循环依赖）"""

    def test_renderer_importable(self):
        """渲染策略可导入"""
        from app.routers.wp_render_strategies._n1_deferred_tax_assets import render  # noqa: F401
        assert callable(render)

    def test_router_importable(self):
        """路由模块可导入"""
        from app.routers.n1_deferred_tax_assets import router  # noqa: F401
        assert router is not None

    def test_service_importable(self):
        """服务模块可导入"""
        from app.services.n1_deferred_tax_assets_service import (
            calc_asset_end_balance,
            calc_audited_amount,
            calc_temporary_difference,
            calc_deferred_tax,
            calc_deferred_tax_asset,
            calc_unrecovered_loss,
            calc_recognizable_asset,
            is_compensation_expired,
            classify_temporary_differences,
            calc_loss_recognition,
        )
        assert callable(calc_asset_end_balance)
        assert callable(calc_audited_amount)
        assert callable(calc_temporary_difference)
        assert callable(calc_deferred_tax)
        assert callable(calc_deferred_tax_asset)
        assert callable(calc_unrecovered_loss)
        assert callable(calc_recognizable_asset)
        assert callable(is_compensation_expired)
        assert callable(classify_temporary_differences)
        assert callable(calc_loss_recognition)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2: RENDERER_DISPATCH 集成
# ═══════════════════════════════════════════════════════════════════════════════


class TestRendererDispatch:
    """验证 n1-deferred-tax-assets 在 RENDERER_DISPATCH 中注册"""

    def test_renderer_dispatch_contains_n1(self):
        """RENDERER_DISPATCH 有 n1-deferred-tax-assets 条目"""
        from app.routers.wp_render_strategies import RENDERER_DISPATCH
        assert "n1-deferred-tax-assets" in RENDERER_DISPATCH

    def test_renderer_dispatch_value_is_callable(self):
        """RENDERER_DISPATCH['n1-deferred-tax-assets'] 是可调用的 render 函数"""
        from app.routers.wp_render_strategies import RENDERER_DISPATCH
        fn = RENDERER_DISPATCH["n1-deferred-tax-assets"]
        assert callable(fn)

    def test_renderer_dispatch_value_is_correct_function(self):
        """RENDERER_DISPATCH 指向正确的 render 函数"""
        from app.routers.wp_render_strategies import RENDERER_DISPATCH
        from app.routers.wp_render_strategies._n1_deferred_tax_assets import render
        assert RENDERER_DISPATCH["n1-deferred-tax-assets"] is render


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3: wp_code_overrides 覆盖 (N1系列9条目)
# ═══════════════════════════════════════════════════════════════════════════════


class TestWpCodeOverrides:
    """验证 wp_code_overrides.json 中 N1 系列映射"""

    @pytest.fixture(scope="class")
    def overrides(self) -> dict[str, str]:
        """加载 wp_code_overrides.json"""
        overrides_path = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "data"
            / "wp_code_overrides.json"
        )
        assert overrides_path.exists(), f"wp_code_overrides.json 不存在: {overrides_path}"
        with open(overrides_path, encoding="utf-8") as f:
            return json.load(f)

    @pytest.mark.parametrize(
        "wp_code",
        [
            "N1",
            "N1-1",
            "N1-2",
            "N1-3",
            "N1-4",
            "N1-5",
            "N1A",
        ],
    )
    def test_n1_wp_code_mapped(self, overrides: dict, wp_code: str):
        """N1系列wp_code均映射到n1-deferred-tax-assets"""
        assert wp_code in overrides, f"wp_code '{wp_code}' 不在 overrides 中"
        assert overrides[wp_code] == "n1-deferred-tax-assets"


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4: 资产类取数逻辑 (Req 8.1-8.4)
# ═══════════════════════════════════════════════════════════════════════════════


class TestAssetEndBalance:
    """资产类期末余额 = 期初 + 借方 - 贷方（Req 8.1）"""

    def test_basic_asset_end_balance(self):
        """期初1000万+借500万-贷200万 = 1300万"""
        from app.services.n1_deferred_tax_assets_service import calc_asset_end_balance
        result = calc_asset_end_balance(10_000_000, 5_000_000, 2_000_000)
        assert result == 13_000_000

    def test_zero_begin_debit_only(self):
        """零期初+仅借方 → 期末=借方"""
        from app.services.n1_deferred_tax_assets_service import calc_asset_end_balance
        result = calc_asset_end_balance(0, 3_000_000, 0)
        assert result == 3_000_000

    def test_full_reversal(self):
        """全额转回 → 期末=0"""
        from app.services.n1_deferred_tax_assets_service import calc_asset_end_balance
        result = calc_asset_end_balance(5_000_000, 0, 5_000_000)
        assert result == 0

    def test_asset_vs_liability_direction(self):
        """资产类 vs 负债类方向不同验证"""
        from app.services.n1_deferred_tax_assets_service import calc_asset_end_balance
        begin, debit, credit = 5_000_000, 3_000_000, 1_000_000
        asset_end = calc_asset_end_balance(begin, debit, credit)
        liability_end = begin + credit - debit  # 负债类
        assert asset_end == 7_000_000
        assert liability_end == 3_000_000
        assert asset_end != liability_end

    def test_validate_asset_direction(self):
        """validate_asset_direction 校验通过"""
        from app.services.n1_deferred_tax_assets_service import validate_asset_direction
        result = validate_asset_direction(10_000_000, 5_000_000, 2_000_000, 13_000_000)
        assert result["isValid"] is True
        assert result["direction"] == "debit"
        assert result["account_code"] == "1811"

    def test_validate_asset_direction_mismatch(self):
        """validate_asset_direction 校验失败（报告值不等于计算值）"""
        from app.services.n1_deferred_tax_assets_service import validate_asset_direction
        result = validate_asset_direction(10_000_000, 5_000_000, 2_000_000, 14_000_000)
        assert result["isValid"] is False
        assert result["difference"] == 1_000_000


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5: 递延所得税测算引擎 (Req 4.2-4.4)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeferredTaxEngine:
    """递延所得税 = 暂时性差异 × 适用税率"""

    def test_temporary_difference(self):
        """暂时性差异 = 账面价值 - 计税基础"""
        from app.services.n1_deferred_tax_assets_service import calc_temporary_difference
        assert calc_temporary_difference(1_000_000, 1_500_000) == -500_000  # 可抵扣
        assert calc_temporary_difference(2_000_000, 1_500_000) == 500_000   # 应纳税
        assert calc_temporary_difference(1_000_000, 1_000_000) == 0          # 无差异

    def test_deferred_tax(self):
        """递延所得税 = 差异 × 税率"""
        from app.services.n1_deferred_tax_assets_service import calc_deferred_tax
        assert calc_deferred_tax(2_000_000, 0.25) == 500_000
        assert calc_deferred_tax(-500_000, 0.25) == -125_000
        assert calc_deferred_tax(0, 0.25) == 0

    def test_deferred_tax_asset(self):
        """递延所得税资产 = 可抵扣差异 × 税率"""
        from app.services.n1_deferred_tax_assets_service import calc_deferred_tax_asset
        assert calc_deferred_tax_asset(500_000, 0.25) == 125_000
        assert calc_deferred_tax_asset(3_000_000, 0.15) == 450_000

    def test_classify_temporary_differences(self):
        """分类暂时性差异：可抵扣→N1资产，应纳税→N3负债"""
        from app.services.n1_deferred_tax_assets_service import classify_temporary_differences
        rows = [
            {"bookValue": 1_000_000, "taxBase": 1_500_000, "name": "资产减值"},   # 可抵扣
            {"bookValue": 2_000_000, "taxBase": 1_500_000, "name": "公允价值"},   # 应纳税
            {"bookValue": 800_000, "taxBase": 1_000_000, "name": "预提费用"},     # 可抵扣
            {"bookValue": 1_000_000, "taxBase": 1_000_000, "name": "无差异"},     # 无
        ]
        result = classify_temporary_differences(rows)
        assert len(result["deductible"]) == 2  # 资产减值+预提费用→N1
        assert len(result["taxable"]) == 1     # 公允价值→N3
        # 验证可抵扣差异绝对值
        assert result["deductible"][0]["deductibleDiff"] == 500_000
        assert result["deductible"][1]["deductibleDiff"] == 200_000
        # 验证应纳税差异
        assert result["taxable"][0]["taxableDiff"] == 500_000

    def test_weighted_avg_rate(self):
        """加权平均税率验证"""
        from app.services.n1_deferred_tax_assets_service import calc_weighted_avg_rate
        tax_amounts = [500_000, 150_000, 125_000]
        diffs = [2_000_000, 1_000_000, 500_000]
        expected = sum(tax_amounts) / sum(diffs)
        assert abs(calc_weighted_avg_rate(tax_amounts, diffs) - expected) < 1e-10

    def test_weighted_avg_rate_zero_diffs(self):
        """差异合计=0时返回0"""
        from app.services.n1_deferred_tax_assets_service import calc_weighted_avg_rate
        assert calc_weighted_avg_rate([0, 0], [0, 0]) == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Section 6: 可弥补亏损确认引擎 (Req 5.2-5.5)
# ═══════════════════════════════════════════════════════════════════════════════


class TestLossCompensationEngine:
    """可弥补亏损确认：min(未弥补亏损, 预计未来所得额)×税率"""

    def test_unrecovered_loss(self):
        """未弥补亏损 = 亏损 - 已弥补"""
        from app.services.n1_deferred_tax_assets_service import calc_unrecovered_loss
        assert calc_unrecovered_loss(10_000_000, 2_000_000) == 8_000_000
        assert calc_unrecovered_loss(5_000_000, 5_000_000) == 0
        assert calc_unrecovered_loss(3_000_000, 5_000_000) == 0  # 不允许负值

    def test_recognizable_asset(self):
        """可确认递延税资产 = min(未弥补, 未来所得额) × 税率"""
        from app.services.n1_deferred_tax_assets_service import calc_recognizable_asset
        # 未弥补800万, 未来所得500万 → min(800,500)×25%=125万
        assert calc_recognizable_asset(8_000_000, 5_000_000, 0.25) == 1_250_000
        # 未弥补200万, 未来所得500万 → min(200,500)×25%=50万
        assert calc_recognizable_asset(2_000_000, 5_000_000, 0.25) == 500_000

    def test_compensation_expired(self):
        """弥补期限届满判断"""
        from app.services.n1_deferred_tax_assets_service import is_compensation_expired
        # 2019年亏损, 2025年审计, 5年 → 2025-2019=6>5 → 届满
        assert is_compensation_expired(2019, 2025, 5) is True
        # 2020年亏损, 2025年审计, 5年 → 2025-2020=5=5 → 未届满
        assert is_compensation_expired(2020, 2025, 5) is False
        # 高新10年：2016年, 2025年 → 2025-2016=9<10 → 未届满
        assert is_compensation_expired(2016, 2025, 10) is False

    def test_loss_recognition_batch(self):
        """批量亏损确认计算"""
        from app.services.n1_deferred_tax_assets_service import calc_loss_recognition
        losses = [
            {"lossYear": 2021, "lossAmount": 5_000_000, "recovered": 1_000_000, "maxYears": 5},
            {"lossYear": 2022, "lossAmount": 3_000_000, "recovered": 500_000, "maxYears": 5},
        ]
        result = calc_loss_recognition(losses, 10_000_000, 0.25)
        assert result["totalUnrecovered"] > 0
        assert result["totalRecognizable"] > 0
        assert result["insufficientWarning"] is False
        assert len(result["details"]) == 2

    def test_loss_recognition_insufficient_income(self):
        """未来所得额不足 → insufficientWarning=True"""
        from app.services.n1_deferred_tax_assets_service import calc_loss_recognition
        losses = [
            {"lossYear": 2023, "lossAmount": 20_000_000, "recovered": 0, "maxYears": 5},
        ]
        result = calc_loss_recognition(losses, 5_000_000, 0.25)
        assert result["insufficientWarning"] is True
        assert result["totalUnrecovered"] == 20_000_000


# ═══════════════════════════════════════════════════════════════════════════════
# Section 7: 跨底稿合计逻辑 (Req 7.1-7.5, 4.4)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossWorkpaperTotals:
    """N1+N3→N5 递延所得税费用核对逻辑"""

    def test_deferred_tax_expense_formula(self):
        """递延所得税费用 = N3本期变动 - N1本期变动"""
        # N1变动(资产增加300万): 费用=-300万（资产增加减少费用）
        # N3变动(负债增加200万): 费用=+200万（负债增加增加费用）
        n1_change = 3_000_000
        n3_change = 2_000_000
        deferred_tax_expense = n3_change - n1_change
        assert deferred_tax_expense == -1_000_000

    def test_n1_n3_correspondence_asset_liability_split(self):
        """N1-4同源测算：可抵扣→N1资产 / 应纳税→N3负债"""
        from app.services.n1_deferred_tax_assets_service import (
            classify_temporary_differences,
            calc_deferred_tax_asset,
        )
        rows = [
            {"bookValue": 5_000_000, "taxBase": 8_000_000},   # 可抵扣300万
            {"bookValue": 10_000_000, "taxBase": 7_000_000},  # 应纳税300万
            {"bookValue": 2_000_000, "taxBase": 3_000_000},   # 可抵扣100万
        ]
        classified = classify_temporary_differences(rows)
        # 可抵扣部分（→N1）: 300万+100万=400万
        total_deductible = sum(r["deductibleDiff"] for r in classified["deductible"])
        assert total_deductible == 4_000_000
        # 应纳税部分（→N3）: 300万
        total_taxable = sum(r["taxableDiff"] for r in classified["taxable"])
        assert total_taxable == 3_000_000
        # 递延税资产合计
        total_asset = calc_deferred_tax_asset(total_deductible, 0.25)
        assert total_asset == 1_000_000

    def test_period_change_for_n5(self):
        """本期变动额 = 期末 - 期初（供N5核对）"""
        from app.services.n1_deferred_tax_assets_service import calc_asset_end_balance
        begin = 10_000_000
        end = calc_asset_end_balance(begin, 5_000_000, 2_000_000)
        change = end - begin
        assert change == 3_000_000

    def test_audited_amount_writeback_payload(self):
        """审定数 = 未审 + AJE + RJE → 回写 trial_balance 期末余额"""
        from app.services.n1_deferred_tax_assets_service import calc_audited_amount
        audited = calc_audited_amount(12_000_000, 500_000, -200_000)
        assert audited == 12_300_000
        # 回写payload验证
        payload = {
            "account_code": "1811",
            "audited_amount": audited,
            "direction": "debit",
        }
        assert payload["account_code"] == "1811"
        assert payload["direction"] == "debit"
        assert payload["audited_amount"] == 12_300_000


# ═══════════════════════════════════════════════════════════════════════════════
# Section 8: E2E 完整流程（纯函数闭环）
# ═══════════════════════════════════════════════════════════════════════════════


class TestE2EFlow:
    """完整流程：TB取数→审定→明细→测算→亏损→N3→N5"""

    def test_full_pipeline(self):
        """N1完整计算流程闭环"""
        from app.services.n1_deferred_tax_assets_service import (
            calc_asset_end_balance,
            calc_audited_amount,
            calc_temporary_difference,
            calc_deferred_tax_asset,
            calc_unrecovered_loss,
            calc_recognizable_asset,
            classify_temporary_differences,
        )

        # Step 1: TB取数（资产类借方）
        begin = 10_000_000
        debit = 5_000_000
        credit = 2_000_000
        end_balance = calc_asset_end_balance(begin, debit, credit)
        assert end_balance == 13_000_000

        # Step 2: 审定数
        audited = calc_audited_amount(end_balance, 200_000, -100_000)
        assert audited == 13_100_000

        # Step 3: 暂时性差异分类
        rows = [
            {"bookValue": 5_000_000, "taxBase": 8_000_000},   # 可抵扣300万
            {"bookValue": 2_000_000, "taxBase": 4_000_000},   # 可抵扣200万
            {"bookValue": 10_000_000, "taxBase": 7_000_000},  # 应纳税300万→N3
        ]
        classified = classify_temporary_differences(rows)
        assert len(classified["deductible"]) == 2
        assert len(classified["taxable"]) == 1

        # Step 4: 递延税资产合计
        total_deductible = sum(
            r["deductibleDiff"] for r in classified["deductible"]
        )
        assert total_deductible == 5_000_000  # 300万+200万
        dta = calc_deferred_tax_asset(total_deductible, 0.25)
        assert dta == 1_250_000

        # Step 5: 可弥补亏损确认
        unrecovered = calc_unrecovered_loss(4_000_000, 1_000_000)
        assert unrecovered == 3_000_000
        loss_asset = calc_recognizable_asset(unrecovered, 2_000_000, 0.25)
        assert loss_asset == 500_000  # min(300,200)×25%

        # Step 6: 跨底稿
        total_asset = dta + loss_asset  # 125万+50万=175万
        assert total_asset == 1_750_000
        total_liability = calc_deferred_tax_asset(
            classified["taxable"][0]["taxableDiff"], 0.25
        )
        assert total_liability == 750_000

        # Step 7: N5递延税费用核对
        period_change = end_balance - begin  # 300万
        assert period_change == 3_000_000


# ═══════════════════════════════════════════════════════════════════════════════
# Section 9: 导入导出 Sheet_Spec 三重键契约（防串表 / 防 Orphan_Key）
# ═══════════════════════════════════════════════════════════════════════════════


class TestN1ImportExportSheetSpecContract:
    """N1 导入导出 spec 必须覆盖全部挂了「导入导出 ▾」的 sheet，且三重键与前端一致。

    背景（真实缺陷）：N1-4/N1-5 页面挂了导入导出按钮但后端只注册 N1-2，
    前端调用又漏传 sheet → 落到 Query 默认值 "N1-2"
    → 在测算表/亏损表导出到的是明细表数据、导入会覆盖 N1-2 明细行（串表 + 数据破坏）。
    """

    @pytest.mark.parametrize("sheet", ["N1-2", "N1-4", "N1-5"])
    def test_sheet_registered_in_all_maps(self, sheet: str):
        """每个受支持 sheet 在 headers/field_map/item_id/storage_field/row-id 五张表齐备"""
        from app.routers.n1_deferred_tax_assets import (
            _FIELD_MAPS,
            _SHEET_HEADERS,
            _SHEET_ITEM_ID,
            _SHEET_ROW_ID_PREFIX,
            _SHEET_STORAGE_FIELD,
            _SUPPORTED_SHEETS,
        )

        assert sheet in _SUPPORTED_SHEETS
        assert sheet in _SHEET_HEADERS and _SHEET_HEADERS[sheet]
        assert sheet in _FIELD_MAPS and _FIELD_MAPS[sheet]
        assert sheet in _SHEET_ITEM_ID
        assert sheet in _SHEET_STORAGE_FIELD
        assert sheet in _SHEET_ROW_ID_PREFIX
        # headers 与 field_map 一一对应（导出按 headers 取 field，漏项会导出空列）
        assert set(_SHEET_HEADERS[sheet]) == set(_FIELD_MAPS[sheet].keys())

    def test_item_id_matches_frontend_storage_key(self):
        """item_id 必须等于前端 composable 的持久化键（写错 = 导入后前端读不到）"""
        from app.routers.n1_deferred_tax_assets import _SHEET_ITEM_ID

        assert _SHEET_ITEM_ID["N1-2"] == "N1-2-detail-rows"   # useN1Detail
        assert _SHEET_ITEM_ID["N1-4"] == "N1-4-calc-rows"     # useN1CalcTable
        assert _SHEET_ITEM_ID["N1-5"] == "N1-5-rows"           # useN1LossCheck（新键，spec n1-loss-check-source-alignment）

    def test_storage_field_is_conclusion(self):
        """N1 三张动态行表前端均把行数组 JSON 存在 conclusion 列"""
        from app.routers.n1_deferred_tax_assets import _SHEET_STORAGE_FIELD

        assert set(_SHEET_STORAGE_FIELD.values()) == {"conclusion"}

    def test_field_keys_match_frontend_row_models(self):
        """field_keys 必须是前端行模型字段名（否则导入后字段读不出）"""
        from app.routers.n1_deferred_tax_assets import _FIELD_MAPS

        assert set(_FIELD_MAPS["N1-4"].values()) == {
            "itemName", "bookValue", "taxBase", "taxRate",
            "assetCounterAccount", "assetBookBalance",
            "liabilityCounterAccount", "liabilityBookBalance",
        }
        assert set(_FIELD_MAPS["N1-5"].values()) == {
            "expiryYear", "priorUnrecognized", "bookAmount", "auditAdjustment",
            "recognizedAmount", "taxRate", "basis", "sufficient",
            "sourceOperating", "sourceTemporaryDiff", "sourceOther",
            "indexRef", "remark",
        }

    def test_unsupported_sheet_rejected(self):
        """未注册 sheet 必须 400，不得静默落到默认 sheet"""
        from fastapi import HTTPException

        from app.routers.n1_deferred_tax_assets import _validate_sheet

        with pytest.raises(HTTPException) as exc:
            _validate_sheet("N1-1")
        assert exc.value.status_code == 400

    def test_parse_row_uses_sheet_specific_id_prefix_and_int_years(self):
        """行 id 前缀按 sheet 生成（对齐前端 addRow），年度解析为 int 不带 .0"""
        from app.routers.n1_deferred_tax_assets import _parse_row, _SHEET_HEADERS

        # N1-5 新模型列（spec n1-loss-check-source-alignment Task 5.1）
        headers = _SHEET_HEADERS["N1-5"]
        row = (
            2027,      # 到期年度
            50000,     # 上期不确认
            200000,    # 本期账面金额
            -10000,    # 本期审计调整
            120000,    # 确认金额
            0.25,      # 适用税率
            "预计未来所得额充足",  # 依据
            "是",      # 到期前是否有足够的应纳税所得额
            "√",       # 其中：来源于生产经营所得
            "",        # 其中：来源于暂时性差异
            "否",      # 其中：来源于其他原因
            "N1-4",    # 检查底稿索引
            "高新10年", # 备注
        )
        parsed = _parse_row("N1-5", row, headers, seq=1)

        assert parsed["id"] == "loss-1"
        assert parsed["expiryYear"] == 2027 and isinstance(parsed["expiryYear"], int)
        assert parsed["priorUnrecognized"] == 50000.0
        assert parsed["bookAmount"] == 200000.0
        assert parsed["auditAdjustment"] == -10000.0
        assert parsed["recognizedAmount"] == 120000.0
        assert parsed["taxRate"] == 0.25
        assert parsed["basis"] == "预计未来所得额充足"
        assert parsed["sufficient"] == "yes"
        assert parsed["sourceOperating"] is True
        assert parsed["sourceTemporaryDiff"] is False
        assert parsed["sourceOther"] is False
        assert parsed["indexRef"] == "N1-4"
        assert parsed["remark"] == "高新10年"
        # Property 11: 派生列不出现在解析结果里
        assert "auditedAmount" not in parsed
        assert "unrecognizedAmount" not in parsed
        assert "recognizableAsset" not in parsed

        calc_headers = [
            "项目名称", "账面价值", "计税基础", "适用税率",
            "递延税资产对方科目", "递延所得税资产期末账面余额",
            "递延税负债对方科目", "递延所得税负债期末账面余额",
        ]
        calc_parsed = _parse_row(
            "N1-4",
            ("存货跌价准备", 1_000_000, 1_500_000, 0.25, "6711", 125_000, "", 0),
            calc_headers,
            seq=2,
        )
        assert calc_parsed["id"] == "calc-2"
        assert calc_parsed["taxBase"] == 1_500_000.0
        assert calc_parsed["assetCounterAccount"] == "6711"

    def test_round_trip_export_then_parse_preserves_fields(self):
        """导出行 → 解析回来字段逐一还原（Round_Trip 字段完备性）"""
        from app.routers.n1_deferred_tax_assets import (
            _FIELD_MAPS,
            _SHEET_HEADERS,
            _export_row,
            _parse_row,
        )

        data = {
            "id": "calc-1",
            "itemName": "固定资产减值准备",
            "bookValue": 900_000.0,
            "taxBase": 1_000_000.0,
            "taxRate": 0.25,
            "assetCounterAccount": "6711",
            "assetBookBalance": 20_000.0,
            "liabilityCounterAccount": "",
            "liabilityBookBalance": 0.0,
        }
        exported = _export_row("N1-4", data)
        parsed = _parse_row("N1-4", tuple(exported), _SHEET_HEADERS["N1-4"], seq=1)
        for field in _FIELD_MAPS["N1-4"].values():
            assert parsed[field] == data[field], field


# ═══════════════════════════════════════════════════════════════════════════════
# Section 10: 改造前 IE 现状基线冻结 (Task 1.2, Req 7.2, 8.1)
# ═══════════════════════════════════════════════════════════════════════════════


class TestN1IECurrentStateBaseline:
    """冻结改造前后端 N1 IE 现状基线（characterization test）。

    本组测试在改造 N1-5 之前锁定当前状态，确保：
    1. _SUPPORTED_SHEETS 当前含 N1-2/N1-4/N1-5 三张表
    2. 每张表在五张配置映射（headers/field_maps/item_id/storage_field/row_id_prefix）齐备
    3. 每张 item_id 与前端读取键一致
    4. 所有 storage_field 为 'conclusion'

    改造后 N1-5 的 item_id 将从 'N1-5-loss-rows' 变为 'N1-5-rows'。
    本测试冻结改造前状态，改造时需显式更新本组断言（记录为 basis 改变）。

    Spec: .kiro/specs/n1-loss-check-source-alignment Task 1.2
    Requirements: 7.2, 8.1
    """

    def test_supported_sheets_exact_set(self):
        """_SUPPORTED_SHEETS 当前精确包含三张表（改造前基线）"""
        from app.routers.n1_deferred_tax_assets import _SUPPORTED_SHEETS

        assert _SUPPORTED_SHEETS == {"N1-2", "N1-4", "N1-5"}

    @pytest.mark.parametrize("sheet", ["N1-2", "N1-4", "N1-5"])
    def test_five_config_maps_complete_for_each_sheet(self, sheet: str):
        """每张 sheet 的五张配置映射（headers/field_maps/item_id/storage_field/row_id_prefix）齐备"""
        from app.routers.n1_deferred_tax_assets import (
            _FIELD_MAPS,
            _SHEET_HEADERS,
            _SHEET_ITEM_ID,
            _SHEET_ROW_ID_PREFIX,
            _SHEET_STORAGE_FIELD,
            _SUPPORTED_SHEETS,
        )

        assert sheet in _SUPPORTED_SHEETS, f"{sheet} 不在 _SUPPORTED_SHEETS"
        assert sheet in _SHEET_HEADERS and len(_SHEET_HEADERS[sheet]) > 0
        assert sheet in _FIELD_MAPS and len(_FIELD_MAPS[sheet]) > 0
        assert sheet in _SHEET_ITEM_ID and _SHEET_ITEM_ID[sheet]
        assert sheet in _SHEET_STORAGE_FIELD and _SHEET_STORAGE_FIELD[sheet]
        assert sheet in _SHEET_ROW_ID_PREFIX and _SHEET_ROW_ID_PREFIX[sheet]

    def test_item_id_matches_frontend_reading_key_baseline(self):
        """item_id 与前端读取键精确一致（改造后快照）

        N1-5 已从 'N1-5-loss-rows' 改为 'N1-5-rows'（spec n1-loss-check-source-alignment Task 5.1）。
        此断言记录为 basis 改变（Req 8.4）。
        """
        from app.routers.n1_deferred_tax_assets import _SHEET_ITEM_ID

        # 改造后精确值快照（basis 改变：N1-5 item_id 'N1-5-loss-rows' → 'N1-5-rows'）
        expected = {
            "N1-2": "N1-2-detail-rows",
            "N1-4": "N1-4-calc-rows",
            "N1-5": "N1-5-rows",
        }
        assert _SHEET_ITEM_ID == expected

    def test_all_storage_fields_are_conclusion(self):
        """所有 sheet 的 storage_field 均为 'conclusion'"""
        from app.routers.n1_deferred_tax_assets import _SHEET_STORAGE_FIELD

        for sheet, field in _SHEET_STORAGE_FIELD.items():
            assert field == "conclusion", (
                f"{sheet} 的 storage_field 应为 'conclusion'，实际为 '{field}'"
            )

    def test_row_id_prefix_baseline(self):
        """行 id 前缀冻结（前端 addRow 用此前缀生成行 id）"""
        from app.routers.n1_deferred_tax_assets import _SHEET_ROW_ID_PREFIX

        expected = {
            "N1-2": "row",
            "N1-4": "calc",
            "N1-5": "loss",
        }
        assert _SHEET_ROW_ID_PREFIX == expected

    def test_headers_and_field_maps_consistent(self):
        """每张表的 headers 集合 == field_maps 键集合（防导出空列/导入漏字段）"""
        from app.routers.n1_deferred_tax_assets import _FIELD_MAPS, _SHEET_HEADERS

        for sheet in ("N1-2", "N1-4", "N1-5"):
            assert set(_SHEET_HEADERS[sheet]) == set(_FIELD_MAPS[sheet].keys()), (
                f"{sheet}: headers 与 field_maps 键不一致"
            )

    def test_n1_5_current_item_id_is_loss_rows(self):
        """N1-5 改造前 item_id 是 'N1-5-loss-rows'（非新键 'N1-5-rows'）

        这是改造的关键变更点：改造后将变为 'N1-5-rows'。
        本断言在改造落地前必须通过，改造后需显式更新。
        """
        from app.routers.n1_deferred_tax_assets import _SHEET_ITEM_ID

        # 改造已落地（spec n1-loss-check-source-alignment）：新模型键为 N1-5-rows；
        # 旧键 N1-5-loss-rows 仅由前端 n1LossMigration 只读迁移，不再作为 IE 目标键。
        assert _SHEET_ITEM_ID["N1-5"] == "N1-5-rows"


# ═══════════════════════════════════════════════════════════════════════════════
# Section 11: N1-5 IE 契约与 Round_Trip 测试 (Property 11, Task 5.2)
# ═══════════════════════════════════════════════════════════════════════════════


class TestN1_5_RoundTrip_Property11:
    """N1-5 IE Round_Trip 字段逐字对应 (Property 11).

    **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

    验证 Task 5.1 改造后的 N1-5 亏损检查表 IE 契约：
    1. headers 与 field_keys 一致（长度相等 + 集合相等）
    2. item_id === 'N1-5-rows'
    3. expiryYear 为 int（不出现 2023.0）
    4. sufficient ∈ {'yes','no',''}；来源三标记为 bool
    5. 派生列不出现在解析结果里
    6. _export_row → _parse_row 逐字段相等（Round_Trip）
    """

    # ─── 1. headers 与 field_keys 一致 ────────────────────────────────────────

    def test_headers_length_matches_field_maps_keys(self):
        """_SHEET_HEADERS['N1-5'] 长度 == _FIELD_MAPS['N1-5'] 键数"""
        from app.routers.n1_deferred_tax_assets import _FIELD_MAPS, _SHEET_HEADERS

        headers = _SHEET_HEADERS["N1-5"]
        field_map = _FIELD_MAPS["N1-5"]
        assert len(headers) == len(field_map), (
            f"headers 有 {len(headers)} 列，field_map 有 {len(field_map)} 键"
        )

    def test_headers_set_equals_field_maps_keys_set(self):
        """_SHEET_HEADERS['N1-5'] 集合 == _FIELD_MAPS['N1-5'].keys() 集合"""
        from app.routers.n1_deferred_tax_assets import _FIELD_MAPS, _SHEET_HEADERS

        headers_set = set(_SHEET_HEADERS["N1-5"])
        keys_set = set(_FIELD_MAPS["N1-5"].keys())
        assert headers_set == keys_set, (
            f"差异: headers 多 {headers_set - keys_set}, field_map 多 {keys_set - headers_set}"
        )

    # ─── 2. item_id === 'N1-5-rows' ──────────────────────────────────────────

    def test_item_id_is_n1_5_rows(self):
        """_SHEET_ITEM_ID['N1-5'] == 'N1-5-rows'（改造后新键）"""
        from app.routers.n1_deferred_tax_assets import _SHEET_ITEM_ID

        assert _SHEET_ITEM_ID["N1-5"] == "N1-5-rows"

    # ─── 3. expiryYear 为 int ─────────────────────────────────────────────────

    def test_expiry_year_parsed_as_int(self):
        """expiryYear 解析为 int（不出现 2023.0 浮点）"""
        from app.routers.n1_deferred_tax_assets import _SHEET_HEADERS, _parse_row

        headers = _SHEET_HEADERS["N1-5"]
        row = (2023, 100000, 500000, 50000, 300000, 0.25, "充足", "是",
               "√", "", "√", "wp:N1-4", "测试备注")
        parsed = _parse_row("N1-5", row, headers, seq=1)
        assert parsed["expiryYear"] == 2023
        assert isinstance(parsed["expiryYear"], int)
        # 确认不是 float
        assert not isinstance(parsed["expiryYear"], float)

    def test_expiry_year_in_int_fields(self):
        """expiryYear 在 _INT_FIELDS['N1-5'] 中注册"""
        from app.routers.n1_deferred_tax_assets import _INT_FIELDS

        assert "N1-5" in _INT_FIELDS
        assert "expiryYear" in _INT_FIELDS["N1-5"]

    # ─── 4. sufficient / 来源三标记类型 ───────────────────────────────────────

    def test_sufficient_parsed_to_yes_no_empty(self):
        """sufficient 解析为 'yes'/'no'/''"""
        from app.routers.n1_deferred_tax_assets import _SHEET_HEADERS, _parse_row

        headers = _SHEET_HEADERS["N1-5"]

        # "是" → 'yes'
        row_yes = (2024, 0, 100000, 0, 80000, 0.25, "", "是", "", "", "", "", "")
        parsed_yes = _parse_row("N1-5", row_yes, headers, seq=1)
        assert parsed_yes["sufficient"] == "yes"

        # "否" → 'no'
        row_no = (2024, 0, 100000, 0, 0, 0.25, "", "否", "", "", "", "", "")
        parsed_no = _parse_row("N1-5", row_no, headers, seq=2)
        assert parsed_no["sufficient"] == "no"

        # 空 → ''
        row_empty = (2024, 0, 100000, 0, 0, 0.25, "", "", "", "", "", "", "")
        parsed_empty = _parse_row("N1-5", row_empty, headers, seq=3)
        assert parsed_empty["sufficient"] == ""

    def test_source_flags_parsed_as_bool(self):
        """sourceOperating/sourceTemporaryDiff/sourceOther 解析为 bool"""
        from app.routers.n1_deferred_tax_assets import _SHEET_HEADERS, _parse_row

        headers = _SHEET_HEADERS["N1-5"]

        # "√" 或 "是" → True
        row = (2025, 0, 200000, 10000, 150000, 0.25, "测试", "是",
               "√", "是", "", "", "")
        parsed = _parse_row("N1-5", row, headers, seq=1)
        assert parsed["sourceOperating"] is True
        assert isinstance(parsed["sourceOperating"], bool)
        assert parsed["sourceTemporaryDiff"] is True
        assert isinstance(parsed["sourceTemporaryDiff"], bool)
        assert parsed["sourceOther"] is False
        assert isinstance(parsed["sourceOther"], bool)

    # ─── 5. 派生列不出现在解析结果里 ──────────────────────────────────────────

    def test_derived_fields_not_in_parsed_result(self):
        """auditedAmount / unrecognizedAmount / recognizableAsset 不在解析结果中"""
        from app.routers.n1_deferred_tax_assets import _SHEET_HEADERS, _parse_row

        headers = _SHEET_HEADERS["N1-5"]
        row = (2024, 50000, 300000, 20000, 200000, 0.25, "充足", "是",
               "√", "", "", "wp:N1-4", "")
        parsed = _parse_row("N1-5", row, headers, seq=1)

        # 派生列不应出现
        derived_fields = {"auditedAmount", "unrecognizedAmount", "recognizableAsset"}
        actual_keys = set(parsed.keys())
        intersection = derived_fields & actual_keys
        assert not intersection, f"派生列不应出现在解析结果中: {intersection}"

    # ─── 6. Round_Trip: _export_row → _parse_row 逐字段相等 ──────────────────

    def test_round_trip_all_fields_equal(self):
        """构造 N1-5 完整行 → _export_row → _parse_row → 逐字段相等"""
        from app.routers.n1_deferred_tax_assets import (
            _FIELD_MAPS,
            _SHEET_HEADERS,
            _export_row,
            _parse_row,
        )

        # 构造完整行数据（所有可编辑字段）
        original = {
            "id": "loss-1",
            "expiryYear": 2025,
            "priorUnrecognized": 150000.0,
            "bookAmount": 800000.0,
            "auditAdjustment": -30000.0,
            "recognizedAmount": 500000.0,
            "taxRate": 0.25,
            "basis": "预计未来五年有足够应纳税所得额",
            "sufficient": "yes",
            "sourceOperating": True,
            "sourceTemporaryDiff": False,
            "sourceOther": True,
            "indexRef": "wp:N1-4",
            "remark": "高新技术企业",
        }

        # 导出
        exported = _export_row("N1-5", original)
        assert len(exported) == len(_SHEET_HEADERS["N1-5"])

        # 解析回来
        parsed = _parse_row("N1-5", tuple(exported), _SHEET_HEADERS["N1-5"], seq=1)

        # 逐字段对比（排除 id，因 _parse_row 重新生成 id）
        for field in _FIELD_MAPS["N1-5"].values():
            assert parsed[field] == original[field], (
                f"字段 '{field}' Round_Trip 不一致: "
                f"原始={original[field]!r}, 解析={parsed[field]!r}"
            )

    def test_round_trip_with_empty_optional_fields(self):
        """Round_Trip：可选字段为空时也能正确往返"""
        from app.routers.n1_deferred_tax_assets import (
            _FIELD_MAPS,
            _SHEET_HEADERS,
            _export_row,
            _parse_row,
        )

        original = {
            "id": "loss-2",
            "expiryYear": 2026,
            "priorUnrecognized": 0.0,
            "bookAmount": 200000.0,
            "auditAdjustment": 0.0,
            "recognizedAmount": 0.0,
            "taxRate": 0.15,
            "basis": "",
            "sufficient": "",
            "sourceOperating": False,
            "sourceTemporaryDiff": False,
            "sourceOther": False,
            "indexRef": "",
            "remark": "",
        }

        exported = _export_row("N1-5", original)
        parsed = _parse_row("N1-5", tuple(exported), _SHEET_HEADERS["N1-5"], seq=2)

        for field in _FIELD_MAPS["N1-5"].values():
            assert parsed[field] == original[field], (
                f"字段 '{field}' 空值 Round_Trip 不一致: "
                f"原始={original[field]!r}, 解析={parsed[field]!r}"
            )

    def test_round_trip_expiry_year_stays_int(self):
        """Round_Trip 后 expiryYear 仍为 int（不被 safe_float 转成 2025.0）"""
        from app.routers.n1_deferred_tax_assets import (
            _SHEET_HEADERS,
            _export_row,
            _parse_row,
        )

        original = {
            "id": "loss-3",
            "expiryYear": 2028,
            "priorUnrecognized": 0.0,
            "bookAmount": 100000.0,
            "auditAdjustment": 0.0,
            "recognizedAmount": 50000.0,
            "taxRate": 0.25,
            "basis": "",
            "sufficient": "no",
            "sourceOperating": False,
            "sourceTemporaryDiff": True,
            "sourceOther": False,
            "indexRef": "",
            "remark": "",
        }

        exported = _export_row("N1-5", original)
        parsed = _parse_row("N1-5", tuple(exported), _SHEET_HEADERS["N1-5"], seq=3)

        assert parsed["expiryYear"] == 2028
        assert isinstance(parsed["expiryYear"], int)

    # ─── 7. 前端调用方回归断言 ────────────────────────────────────────────────

    def test_frontend_explicit_sheet_n1_5(self):
        """前端调用方应显式传 sheet='N1-5'（回归断言：不再落到默认 'N1-2'）

        验证 _SUPPORTED_SHEETS 包含 'N1-5' 且后端能独立校验该 sheet。
        前端 useN1ImportExport 应显式传 sheet='N1-5' 不依赖后端 Query 默认值。
        """
        from app.routers.n1_deferred_tax_assets import _SUPPORTED_SHEETS, _validate_sheet

        # N1-5 已注册
        assert "N1-5" in _SUPPORTED_SHEETS

        # 调 _validate_sheet('N1-5') 不抛异常
        _validate_sheet("N1-5")  # 不应 raise

    def test_n1_5_headers_count_is_13(self):
        """N1-5 表头恰好 13 列（源模板对齐：到期年度~备注）"""
        from app.routers.n1_deferred_tax_assets import _SHEET_HEADERS

        assert len(_SHEET_HEADERS["N1-5"]) == 13
