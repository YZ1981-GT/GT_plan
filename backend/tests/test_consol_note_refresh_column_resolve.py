"""测试 _resolve_value_columns / _classify_header 列定位三层策略。

spec: consol-note-refresh-multi-header-fix

验收矩阵：
  1. 简单扁平表头（无分组）→ 第一个期末列 + 第一个期初列
  2. 多级表头（multi_header 2 行）→ multi_header[0] 的首个期末/期初分组列
  3. 多级表头（multi_header 3 行）→ 同上
  4. _column_groups 存在时 → 优先按组名定位
  5. 变动表排除（"本期增加"不是期末值列）
  6. 斜杠路径表头 → 不被"账面余额"误命中
  7. 空表头 / 无关键词 → audited=[], opening=[]
  8. "上年年末余额"命中 opening（改进 2）
  9. _classify_header 逐列分类（审计校验用）
"""

import pytest

from app.routers.consol_note_sections import (
    _classify_header,
    _is_ending_label,
    _is_opening_label,
    _resolve_value_columns,
)


# ─── 辅助函数单元测试 ────────────────────────────────────────────────────────


class TestIsEndingLabel:
    """_is_ending_label 含变动排除。"""

    def test_ending_keywords(self):
        assert _is_ending_label("期末余额") is True
        assert _is_ending_label("期末数") is True
        assert _is_ending_label("本期数") is True

    def test_change_keywords_excluded(self):
        """变动类关键词排除：含"本期"但也含"增加"→ False。"""
        assert _is_ending_label("本期增加") is False
        assert _is_ending_label("本期减少") is False
        assert _is_ending_label("本期计提") is False
        assert _is_ending_label("本期转回") is False
        assert _is_ending_label("本期转销") is False
        assert _is_ending_label("本期核销") is False
        assert _is_ending_label("本期摊销") is False
        assert _is_ending_label("本期偿还") is False
        assert _is_ending_label("本期发行") is False
        assert _is_ending_label("本期增减变动") is False

    def test_ending_balance_not_excluded(self):
        """"期末余额"不含排除词 → True。"""
        assert _is_ending_label("期末余额") is True
        assert _is_ending_label("期末公允价值") is True
        assert _is_ending_label("期末账面价值") is True

    def test_no_keyword(self):
        assert _is_ending_label("金额") is False
        assert _is_ending_label("比例(%)") is False


class TestIsOpeningLabel:
    """_is_opening_label 含"上年"关键词。"""

    def test_standard_keywords(self):
        assert _is_opening_label("期初余额") is True
        assert _is_opening_label("年初余额") is True
        assert _is_opening_label("上期数") is True

    def test_prior_year_keyword(self):
        """改进 2：上年年末余额命中 opening。"""
        assert _is_opening_label("上年年末余额") is True
        assert _is_opening_label("上年年末金额") is True

    def test_no_keyword(self):
        assert _is_opening_label("金额") is False


class TestClassifyHeader:
    """_classify_header 逐列分类。"""

    def test_ending_header(self):
        assert _classify_header("期末余额") == "audited"
        assert _classify_header("期末数") == "audited"

    def test_opening_header(self):
        assert _classify_header("期初余额") == "opening"
        assert _classify_header("年初余额") == "opening"
        assert _classify_header("上年年末余额") == "opening"

    def test_change_header_excluded(self):
        """变动列不归为 audited 也不归为 opening。"""
        assert _classify_header("本期增加") is None
        assert _classify_header("本期减少") is None

    def test_slash_path_uses_root(self):
        """斜杠路径用首段判断。"""
        assert _classify_header("期末数/账面余额/金额") == "audited"
        assert _classify_header("期初数/坏账准备") == "opening"
        # 期初数开头但内含"账面余额"→ 首段是"期初数" → opening
        assert _classify_header("期初数/账面余额") == "opening"

    def test_empty_and_none(self):
        assert _classify_header("") is None
        assert _classify_header("  ") is None

    def test_fullwidth_space_stripped(self):
        """全角空格被清理。"""
        assert _classify_header("期末\u3000余额") == "audited"


