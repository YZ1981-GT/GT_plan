"""Unit tests for backend.app.services.template_selector.

R4（trim-generation-plan-followup-optimizations）起按 ``project_classification`` 推荐：分类列只放质控分类码，
IPO / 上市 / 新三板来自专项场景、语义等价细分类与上市公司报表模板；不再在分类列里找自由文本关键词。
"""

from app.services.project_classification import resolve
from app.services.template_selector import (
    A16_ALL_VERSIONS,
    A16_ALWAYS_REQUIRED,
    A16_CATEGORY_MAP,
    A16_DEFAULT,
    A16_LABELS,
    get_a16_label,
    recommend_a16_version,
)


class TestRecommendA16Version:
    """recommend_a16_version 映射规则测试。"""

    def test_none_returns_default(self):
        assert recommend_a16_version(None) == "A16-1"

    def test_empty_string_returns_default(self):
        assert recommend_a16_version("") == "A16-1"

    def test_ipo_from_scenario_category_or_legacy_value(self):
        assert recommend_a16_version(resolve("C", "ipo")) == "A16-3"
        assert recommend_a16_version(resolve("A2", "normal")) == "A16-3"
        assert recommend_a16_version("IPO") == "A16-3", "V219 迁移前残留在分类列的旧场景值"

    def test_listed_from_scenario_category_or_template(self):
        assert recommend_a16_version(resolve("C", "listed")) == "A16-2"
        assert recommend_a16_version(resolve("A1", "normal")) == "A16-2"
        assert recommend_a16_version(resolve("A7", None)) == "A16-2"
        assert recommend_a16_version(resolve(None, None, "listed")) == "A16-2"

    def test_neeq_from_scenario_or_b1(self):
        assert recommend_a16_version(resolve("C", "transfer")) == "A16-5"
        assert recommend_a16_version("B1") == "A16-5"

    def test_bond_from_b2(self):
        assert recommend_a16_version("B2") == "A16-6"

    def test_ipo_takes_precedence_over_listed(self):
        assert recommend_a16_version(resolve("A1", "ipo")) == "A16-3"

    def test_free_text_is_no_longer_interpreted(self):
        for text in ("上市公司审计", "新三板挂牌企业", "企业债发行审计", "IPO项目", "普通企业年报审计"):
            assert recommend_a16_version(text) == "A16-1", text

    def test_result_always_in_all_versions(self):
        cases = [None, "", "IPO", "上市", "listed", "新三板", "企业债", "债券", "其他"]
        for bc in cases:
            result = recommend_a16_version(bc)
            assert result in A16_ALL_VERSIONS, f"{bc!r} → {result} not in ALL_VERSIONS"


class TestGetA16Label:
    """get_a16_label 标签查找测试。"""

    def test_known_code(self):
        assert get_a16_label("A16-1") == "一般财报（企业会计准则）"
        assert get_a16_label("A16-7") == "管理层关联交易声明书"

    def test_unknown_code_returns_empty(self):
        assert get_a16_label("UNKNOWN") == ""
        assert get_a16_label("A16-99") == ""


class TestConstants:
    """常量完整性测试。"""

    def test_all_versions_count(self):
        assert len(A16_ALL_VERSIONS) == 7

    def test_labels_cover_all_versions(self):
        for code in A16_ALL_VERSIONS:
            assert code in A16_LABELS, f"{code} missing from A16_LABELS"

    def test_default_in_all_versions(self):
        assert A16_DEFAULT in A16_ALL_VERSIONS

    def test_always_required_in_all_versions(self):
        for code in A16_ALWAYS_REQUIRED:
            assert code in A16_ALL_VERSIONS

    def test_category_map_values_in_all_versions(self):
        for keyword, version in A16_CATEGORY_MAP.items():
            assert version in A16_ALL_VERSIONS, f"{keyword}→{version} not in ALL_VERSIONS"
