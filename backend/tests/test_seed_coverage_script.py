"""Tests for check_account_to_report_line_seed_coverage script.

Validates:
- 7.2 校验四套 Seed_Dimension 均存在且各自完整
- 7.3 校验 standard_account_code 重复、report_line_code 格式、report_type 合法性
- 7.4 以平台标准 AccountChart seed 为权威全集输出未覆盖科目清单
- 7.7 生成 coverage baseline
- 7.8 脚本能发现缺失、重复和非法行次

Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 5.7
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.scripts.check.check_account_to_report_line_seed_coverage import (
    REPORT_LINE_CODE_PATTERN,
    REQUIRED_DIMENSIONS,
    VALID_REPORT_TYPES,
    check_dimensions_exist,
    check_single_dimension,
    find_duplicate_account_codes,
    find_invalid_report_line_codes,
    find_invalid_report_types,
    find_uncovered_accounts,
    generate_baseline,
    run_full_check,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_seed_data() -> dict:
    """完整有效的 seed 数据。"""
    entry = {
        "standard_account_code": "1001",
        "report_type": "balance_sheet",
        "report_line_code": "BS-002",
        "report_line_name": "货币资金",
    }
    return {
        "mappings": {dim: [entry] for dim in REQUIRED_DIMENSIONS}
    }


@pytest.fixture
def standard_accounts() -> list[dict]:
    """标准科目全集 fixture。"""
    return [
        {"code": "1001", "name": "库存现金"},
        {"code": "1002", "name": "银行存款"},
        {"code": "1012", "name": "其他货币资金"},
    ]


@pytest.fixture
def tmp_seed_file(valid_seed_data: dict) -> Path:
    """写入临时 seed 文件。"""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(valid_seed_data, f, ensure_ascii=False)
    f.close()
    return Path(f.name)


@pytest.fixture
def tmp_chart_file(standard_accounts: list[dict]) -> Path:
    """写入临时标准科目文件。"""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump({"standard": "enterprise", "name": "test", "accounts": standard_accounts}, f)
    f.close()
    return Path(f.name)


# ---------------------------------------------------------------------------
# Unit tests: 7.2 四套维度存在性
# ---------------------------------------------------------------------------


class TestDimensionsExist:
    """7.2: 校验四套 Seed_Dimension 均存在且各自完整。"""

    def test_all_dimensions_present(self, valid_seed_data: dict):
        missing = check_dimensions_exist(valid_seed_data)
        assert missing == []

    def test_missing_one_dimension(self):
        data = {"mappings": {"soe_standalone": [], "soe_consolidated": [], "listed_standalone": []}}
        missing = check_dimensions_exist(data)
        assert "listed_consolidated" in missing

    def test_empty_mappings_reports_all_missing(self):
        data = {"mappings": {}}
        missing = check_dimensions_exist(data)
        assert set(missing) == set(REQUIRED_DIMENSIONS)


# ---------------------------------------------------------------------------
# Unit tests: 7.3 重复、格式、合法性
# ---------------------------------------------------------------------------


class TestDuplicateAccountCodes:
    """7.3: 找出 standard_account_code 重复。"""

    def test_no_duplicates(self):
        entries = [
            {"standard_account_code": "1001"},
            {"standard_account_code": "1002"},
        ]
        assert find_duplicate_account_codes(entries) == []

    def test_finds_duplicates(self):
        entries = [
            {"standard_account_code": "1001"},
            {"standard_account_code": "1001"},
            {"standard_account_code": "1002"},
        ]
        dupes = find_duplicate_account_codes(entries)
        assert "1001" in dupes
        assert "1002" not in dupes


class TestInvalidReportLineCodes:
    """7.3: 找出不合法的 report_line_code。"""

    def test_valid_codes_pass(self):
        entries = [
            {"report_line_code": "BS-002"},
            {"report_line_code": "PL-001"},
            {"report_line_code": "CF-010"},
        ]
        assert find_invalid_report_line_codes(entries) == []

    def test_invalid_codes_detected(self):
        entries = [
            {"report_line_code": "INVALID"},
            {"report_line_code": "BS002"},
            {"report_line_code": "BS-2"},
        ]
        invalid = find_invalid_report_line_codes(entries)
        assert len(invalid) == 3

    def test_empty_code_ignored(self):
        entries = [{"report_line_code": ""}]
        assert find_invalid_report_line_codes(entries) == []


class TestInvalidReportTypes:
    """7.3: 找出非法 report_type。"""

    def test_valid_types_pass(self):
        entries = [
            {"report_type": "balance_sheet"},
            {"report_type": "profit_loss"},
            {"report_type": "cash_flow"},
        ]
        assert find_invalid_report_types(entries) == []

    def test_invalid_type_detected(self):
        entries = [{"report_type": "unknown_type"}]
        invalid = find_invalid_report_types(entries)
        assert "unknown_type" in invalid


# ---------------------------------------------------------------------------
# Unit tests: 7.4 未覆盖科目
# ---------------------------------------------------------------------------


class TestUncoveredAccounts:
    """7.4: 输出未覆盖科目。"""

    def test_all_covered(self):
        entries = [{"standard_account_code": "1001"}, {"standard_account_code": "1002"}]
        standard = [{"code": "1001", "name": "库存现金"}, {"code": "1002", "name": "银行存款"}]
        assert find_uncovered_accounts(entries, standard) == []

    def test_finds_uncovered(self, standard_accounts: list[dict]):
        entries = [{"standard_account_code": "1001"}]
        uncovered = find_uncovered_accounts(entries, standard_accounts)
        codes = [a["code"] for a in uncovered]
        assert "1002" in codes
        assert "1012" in codes
        assert "1001" not in codes


# ---------------------------------------------------------------------------
# Unit tests: 7.7 baseline 生成
# ---------------------------------------------------------------------------


class TestBaseline:
    """7.7: 生成 coverage baseline。"""

    def test_baseline_structure(self):
        check_result = {
            "dimensions": {
                "soe_standalone": {
                    "uncovered_accounts": [{"code": "2701", "name": "长期应付款"}],
                    "duplicate_account_codes": ["1001"],
                    "entry_count": 145,
                }
            }
        }
        baseline = generate_baseline(check_result)
        assert "generated_at" in baseline
        assert "dimensions" in baseline
        dim = baseline["dimensions"]["soe_standalone"]
        assert dim["known_missing_accounts"] == ["2701"]
        assert dim["known_duplicates"] == ["1001"]
        assert dim["entry_count"] == 145


# ---------------------------------------------------------------------------
# Integration: run_full_check
# ---------------------------------------------------------------------------


class TestRunFullCheck:
    """7.8: 脚本能发现缺失、重复和非法行次。"""

    def test_full_check_on_valid_data(self, tmp_seed_file: Path, tmp_chart_file: Path):
        result = run_full_check(tmp_seed_file, tmp_chart_file)
        assert result["missing_dimensions"] == []
        # 1001 is covered, 1002 and 1012 are not
        for dim_result in result["dimensions"].values():
            uncovered_codes = [a["code"] for a in dim_result["uncovered_accounts"]]
            assert "1002" in uncovered_codes

    def test_full_check_detects_duplicates(self, tmp_chart_file: Path):
        seed = {
            "mappings": {
                dim: [
                    {"standard_account_code": "1001", "report_type": "balance_sheet", "report_line_code": "BS-002"},
                    {"standard_account_code": "1001", "report_type": "balance_sheet", "report_line_code": "BS-003"},
                ]
                for dim in REQUIRED_DIMENSIONS
            }
        }
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(seed, f, ensure_ascii=False)
        f.close()
        result = run_full_check(Path(f.name), tmp_chart_file)
        for dim_result in result["dimensions"].values():
            assert "1001" in dim_result["duplicate_account_codes"]


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------


valid_report_line_code_st = st.from_regex(r"(BS|PL|CF)-\d{3}", fullmatch=True)
invalid_report_line_code_st = st.from_regex(r"[A-Z]{2,4}\d{2,4}", fullmatch=True).filter(
    lambda x: not REPORT_LINE_CODE_PATTERN.match(x)
)


class TestSeedCoverageProperties:
    """PBT: seed 覆盖率脚本不变量。"""

    @settings(max_examples=5)
    @given(codes=st.lists(st.from_regex(r"[1-9][0-9]{3}", fullmatch=True), min_size=0, max_size=10))
    def test_no_false_duplicates(self, codes: list[str]):
        """**Validates: Requirements 5.3**

        Property: 无重复输入时不报告重复。
        """
        unique_entries = [{"standard_account_code": c} for c in set(codes)]
        dupes = find_duplicate_account_codes(unique_entries)
        assert dupes == []

    @settings(max_examples=5)
    @given(code=valid_report_line_code_st)
    def test_valid_line_codes_never_rejected(self, code: str):
        """**Validates: Requirements 5.3**

        Property: 合法 report_line_code 永远不被标为非法。
        """
        entries = [{"report_line_code": code}]
        assert find_invalid_report_line_codes(entries) == []

    @settings(max_examples=5)
    @given(
        seed_codes=st.lists(st.from_regex(r"[1-9][0-9]{3}", fullmatch=True), min_size=0, max_size=5),
        all_codes=st.lists(st.from_regex(r"[1-9][0-9]{3}", fullmatch=True), min_size=1, max_size=10),
    )
    def test_uncovered_is_complement(self, seed_codes: list[str], all_codes: list[str]):
        """**Validates: Requirements 5.2**

        Property: 未覆盖科目 = 全集 - seed 覆盖集。
        """
        entries = [{"standard_account_code": c} for c in seed_codes]
        standard = [{"code": c, "name": f"科目{c}"} for c in all_codes]
        uncovered = find_uncovered_accounts(entries, standard)
        uncovered_codes = {a["code"] for a in uncovered}
        expected = {c for c in all_codes if c not in set(seed_codes)}
        assert uncovered_codes == expected
