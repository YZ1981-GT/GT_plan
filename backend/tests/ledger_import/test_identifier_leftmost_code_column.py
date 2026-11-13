"""科目编码 / 科目名称只认最左一列；右侧备选编码列（SAP科目编码、原始科目编码等）不参与识别。"""
from __future__ import annotations

from app.services.ledger_import import identifier


HEADERS = [
    "公司代码", "科目编码", "科目名称", "级次", "年初借方", "年初贷方",
    "本期借方", "本期贷方", "期末借方", "期末贷方", "币种",
    "SAP科目编码", "来源系统", "原始科目编码", "原始科目名称", "映射方式",
]


def _fields(headers):
    _tt, _c, matches, _e = identifier._detect_by_headers(headers)
    return {m.column_header: m.standard_field for m in matches}


def test_alt_code_columns_not_mapped():
    f = _fields(HEADERS)
    assert f["科目编码"] == "account_code"
    assert f["科目名称"] == "account_name"
    assert f["SAP科目编码"] is None
    assert f["原始科目编码"] is None
    assert f["原始科目名称"] is None


def test_only_one_column_per_code_and_name_field():
    _tt, _c, matches, _e = identifier._detect_by_headers(HEADERS)
    fields = [m.standard_field for m in matches if m.standard_field]
    assert fields.count("account_code") == 1
    assert fields.count("account_name") == 1


def test_leftmost_wins_even_when_it_is_not_first_exact():
    f = _fields(["公司代码", "科目编码", "SAP科目编码"])
    assert f["科目编码"] == "account_code"
    assert f["SAP科目编码"] is None
    f2 = _fields(["SAP科目编码", "科目编码"])
    assert f2["SAP科目编码"] == "account_code"
    assert f2["科目编码"] is None


def test_other_fields_unaffected():
    f = _fields(HEADERS)
    assert f["币种"] == "currency_code"
    assert f["公司代码"] == "company_code"
    assert f["级次"] == "level"


def test_voucher_category_header_is_voucher_type_not_date():
    """「凭证类别」曾被编辑距离模糊匹配成 voucher_date（遇到的第一个距离≤2 的别名）。"""
    identifier.reload_rules()
    assert identifier._match_header("凭证类别")[0] == "voucher_type"
    assert identifier._match_header("凭证分类")[0] == "voucher_type"
    # 既有写法不受影响
    assert identifier._match_header("凭证日期")[0] == "voucher_date"
    assert identifier._match_header("记账日期")[0] == "voucher_date"
    assert identifier._match_header("凭证类型")[0] == "voucher_type"


def test_fuzzy_match_prefers_the_nearest_alias():
    """距离相同层级之前，距离更小的别名优先（1 先于 2）。"""
    identifier.reload_rules()
    # 「凭证日朗」与「凭证日期」差 1，与「凭证类型」差 2 ⇒ 必须是 voucher_date
    assert identifier._match_header("凭证日朗")[0] == "voucher_date"
