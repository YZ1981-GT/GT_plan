"""函证候选对象提取 —— 纯解析逻辑单测

覆盖 confirmation_service 的 _build_candidate_name / _is_numeric_token：
从 tb_aux_balance 的 aux_dimensions_raw（多维核算串）构造函证对象显示名。
审计敏感：名称/账号解析错误会导致函证对象错配，故锁定行为。
"""

from app.services.confirmation_service import (
    _build_candidate_name,
    _is_numeric_token,
    _CONFIRM_TYPE_ACCOUNT_PREFIXES,
)


class TestIsNumericToken:
    def test_pure_digits(self):
        assert _is_numeric_token("182769895215") is True

    def test_account_with_dashes(self):
        assert _is_numeric_token("6170-1970-0000-001906") is True

    def test_bank_name(self):
        assert _is_numeric_token("中国银行") is False

    def test_empty_treated_numeric(self):
        assert _is_numeric_token("") is True
        assert _is_numeric_token(None) is True


class TestBuildCandidateName:
    def test_bank_name_plus_account(self):
        raw = "金融机构:YG0003,中国银行;银行账户:182769895215"
        assert _build_candidate_name(raw, []) == "中国银行（182769895215）"

    def test_bank_name_dim_preferred_over_order(self):
        # 账号维度在前，机构维度在后，仍应取机构名为主名
        raw = "银行账户:617019700000001906;金融机构:YG0143,九江银行"
        assert _build_candidate_name(raw, []) == "九江银行（617019700000001906）"

    def test_receivable_single_dim_customer(self):
        raw = "客户:C001,某某贸易有限公司"
        assert _build_candidate_name(raw, []) == "某某贸易有限公司"

    def test_supplier_dim(self):
        raw = "供应商:S009,华东供货商"
        assert _build_candidate_name(raw, []) == "华东供货商"

    def test_no_raw_fallback_to_group_names(self):
        # raw 为空时回退分组内非数字 aux_name
        names = [("银行账户", "182769895215"), ("金融机构", "招商银行")]
        assert _build_candidate_name(None, names) == "招商银行"

    def test_all_numeric_returns_account(self):
        raw = "银行账户:551905148010401"
        assert _build_candidate_name(raw, []) == "551905148010401"

    def test_empty_returns_empty(self):
        assert _build_candidate_name(None, []) == ""


class TestAccountPrefixMapping:
    def test_bank_prefixes(self):
        assert _CONFIRM_TYPE_ACCOUNT_PREFIXES["bank"] == ["1001", "1002", "1012"]

    def test_all_types_present(self):
        for t in ("bank", "receivable", "payable", "loan"):
            assert t in _CONFIRM_TYPE_ACCOUNT_PREFIXES
            assert _CONFIRM_TYPE_ACCOUNT_PREFIXES[t]

    def test_unknown_type_absent(self):
        assert _CONFIRM_TYPE_ACCOUNT_PREFIXES.get("unknown") is None