# ─── 策略 3：扁平表头 ───────────────────────────────────────────────────────


class TestFlatHeaders:
    """无 multi_header / 无 _column_groups 的简单表。"""

    def test_simple_two_column(self):
        """货币资金表：["项目", "期末余额", "期初余额"]"""
        tpl = {
            "headers": ["项  目", "期末余额", "期初余额"],
        }
        result = _resolve_value_columns(tpl)
        assert result["audited"] == [1]
        assert result["opening"] == [2]

    def test_change_table_skips_change_cols(self):
        """变动表：变动列被排除，只有"期末余额"命中 audited。"""
        tpl = {
            "headers": ["项  目", "期初余额", "本期增加", "本期减少", "期末余额"],
        }
        result = _resolve_value_columns(tpl)
        # "本期增加"和"本期减少"被 _CHANGE_EXCLUDE 排除
        # "期末余额"是第一个（也是唯一一个）命中 → col 4
        assert result["audited"] == [4], "变动列排除后只有期末余额命中"
        assert result["opening"] == [1]

    def test_no_keyword_headers(self):
        """无关键词表头 → 空列表。"""
        tpl = {
            "headers": ["类别", "金额", "比例(%)"],
        }
        result = _resolve_value_columns(tpl)
        assert result["audited"] == []
        assert result["opening"] == []

    def test_empty_headers(self):
        """空表头 → 空列表。"""
        tpl = {"headers": []}
        result = _resolve_value_columns(tpl)
        assert result["audited"] == []
        assert result["opening"] == []

    def test_single_ending_column(self):
        """只有一个期末列，无期初列。"""
        tpl = {
            "headers": ["项目", "期末数"],
        }
        result = _resolve_value_columns(tpl)
        assert result["audited"] == [1]
        assert result["opening"] == []


# ─── 策略 3（斜杠路径降级） ──────────────────────────────────────────────────


class TestSlashPathFallback:
    """有斜杠路径但无 multi_header / 无 _column_groups 的场景。"""

    def test_slash_path_uses_root_segment(self):
        """斜杠路径表头：首段"期末数"命中期末，"期初数"命中期初。"""
        tpl = {
            "headers": [
                "类  别",
                "期末数/账面余额/金额",
                "期末数/账面余额/比例(%)",
                "期末数/坏账准备/金额",
                "期末数/坏账准备/预期信用损失率(%)",
                "期末数/账面价值",
                "期初数/账面余额/金额",
                "期初数/账面余额/比例(%)",
                "期初数/坏账准备/金额",
                "期初数/坏账准备/预期信用损失率(%)",
                "期初数/账面价值",
            ],
        }
        result = _resolve_value_columns(tpl)
        assert result["audited"] == [1]
        assert result["opening"] == [6]

    def test_slash_path_not_mismatched_by_inner_keyword(self):
        """旧逻辑缺陷再现：`"期初数/账面余额"` 不该被"账面余额"命中为 audited。"""
        tpl = {
            "headers": [
                "账  龄",
                "期末数/账面余额",
                "期初数/坏账准备",
                "期初数/账面余额",
                "期初数/坏账准备",
            ],
        }
        result = _resolve_value_columns(tpl)
        assert result["audited"] == [1]
        assert result["opening"] == [2]

    def test_br_in_header(self):
        """含 <br/> 的表头："期末<br/>余额"首段"期末<br"含"期末"但也可能被切。

        实际行为：h_clean="期末<br/>余额", root="期末<br"，"期末" in "期末<br" = True，
        但不含变动排除词 → audited。
        "本期<br/>增加" root="本期<br"，含"本期"但"增加"在第二段 → 不被排除。
        然而 root 只含"本期<br"而 _CHANGE_EXCLUDE 的"增加"不在 root 中…
        所以 _is_ending_label 在 root 上只看到"本期"且排除词在 root 中不命中 → True。
        """
        tpl = {
            "headers": ["项目", "期初余额", "本期<br/>增加", "期末<br/>余额"],
        }
        result = _resolve_value_columns(tpl)
        # "本期<br/>增加" root="本期<br" → 含"本期"、不含"增加" → 命中 audited
        # 但因为 [:1] 只取第一个，所以 audited=[2]
        assert result["audited"] == [2]
        assert result["opening"] == [1]


