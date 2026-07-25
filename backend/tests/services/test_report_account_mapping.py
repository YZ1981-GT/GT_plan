"""report_account_mapping 单测：报表规则映射 → 科目编号解析。"""
from __future__ import annotations

from app.services.report_account_mapping import (
    extract_codes_from_formula,
    build_trial_balance_code_filter,
)


class TestExtractCodes:
    def test_single_tb_codes(self):
        f = "TB('1001','期末余额') + TB('1002','期末余额') + TB('1012','期末余额')"
        assert extract_codes_from_formula(f) == ["1001", "1002", "1012"]

    def test_sum_tb_range(self):
        f = "SUM_TB('1401~1499','期末余额')"
        assert extract_codes_from_formula(f) == ["1401~1499"]

    def test_mixed(self):
        f = "TB('1001','期末余额') + SUM_TB('1401~1499','期末余额')"
        assert extract_codes_from_formula(f) == ["1001", "1401~1499"]

    def test_empty_and_none(self):
        assert extract_codes_from_formula(None) == []
        assert extract_codes_from_formula("") == []
        assert extract_codes_from_formula("100 + 50") == []

    def test_dedup_and_sorted(self):
        f = "TB('1002','期末') + TB('1001','期末') + TB('1002','期初')"
        assert extract_codes_from_formula(f) == ["1001", "1002"]


class TestBuildFilter:
    def test_single_codes_like_prefix(self):
        where, params = build_trial_balance_code_filter(["1001", "1002", "1012"])
        assert "standard_account_code LIKE :acc0" in where
        assert params == {"acc0": "1001%", "acc1": "1002%", "acc2": "1012%"}

    def test_range_between(self):
        where, params = build_trial_balance_code_filter(["1401~1499"])
        assert ":acc0_lo" in where and ":acc0_hi" in where
        assert params["acc0_lo"] == "1401"
        assert params["acc0_hi"].startswith("1499")

    def test_empty_codes_matches_nothing(self):
        where, params = build_trial_balance_code_filter([])
        assert where == "1=0"
        assert params == {}

    def test_custom_prefix(self):
        where, params = build_trial_balance_code_filter(["6602"], param_prefix="x")
        assert params == {"x0": "6602%"}
