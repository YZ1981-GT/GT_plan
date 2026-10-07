"""
测试：附注模板变体矩阵 (note_template_variant_matrix.json)

验证 account_key 可找到四版本映射（soe/listed × standalone/consolidated）。
适配 2026-10 新 schema：顶层 key 改 accounts，条目用 account_key + variants(str)。
"""

import json
from pathlib import Path

import pytest

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "note_template_variant_matrix.json"

VARIANT_KEYS = ["soe_standalone", "soe_consolidated", "listed_standalone", "listed_consolidated"]

# 典型科目 key（smoke test 样本，不穷举）
EXPECTED_ACCOUNT_KEYS = [
    "huo_bi_zi_jin",  # 货币资金
]


@pytest.fixture
def matrix_data():
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def matrix_entries(matrix_data):
    return matrix_data.get("accounts") or matrix_data.get("matrix") or []


class TestVariantMatrixLoading:

    def test_file_exists(self):
        assert DATA_PATH.exists(), f"变体矩阵文件不存在: {DATA_PATH}"

    def test_valid_json(self, matrix_data):
        assert "version" in matrix_data
        assert isinstance(matrix_data.get("accounts") or matrix_data.get("matrix"), list)

    def test_has_version(self, matrix_data):
        assert matrix_data.get("version")

    def test_has_description(self, matrix_data):
        desc = matrix_data.get("description", "")
        assert len(desc) > 0


class TestVariantMatrixContent:

    def test_pilot_account_keys_present(self, matrix_entries):
        actual_keys = [e.get("account_key") or e.get("semantic_section_id") for e in matrix_entries]
        for expected in EXPECTED_ACCOUNT_KEYS:
            assert expected in actual_keys, f"缺少 account_key: {expected}"

    def test_each_entry_has_four_variants(self, matrix_entries):
        for entry in matrix_entries:
            key = entry.get("account_key") or entry.get("semantic_section_id", "?")
            variants = entry.get("variants", {})
            for vk in VARIANT_KEYS:
                assert vk in variants, f"{key} 缺少变体: {vk}"

    def test_section_ids_non_empty(self, matrix_entries):
        """大多数 section_id 非空；允许个别变体为空（该科目在该准则下无对应章节）。"""
        empty_count = 0
        for entry in matrix_entries:
            key = entry.get("account_key") or entry.get("semantic_section_id", "?")
            variants = entry.get("variants", {})
            for vk in VARIANT_KEYS:
                val = variants.get(vk)
                if isinstance(val, dict):
                    sid = val.get("section_id", "")
                else:
                    sid = str(val or "")
                if not sid.strip():
                    empty_count += 1
        # 大部分非空即可；如果超过 20% 为空说明数据有系统性问题
        total = len(matrix_entries) * len(VARIANT_KEYS)
        assert empty_count < total * 0.2, f"空 section_id 过多：{empty_count}/{total}"


class TestVariantLookup:

    def test_lookup_huo_bi_zi_jin(self, matrix_entries):
        """货币资金可找到四版本且国企/上市 section_id 不同。"""
        entry = next((e for e in matrix_entries if e.get("account_key") == "huo_bi_zi_jin"), None)
        assert entry is not None
        v = entry["variants"]
        soe = v["soe_standalone"] if isinstance(v["soe_standalone"], str) else v["soe_standalone"]["section_id"]
        listed = v["listed_standalone"] if isinstance(v["listed_standalone"], str) else v["listed_standalone"]["section_id"]
        assert soe != listed, "国企版和上市版应有不同 section_id"

    def test_consolidated_variants_may_have_sub_sections(self, matrix_entries):
        """合并版本存在 section_id 值（新 schema 是字符串）。"""
        entry = next((e for e in matrix_entries if e.get("account_key") == "huo_bi_zi_jin"), None)
        assert entry is not None
        consol = entry["variants"]["soe_consolidated"]
        if isinstance(consol, str):
            assert consol.strip(), "合并版 section_id 不能为空"
        else:
            assert consol.get("section_id", "").strip()