# ─── 策略 2：multi_header ────────────────────────────────────────────────────


class TestMultiHeader:
    """multi_header 非 null 时，按顶行分组名定位。"""

    def test_two_level_receivable_aging(self):
        """应收账款账龄表（soe 五-5-1）：2 行 multi_header。"""
        tpl = {
            "headers": [
                "账  龄",
                "期末数/账面余额",
                "期初数/坏账准备",
                "期初数/账面余额",
                "期初数/坏账准备",
            ],
            "multi_header": [
                ["账  龄", "期末数", "期初数", "", ""],
                ["", "账面余额", "坏账准备", "账面余额", "坏账准备"],
            ],
        }
        result = _resolve_value_columns(tpl)
        assert result["audited"] == [1]
        assert result["opening"] == [2]

    def test_three_level_receivable_classification(self):
        """应收账款分类表（soe 五-5-2）：3 行 multi_header。"""
        tpl = {
            "headers": [
                "类  别",
                "期末数/账面余额/金额",
                "期末数/账面余额/比例(%)",
                "期末数/坏账准备/金额",
                "期末数/坏账准备/预期信用损失率(%)",
                "期末数/账面价值",
                "期初数/账面余额/金额",
                "期初数/账面余额/比例(%)",
                "期初数/坏账准备/金额",
                "期初数/坏账准备/预期信用损失率(%)",
                "期初数/账面价值",
            ],
            "multi_header": [
                ["类  别", "期末数", "", "", "", "", "期初数", "", "", "", ""],
                ["", "账面余额", "", "坏账准备", "", "账面价值", "账面余额", "", "坏账准备", "", "账面价值"],
                ["", "金额", "比例(%)", "金额", "预期信用损失率(%)", "", "金额", "比例(%)", "金额", "预期信用损失率(%)", ""],
            ],
        }
        result = _resolve_value_columns(tpl)
        assert result["audited"] == [1]
        assert result["opening"] == [6]

    def test_multi_header_with_label_only(self):
        """multi_header 但顶行含"期初余额"。"""
        tpl = {
            "headers": ["补助项目", "期初余额", "本期新增"],
            "multi_header": [
                ["补助项目", "期初余额", "本期新增"],
                ["", "", ""],
            ],
        }
        result = _resolve_value_columns(tpl)
        assert result["opening"] == [1]

    def test_multi_header_prior_year(self):
        """上市模板"上年年末余额"在顶行命中 opening（改进 2）。"""
        tpl = {
            "headers": [
                "列1",
                "期末余额/账面余额",
                "上年年末余额/坏账准备",
                "上年年末余额/预期信用损失率(%)",
                "上年年末余额/账面余额",
                "上年年末余额/坏账准备",
                "上年年末余额/预期信用损失率(%)",
            ],
            "multi_header": [
                ["", "期末余额", "上年年末余额", "", "", "", ""],
                ["", "账面余额", "坏账准备", "预期信用损失率(%)", "账面余额", "坏账准备", "预期信用损失率(%)"],
            ],
        }
        result = _resolve_value_columns(tpl)
        assert result["audited"] == [1]
        assert result["opening"] == [2], "上年年末余额含'上年' → opening"


# ─── 策略 1：_column_groups（P2 就绪后） ─────────────────────────────────────


