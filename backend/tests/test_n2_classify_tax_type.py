"""
test_n2_classify_tax_type.py — _classify_tax_type 分类回归测试

spec: .kiro/specs/n2-disclosure-and-extraction-alignment/ Task 4.2
"""
import re
import textwrap
from pathlib import Path

import pytest

# ─── 提取函数体并 exec（避免相对导入依赖）────────────────────────────────────

_SRC = Path(__file__).parent.parent / "app/routers/wp_render_strategies/_n2_taxes_payable.py"
_CODE = _SRC.read_text(encoding="utf-8")

# 用正则提取 def _classify_tax_type 函数体
_FUNC_MATCH = re.search(
    r"(def _classify_tax_type\(.*?\n(?:(?:    .*|[ \t]*)\n)*)", _CODE
)
assert _FUNC_MATCH, "_classify_tax_type 函数未找到"

_ns: dict = {}
exec(_FUNC_MATCH.group(0), _ns)
_classify_tax_type = _ns["_classify_tax_type"]


# ─── 1. 13 种源模板科目名 → 对应独立 key ──────────────────────────────────────

class TestThirteenSourceTemplateNames:
    """逐一断言 13 种源模板写的科目名→对应 classifyKey"""

    @pytest.mark.parametrize(
        "name,expected_key",
        [
            ("企业所得税", "cit"),
            ("增值税", "vat"),
            ("消费税", "consumption"),
            ("资源税", "resource"),
            ("土地增值税", "lvt"),
            ("城市维护建设税", "urban"),
            ("车船牌照税", "vehicle"),
            ("房产税", "property"),
            ("城镇土地使用税", "land-use"),
            ("教育费附加", "education"),
            ("矿产资源补偿费", "mineral"),
            ("代扣代缴外国企业所得税", "wh-foreign-cit"),
            ("代扣代缴个人所得税", "wh-iit"),
        ],
    )
    def test_source_template_names(self, name: str, expected_key: str):
        assert _classify_tax_type(name) == expected_key


# ─── 2. 增值税 → vat 回归断言（曾返回 urban，P0 bug）────────────────────────

class TestVatRegression:
    """P0 回归：增值税必须返回 vat 而非 urban"""

    def test_plain_vat(self):
        assert _classify_tax_type("增值税") == "vat"

    def test_prepaid_vat(self):
        assert _classify_tax_type("未交增值税") == "vat"

    def test_output_vat(self):
        assert _classify_tax_type("应交增值税") == "vat"

    def test_vat_not_urban(self):
        """确保增值税不会误归到 urban（城建税）"""
        result = _classify_tax_type("增值税")
        assert result != "urban"


# ─── 3. 子串陷阱测试 ──────────────────────────────────────────────────────────

class TestSubstringTrap:
    """判断顺序测试：子串关系必须先于泛化匹配"""

    def test_wh_foreign_cit_before_cit(self):
        """「代扣代缴外国企业所得税」先于「企业所得税」"""
        assert _classify_tax_type("代扣代缴外国企业所得税") == "wh-foreign-cit"

    def test_cit_alone(self):
        assert _classify_tax_type("企业所得税") == "cit"

    def test_land_value_added_before_vat(self):
        """「土地增值税」先于「增值税」"""
        assert _classify_tax_type("土地增值税") == "lvt"

    def test_mineral_before_resource(self):
        """「矿产资源补偿费」先于「资源税」"""
        assert _classify_tax_type("矿产资源补偿费") == "mineral"

    def test_resource_tax(self):
        assert _classify_tax_type("资源税") == "resource"

    def test_wh_iit_before_iit(self):
        """「代扣代缴个人所得税」先于「个人所得税」"""
        assert _classify_tax_type("代扣代缴个人所得税") == "wh-iit"

    def test_iit_alone(self):
        assert _classify_tax_type("个人所得税") == "iit"

    def test_land_use_before_lvt_substring(self):
        """「城镇土地使用税」→ land-use，不被土地增值税抢"""
        assert _classify_tax_type("城镇土地使用税") == "land-use"


# ─── 4. 辅助科目名测试 ────────────────────────────────────────────────────────

class TestAuxiliaryNames:
    """tb_balance 真实可能出现的科目名称"""

    def test_unpaid_vat(self):
        """「应交税费-未交增值税」→ vat"""
        assert _classify_tax_type("应交税费-未交增值税") == "vat"

    def test_urban_full_name(self):
        """「应交税费-城市维护建设税」→ urban"""
        assert _classify_tax_type("应交税费-城市维护建设税") == "urban"

    @pytest.mark.parametrize(
        "name",
        [
            "简易计税",
            "应交税费_简易计税",
            "应交税费-简易计税",
        ],
    )
    def test_simple_vat_goes_to_vat(self, name: str):
        """🔴 「简易计税」**不含「增值税」子串**，但源模板附注提示明确要求归入增值税。

        源模板原文：「增值税，根据"应交税费-未交增值税、简易计税、转让金融商品应交增值税、
        代扣代缴增值税"科目贷方余额计算填列」。

        回归背景：实测项目 14fb8c10 的 `2221.08 应交税费_简易计税`（期末 15,233.31）
        曾落到 `other` → 增值税预填值少算 74%（只有 5,350.68 而非 20,583.99）。
        """
        assert _classify_tax_type(name) == "vat"

    @pytest.mark.parametrize(
        "name",
        [
            "转让金融商品应交增值税",
            "应交税费_转让金融商品应交增值税",
            "代扣代缴增值税",
        ],
    )
    def test_other_vat_family_goes_to_vat(self, name: str):
        """源模板增值税口径的其余两个科目（都含「增值税」子串，由通用条捕获）。"""
        assert _classify_tax_type(name) == "vat"

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("应交税费_未交增值税", "vat"),
            ("应交税费_应交城市维护建设税", "urban"),
            ("应交税费_应交教育费附加", "education"),
            ("应交税费_应交地方教育附加", "local-education"),
            ("应交税费_应交印花税", "stamp"),
            ("应交税费_应交个人所得税", "iit"),
        ],
    )
    def test_real_project_account_names(self, name: str, expected: str):
        """真实项目 14fb8c10 的 tb_balance 科目名（下划线分级形态）全部正确分类。"""
        assert _classify_tax_type(name) == expected

    def test_stamp_tax(self):
        assert _classify_tax_type("印花税") == "stamp"

    def test_none_input(self):
        assert _classify_tax_type(None) == "other"

    def test_empty_string(self):
        assert _classify_tax_type("") == "other"

    def test_local_education(self):
        """「地方教育附加」→ local-education"""
        assert _classify_tax_type("地方教育附加") == "local-education"
