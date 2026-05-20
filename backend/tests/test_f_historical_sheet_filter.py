"""F 循环历史遗留 sheet 过滤单测（spec workpaper-f-purchase-inventory F-F2）

Validates: Requirements F-F2.1, F-F2.2, F-F2.3, F-F2.4
ADR: ADR-F3 历史遗留过滤扩展策略

覆盖：
1. 4 种新历史遗留模式被正确过滤
2. D/E 循环原有过滤行为不受影响（回归安全）
3. 正常业务 sheet 名不被误过滤
"""
from __future__ import annotations

import pytest

from app.services.wp_template_init_service import _should_skip_historical_sheet


# -----------------------------------------------------------------------------
# F-F2: 4 种新历史遗留模式
# -----------------------------------------------------------------------------


class TestFCycleHistoricalPatterns:
    """F 循环 4 种新模式应被过滤"""

    @pytest.mark.parametrize(
        "name",
        [
            "预付账款实质性程序表G1A-修订前",   # F1 文件
            "存货计价测试程序G2-8-删除",        # F2-38 文件
            "产品年度成本比较G2-8-4-移至分析类",  # F2-38 文件
            "产品月度成本比较G2-8-5（删除 在舞弊应对单耗分析中）",  # F2-38
            "产品同行业成本比较G2-8-7-移至舞弊应对单耗分析中",  # F2-38
            "同行业存货跌价计提情况G2-9-3-删除",  # F2-47
            "采购定价公允性测算（询价函）G2-10-1-删除",  # F2-52
            "采购定价公允性测算（市场价）G2-10-2-删除",  # F2-52
            "识别未披露的关联方G2-10-3-删除",  # F2-52
            "函证差异检查表（示例）",         # F0
            "合同履约成本测试（示例）",        # F2-55
            "访谈记录与核对示例",             # F2-61
        ],
    )
    def test_f_cycle_historical_skipped(self, name: str):
        """F 循环 12 个真实历史遗留 sheet 名应被过滤"""
        assert _should_skip_historical_sheet(name) is True, (
            f"sheet '{name}' 应被识别为历史遗留但当前未过滤"
        )


# -----------------------------------------------------------------------------
# D/E 循环回归：原有过滤行为
# -----------------------------------------------------------------------------


class TestDECycleRegression:
    """确保 D/E 循环的"修订前/(原)"过滤行为不受影响"""

    @pytest.mark.parametrize(
        "name",
        [
            "主营业务收入审计程序表 D4A（修订前）",
            "应收账款审定表D2-1（修订前）",
            "D7A（原）",
            "D8A(原)",
            "应收账款审定表（原）",
        ],
    )
    def test_d_cycle_historical_still_skipped(self, name: str):
        """D 循环原有历史遗留 sheet 仍然被过滤"""
        assert _should_skip_historical_sheet(name) is True


# -----------------------------------------------------------------------------
# 正常业务 sheet 不被误过滤
# -----------------------------------------------------------------------------


class TestNormalBusinessSheets:
    """正常业务 sheet 名不应被误过滤"""

    @pytest.mark.parametrize(
        "name",
        [
            "底稿目录",
            "GT_Custom",
            "存货实质性程序表F2A",
            "存货审定表F2-1",
            "审定表D2-1",
            "应收账款实质性程序表D2A",
            "明细汇总表F2-2",
            "一、原材料明细表F2-3",
            "存货监盘程序表F2-21A",
            "监盘计划F2-22",
            "审定表D7-1",
            "应收款项融资审定表",
            "客户访谈记录D4-30",  # D 循环访谈，不应误判为示例
            "存货采购入库检查表F2-33-新增",  # 含"新增"不是"删除/移至"
        ],
    )
    def test_normal_business_not_skipped(self, name: str):
        """正常业务 sheet 名不应被过滤"""
        assert _should_skip_historical_sheet(name) is False


# -----------------------------------------------------------------------------
# 边界情况
# -----------------------------------------------------------------------------


class TestEdgeCases:
    def test_none_input(self):
        assert _should_skip_historical_sheet(None) is False  # type: ignore

    def test_empty_string(self):
        assert _should_skip_historical_sheet("") is False

    def test_g_without_digit_not_skipped(self):
        """单纯 G 字符不带数字编号不应被过滤"""
        assert _should_skip_historical_sheet("Google 删除按钮") is False
        assert _should_skip_historical_sheet("GT_Custom") is False

    def test_digit_with_keyword_but_no_g_not_skipped(self):
        """有数字但没有 G 前缀不应被过滤"""
        assert _should_skip_historical_sheet("D2-8 删除测试") is False
