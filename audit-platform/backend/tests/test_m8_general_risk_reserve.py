"""
集成测试 — M8 一般风险准备 风险资产计提引擎 + 公式验证

Spec: .kiro/specs/m8-general-risk-reserve/ Task 7.2
Requirements: 3.3-3.7, 5.1-5.3

科目：4104 一般风险准备（贷方/权益类！期末=期初+贷方-借方）
金融企业专属：银行/证券/保险/信托/基金/期货/金融租赁
"""
import pytest

from app.services.m8_general_risk_reserve_service import (
    calc_risk_provision,
    calc_provision_diff,
    get_risk_provision_summary,
)


# ═══ calc_risk_provision ═════════════════════════════════════════════════════


class TestCalcRiskProvision:
    """应计金额 = 风险资产期末余额 × 计提比例（P3）"""

    def test_standard_1_5_percent(self):
        """标准1.5%计提：10亿×1.5%=1500万"""
        assert calc_risk_provision(1_000_000_000, 0.015) == 15_000_000

    def test_custom_rate(self):
        """自定义比例1%：1亿×1%=100万"""
        assert calc_risk_provision(100_000_000, 0.01) == 1_000_000

    def test_zero_risk_assets(self):
        """风险资产为0 → 应计金额=0"""
        assert calc_risk_provision(0, 0.015) == 0

    def test_zero_rate(self):
        """比例为0 → 应计金额=0"""
        assert calc_risk_provision(500_000_000, 0) == 0

    def test_none_risk_assets(self):
        """None输入安全处理为0"""
        assert calc_risk_provision(None, 0.015) == 0  # type: ignore[arg-type]

    def test_none_rate(self):
        """None比例安全处理为0"""
        assert calc_risk_provision(100_000_000, None) == 0  # type: ignore[arg-type]

    def test_small_amount(self):
        """小额风险资产"""
        assert calc_risk_provision(10_000, 0.015) == 150.0


# ═══ calc_provision_diff ══════════════════════════════════════════════════════


class TestCalcProvisionDiff:
    """计提差异 = 账面计提 − 应计金额（H=B-G）

    注意后端方向：booked - estimated
    - 正差 → 多计提（安全）
    - 负差 → 少计提（风险！）
    """

    def test_exact_match(self):
        """完全一致 → 差异=0"""
        assert calc_provision_diff(15_000_000, 15_000_000) == 0

    def test_over_provision_positive(self):
        """多计提：账面1800万 - 应计1500万 = +300万"""
        diff = calc_provision_diff(18_000_000, 15_000_000)
        assert diff == 3_000_000
        assert diff > 0  # 正差=多提=安全

    def test_under_provision_negative(self):
        """少计提：账面1200万 - 应计1500万 = -300万"""
        diff = calc_provision_diff(12_000_000, 15_000_000)
        assert diff == -3_000_000
        assert diff < 0  # 负差=少提=风险

    def test_none_booked(self):
        """None booked → 视为0"""
        assert calc_provision_diff(None, 1_000_000) == -1_000_000  # type: ignore[arg-type]

    def test_none_estimated(self):
        """None estimated → 视为0"""
        assert calc_provision_diff(5_000_000, None) == 5_000_000  # type: ignore[arg-type]


# ═══ get_risk_provision_summary ═══════════════════════════════════════════════