class TestColumnGroups:
    """_column_groups 存在时优先使用。"""

    def test_column_groups_precedence(self):
        """即使 multi_header 和 headers 都有关键词，_column_groups 优先。"""
        tpl = {
            "headers": ["项目", "期末余额", "期初余额", "其他"],
            "multi_header": [
                ["项目", "期末数", "期初数", "其他"],
                ["", "", "", ""],
            ],
            "_column_groups": [
                {"group": "期末数", "start": 1, "span": 1},
                {"group": "期初数", "start": 2, "span": 1},
            ],
        }
        result = _resolve_value_columns(tpl)
        assert result["audited"] == [1]
        assert result["opening"] == [2]

    def test_column_groups_wide_span(self):
        tpl = {
            "headers": ["项目", "期末数/金额", "期末数/比例", "期初数/金额", "期初数/比例"],
            "_column_groups": [
                {"group": "期末数", "start": 1, "span": 2},
                {"group": "期初数", "start": 3, "span": 2},
            ],
        }
        result = _resolve_value_columns(tpl)
        assert result["audited"] == [1]
        assert result["opening"] == [3]

    def test_column_groups_no_match(self):
        tpl = {
            "headers": ["项目", "累计金额"],
            "_column_groups": [
                {"group": "增减变动", "start": 1, "span": 1},
            ],
        }
        result = _resolve_value_columns(tpl)
        assert result["audited"] == []
        assert result["opening"] == []

    def test_column_groups_empty_list(self):
        tpl = {
            "headers": ["项目", "期末余额", "期初余额"],
            "_column_groups": [],
        }
        result = _resolve_value_columns(tpl)
        assert result["audited"] == [1]
        assert result["opening"] == [2]


# ─── 端到端场景：真实模板结构 ────────────────────────────────────────────────


class TestRealTemplateStructures:
    """用真实模板结构验证端到端行为。"""

    def test_soe_currency_funds(self):
        """国企五-1-1 货币资金（最简单的两列表）。"""
        tpl = {
            "headers": ["项  目", "期末余额", "期初余额"],
            "multi_header": None,
        }
        result = _resolve_value_columns(tpl)
        assert result == {"audited": [1], "opening": [2]}

    def test_soe_fixed_assets_change(self):
        """国企五-23-2 固定资产情况（变动表 4 列含"本期/期末"）。

        改进 1 后变动列被排除，只有"期末余额"命中。"""
        tpl = {
            "headers": ["类  别", "期初余额", "本期增加", "本期减少", "期末余额"],
            "multi_header": None,
        }
        result = _resolve_value_columns(tpl)
        assert result["audited"] == [4], "变动排除后期末余额在 col 4"
        assert result["opening"] == [1]

    def test_soe_receivable_aging_multi_header(self):
        """国企五-5-1 应收账款按账龄披露。"""
        tpl = {
            "headers": [
                "账  龄",
                "期末数/账面余额",
                "期初数/坏账准备",
                "期初数/账面余额",
                "期初数/坏账准备",
            ],
            "multi_header": [
                ["账  龄", "期末数", "期初数", "", ""],
                ["", "账面余额", "坏账准备", "账面余额", "坏账准备"],
            ],
        }
        result = _resolve_value_columns(tpl)
        assert result["audited"] == [1]
        assert result["opening"] == [2]

    def test_listed_receivable_combination_prior_year(self):
        """上市五-5-6 组合计提项目：改进 2 后"上年年末余额"命中 opening。"""
        tpl = {
            "headers": [
                "列1",
                "期末余额/账面余额",
                "上年年末余额/坏账准备",
                "上年年末余额/预期信用损失率(%)",
                "上年年末余额/账面余额",
                "上年年末余额/坏账准备",
                "上年年末余额/预期信用损失率(%)",
            ],
            "multi_header": [
                ["", "期末余额", "上年年末余额", "", "", "", ""],
                ["", "账面余额", "坏账准备", "预期信用损失率(%)", "账面余额", "坏账准备", "预期信用损失率(%)"],
            ],
        }
        result = _resolve_value_columns(tpl)
        assert result["audited"] == [1]
        assert result["opening"] == [2], "上年年末余额含'上年' → opening"

    def test_soe_deferred_revenue_change(self):
        """国企五-57-1 递延收益（典型变动表）：
        ["项目", "期初余额", "本期增加", "本期减少", "期末余额"]
        改进 1 后 audited 精确到"期末余额"列。"""
        tpl = {
            "headers": ["项  目", "期初余额", "本期增加", "本期减少", "期末余额"],
            "multi_header": None,
        }
        result = _resolve_value_columns(tpl)
        assert result["audited"] == [4]
        assert result["opening"] == [1]
