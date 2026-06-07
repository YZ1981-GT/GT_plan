"""
测试：附注模板变体矩阵 (note_template_variant_matrix.json)

验证同一 semantic_section_id 可找到四版本映射
Requirements: 8.1, 8.2, 8.3, 8.4
"""

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ─── Fixtures ──────────────────────────────────────────────────────────────

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "note_template_variant_matrix.json"

EXPECTED_SEMANTIC_IDS = [
    "accounting_policies",
    "accounts_receivable",
    "fixed_assets",
    "cash_and_bank",
    "related_party_transactions",
    "related_party_receivables_payables",
]

VARIANT_KEYS = ["soe_standalone", "soe_consolidated", "listed_standalone", "listed_consolidated"]


@pytest.fixture
def matrix_data():
    """加载变体矩阵 JSON"""
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def matrix_entries(matrix_data):
    """返回 matrix 列表"""
    return matrix_data["matrix"]


# ─── Unit Tests ────────────────────────────────────────────────────────────


class TestVariantMatrixLoading:
    """测试 JSON 加载与基本结构"""

    def test_file_exists(self):
        assert DATA_PATH.exists(), f"变体矩阵文件不存在: {DATA_PATH}"

    def test_valid_json(self, matrix_data):
        assert "version" in matrix_data
        assert "matrix" in matrix_data
        assert isinstance(matrix_data["matrix"], list)

    def test_has_version(self, matrix_data):
        assert matrix_data["version"] == "1.0.0"

    def test_has_description(self, matrix_data):
        assert "description" in matrix_data
        assert len(matrix_data["description"]) > 0


class TestVariantMatrixContent:
    """测试变体矩阵内容完整性"""

    def test_all_pilot_sections_present(self, matrix_entries):
        """所有试点 semantic_section_id 都必须在矩阵中"""
        actual_ids = [entry["semantic_section_id"] for entry in matrix_entries]
        for expected_id in EXPECTED_SEMANTIC_IDS:
            assert expected_id in actual_ids, f"缺少 semantic_section_id: {expected_id}"

    def test_each_entry_has_four_variants(self, matrix_entries):
        """每个条目必须有四个变体版本"""
        for entry in matrix_entries:
            variants = entry["variants"]
            for key in VARIANT_KEYS:
                assert key in variants, (
                    f"{entry['semantic_section_id']} 缺少变体: {key}"
                )

    def test_each_variant_has_required_fields(self, matrix_entries):
        """每个变体必须有 section_id, number, title, scope"""
        required_fields = ["section_id", "number", "title", "scope"]
        for entry in matrix_entries:
            for vk in VARIANT_KEYS:
                variant = entry["variants"][vk]
                for field in required_fields:
                    assert field in variant, (
                        f"{entry['semantic_section_id']}.{vk} 缺少字段: {field}"
                    )

    def test_section_ids_non_empty(self, matrix_entries):
        """所有 section_id 必须非空"""
        for entry in matrix_entries:
            for vk in VARIANT_KEYS:
                section_id = entry["variants"][vk]["section_id"]
                assert section_id and len(section_id.strip()) > 0, (
                    f"{entry['semantic_section_id']}.{vk}.section_id 为空"
                )


class TestVariantLookup:
    """测试按 semantic_section_id 查找"""

    def test_lookup_accounts_receivable(self, matrix_entries):
        """应收账款可找到四版本"""
        entry = next(
            (e for e in matrix_entries if e["semantic_section_id"] == "accounts_receivable"),
            None,
        )
        assert entry is not None
        variants = entry["variants"]
        # 国企版和上市版使用不同的 section_id
        assert "chapter-08" in variants["soe_standalone"]["section_id"]
        assert "chapter-05" in variants["listed_standalone"]["section_id"]

    def test_lookup_accounting_policies(self, matrix_entries):
        """会计政策可找到四版本，国企/上市 section_id 不同"""
        entry = next(
            (e for e in matrix_entries if e["semantic_section_id"] == "accounting_policies"),
            None,
        )
        assert entry is not None
        variants = entry["variants"]
        assert "chapter-04" in variants["soe_standalone"]["section_id"]
        assert "chapter-03" in variants["listed_standalone"]["section_id"]

    def test_lookup_related_party_same_section_id(self, matrix_entries):
        """关联方章节四版本使用相同 section_id"""
        entry = next(
            (e for e in matrix_entries if e["semantic_section_id"] == "related_party_transactions"),
            None,
        )
        assert entry is not None
        variants = entry["variants"]
        ids = {variants[vk]["section_id"] for vk in VARIANT_KEYS}
        assert len(ids) == 1, "关联方交易章节四版本应使用相同 section_id"

    def test_consolidated_variants_may_have_sub_sections(self, matrix_entries):
        """合并版本可能含 consol_sub_sections"""
        entry = next(
            (e for e in matrix_entries if e["semantic_section_id"] == "cash_and_bank"),
            None,
        )
        assert entry is not None
        consol = entry["variants"]["soe_consolidated"]
        assert "consol_sub_sections" in consol
        assert len(consol["consol_sub_sections"]) > 0


# ─── Property-Based Test ───────────────────────────────────────────────────


class TestVariantMatrixPBT:
    """
    PBT: 验证所有条目的 section_id 非空

    **Validates: Requirements 8.1**
    """

    @settings(max_examples=5)
    @given(data=st.data())
    def test_all_entries_have_non_empty_section_id(self, data):
        """所有条目在每个变体中都有非空 section_id"""
        with open(DATA_PATH, encoding="utf-8") as f:
            matrix_data = json.load(f)

        entries = matrix_data["matrix"]
        # 从所有条目中随机选一个
        entry_idx = data.draw(st.integers(min_value=0, max_value=len(entries) - 1))
        entry = entries[entry_idx]

        # 从四个变体中随机选一个
        variant_key = data.draw(st.sampled_from(VARIANT_KEYS))
        variant = entry["variants"][variant_key]

        assert "section_id" in variant
        assert isinstance(variant["section_id"], str)
        assert len(variant["section_id"].strip()) > 0, (
            f"{entry['semantic_section_id']}.{variant_key}.section_id 不能为空"
        )
