"""Verification script for aux_dimension.py Tasks 24-26."""

from backend.app.services.ledger_import.aux_dimension import (
    parse_aux_dimension,
    detect_aux_columns,
    PATTERNS,
)


def test_json_format():
    r = parse_aux_dimension('{"客户":"001","项目":"P01"}')
    assert len(r) == 2
    assert r[0] == {"aux_type": "客户", "aux_code": None, "aux_name": "001"}
    assert r[1] == {"aux_type": "项目", "aux_code": None, "aux_name": "P01"}


def test_colon_code_name():
    r = parse_aux_dimension("客户:001 北京某科技")
    assert r == [{"aux_type": "客户", "aux_code": "001", "aux_name": "北京某科技"}]


def test_slash_separated():
    r = parse_aux_dimension("供应商/V001/上海某某")
    assert r == [{"aux_type": "供应商", "aux_code": "V001", "aux_name": "上海某某"}]


def test_pipe_separated():
    r = parse_aux_dimension("项目|P01|新产品开发")
    assert r == [{"aux_type": "项目", "aux_code": "P01", "aux_name": "新产品开发"}]


def test_code_name():
    r = parse_aux_dimension("C001 北京某科技")
    assert r == [{"aux_type": None, "aux_code": "C001", "aux_name": "北京某科技"}]


def test_arrow_format():
    r = parse_aux_dimension("项目 -> 研发部")
    assert r == [{"aux_type": "项目", "aux_code": None, "aux_name": "研发部"}]


def test_multi_dimension_comma():
    r = parse_aux_dimension("客户:001 北京某科技,项目:P01 新产品")
    assert len(r) == 2
    assert r[0]["aux_type"] == "客户"
    assert r[1]["aux_type"] == "项目"


def test_multi_dimension_semicolon():
    r = parse_aux_dimension("客户:001 北京某科技；项目:P01 新产品")
    assert len(r) == 2


def test_empty_none():
    assert parse_aux_dimension("") == []
    assert parse_aux_dimension("   ") == []
    assert parse_aux_dimension(None) == []


def test_unparseable():
    r = parse_aux_dimension("随便什么")
    assert r == [{"aux_type": None, "aux_code": None, "aux_name": "随便什么"}]


def test_detect_aux_columns():
    headers = ["科目编码", "科目名称", "核算项目", "借方金额", "贷方金额", "辅助核算", "客户"]
    indices = detect_aux_columns(headers)
    assert 2 in indices  # 核算项目
    assert 5 in indices  # 辅助核算
    assert 6 in indices  # 客户
    assert 0 not in indices  # 科目编码 is not aux
    assert 3 not in indices  # 借方金额 is not aux


def test_patterns_exported():
    assert len(PATTERNS) == 8
    assert PATTERNS[0][1] == "json"
    assert PATTERNS[-1][1] == "arrow"


if __name__ == "__main__":
    test_json_format()
    test_colon_code_name()
    test_slash_separated()
    test_pipe_separated()
    test_code_name()
    test_arrow_format()
    test_multi_dimension_comma()
    test_multi_dimension_semicolon()
    test_empty_none()
    test_unparseable()
    test_detect_aux_columns()
    test_patterns_exported()
    print("ALL OK")