class TestGetRiskProvisionSummary:
    """完整风险资产计提测试：多项目 + 汇总 + 结论"""

    def test_single_item_accurate(self):
        """单项计提准确"""
        items = [{
            "name": "信贷资产",
            "risk_asset_balance": 1_000_000_000,
            "provision_rate": 0.015,
            "booked_balance": 15_000_000,
        }]
        result = get_risk_provision_summary(items=items)

        assert len(result["items"]) == 1
        item = result["items"][0]
        assert item["name"] == "信贷资产"
        assert item["risk_asset_balance"] == 1_000_000_000
        assert item["estimated"] == 15_000_000
        assert item["booked"] == 15_000_000
        assert item["diff"] == 0

        assert result["summary"]["total_diff"] == 0
        assert "一致" in result["summary"]["conclusion"]

    def test_multiple_items_mixed(self):
        """多项混合：有多提有少提"""
        items = [
            {
                "name": "信贷资产",
                "risk_asset_balance": 500_000_000,
                "provision_rate": 0.015,
                "booked_balance": 7_000_000,  # 少提50万
            },
            {
                "name": "表外信贷",
                "risk_asset_balance": 200_000_000,
                "provision_rate": 0.015,
                "booked_balance": 3_500_000,  # 多提50万
            },
            {
                "name": "债券投资",
                "risk_asset_balance": 100_000_000,
                "provision_rate": 0.01,
                "booked_balance": 1_000_000,  # 恰好
            },
        ]
        result = get_risk_provision_summary(items=items)

        assert len(result["items"]) == 3

        # 各项验证 G=E×F
        assert result["items"][0]["estimated"] == 7_500_000  # 5亿×1.5%
        assert result["items"][1]["estimated"] == 3_000_000  # 2亿×1.5%
        assert result["items"][2]["estimated"] == 1_000_000  # 1亿×1%

        # 各项差异 H=B-G
        assert result["items"][0]["diff"] == -500_000   # 少提
        assert result["items"][1]["diff"] == 500_000    # 多提
        assert result["items"][2]["diff"] == 0          # 恰好

        # 汇总
        summary = result["summary"]
        assert summary["total_risk_assets"] == 800_000_000
        assert summary["total_estimated"] == 11_500_000
        assert summary["total_booked"] == 11_500_000
        assert summary["total_diff"] == 0
        assert "一致" in summary["conclusion"]

    def test_overall_under_provision(self):
        """合计少计提 → 结论提示关注充足性"""
        items = [
            {
                "name": "信贷资产",
                "risk_asset_balance": 1_000_000_000,
                "provision_rate": 0.015,
                "booked_balance": 12_000_000,  # 少提300万
            },
        ]
        result = get_risk_provision_summary(items=items)

        assert result["summary"]["total_diff"] == -3_000_000
        assert "少计提" in result["summary"]["conclusion"]
        assert "充足性" in result["summary"]["conclusion"]

    def test_overall_over_provision(self):
        """合计多计提 → 结论提示多计提"""
        items = [
            {
                "name": "信贷资产",
                "risk_asset_balance": 1_000_000_000,
                "provision_rate": 0.015,
                "booked_balance": 18_000_000,  # 多提300万
            },
        ]
        result = get_risk_provision_summary(items=items)

        assert result["summary"]["total_diff"] == 3_000_000
        assert "多计提" in result["summary"]["conclusion"]

    def test_threshold_exceed_flag(self):
        """阈值标记：|diff|>threshold → exceed_threshold=True"""
        items = [
            {
                "name": "信贷资产",
                "risk_asset_balance": 500_000_000,
                "provision_rate": 0.015,
                "booked_balance": 5_000_000,  # 少提250万
            },
            {
                "name": "表外信贷",
                "risk_asset_balance": 100_000_000,
                "provision_rate": 0.015,
                "booked_balance": 1_500_000,  # 恰好
            },
        ]
        result = get_risk_provision_summary(items=items, threshold=100_000)

        # 信贷资产 diff=-2_500_000, |diff|>100_000 → exceed
        assert result["items"][0]["exceed_threshold"] is True
        # 表外信贷 diff=0 → not exceed
        assert result["items"][1]["exceed_threshold"] is False

    def test_empty_items(self):
        """空列表 → 差异=0, 结论一致"""
        result = get_risk_provision_summary(items=[])
        assert result["items"] == []
        assert result["summary"]["total_diff"] == 0
        assert "一致" in result["summary"]["conclusion"]

    def test_default_rate_1_5_percent(self):
        """未指定比例时默认1.5%"""
        items = [{
            "name": "测试",
            "risk_asset_balance": 100_000_000,
            # 未提供 provision_rate
            "booked_balance": 1_500_000,
        }]
        result = get_risk_provision_summary(items=items)
        # 默认1.5%: 1亿×0.015=150万
        assert result["items"][0]["estimated"] == 1_500_000
        assert result["items"][0]["diff"] == 0

    def test_none_values_safety(self):
        """None值安全处理"""
        items = [{
            "name": "空值测试",
            "risk_asset_balance": None,
            "provision_rate": None,
            "booked_balance": None,
        }]
        result = get_risk_provision_summary(items=items)
        # None → 0, 使用默认比例0.015: 0×0.015=0
        assert result["items"][0]["estimated"] == 0
        assert result["items"][0]["booked"] == 0

    def test_rounding(self):
        """金额四舍五入到2位小数"""
        items = [{
            "name": "精度测试",
            "risk_asset_balance": 333_333_333,
            "provision_rate": 0.015,
            "booked_balance": 5_000_000,
        }]
        result = get_risk_provision_summary(items=items)
        # 333333333×0.015=4999999.995 → 四舍五入5000000.0
        assert result["items"][0]["estimated"] == 5_000_000.0
        assert result["items"][0]["diff"] == 0
