"""Unit tests for backend.app.services.template_selector."""

from backend.app.services.template_selector import (
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

    def test_ipo_keyword(self):
        assert recommend_a16_version("IPO项目") == "A16-3"
        assert recommend_a16_version("含IPO字样") == "A16-3"

    def test_listed_keyword_chinese(self):
        assert recommend_a16_version("上市公司审计") == "A16-2"

    def test_listed_keyword_english(self):
        assert recommend_a16_version("listed company") == "A16-2"

    def test_neeq_keyword(self):
        assert recommend_a16_version("新三板挂牌企业") == "A16-5"

    def test_enterprise_bond_keyword(self):
        assert recommend_a16_version("企业债发行审计") == "A16-6"

    def test_bond_keyword(self):
        assert recommend_a16_version("债券审计") == "A16-6"

    def test_unmatched_returns_default(self):
        assert recommend_a16_version("普通企业年报审计") == "A16-1"
        assert recommend_a16_version("小微企业") == "A16-1"

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
