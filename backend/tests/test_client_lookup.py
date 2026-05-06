"""客户名称归一化测试"""

import pytest

from app.services.client_lookup import (
    client_names_match,
    normalize_client_name,
)


@pytest.mark.parametrize("a,b,expected", [
    # 相同名称：匹配
    ("ABC 公司", "ABC 公司", True),
    # 有/无"有限公司"后缀：应匹配
    ("ABC 集团有限公司", "ABC 集团", True),
    ("ABC 股份有限公司", "ABC", True),
    # 全角/半角括号
    ("XX（中国）有限公司", "XX(中国)有限公司", True),
    # 完全不同：不匹配
    ("ABC 公司", "XYZ 公司", False),
    # 空/None：不匹配
    ("", "ABC", False),
    (None, "ABC", False),
    ("ABC", None, False),
    ("", "", False),
    # Co.,Ltd 英文变体
    ("ACME Co., Ltd", "ACME Co Ltd", True),
    ("ACME Inc.", "ACME", True),
])
def test_client_names_match(a, b, expected):
    assert client_names_match(a, b) is expected


def test_normalize_strips_whitespace():
    assert normalize_client_name("  ABC  ") == "abc"


def test_normalize_none_returns_empty():
    assert normalize_client_name(None) == ""
    assert normalize_client_name("") == ""


def test_normalize_preserves_chinese_content():
    # 中文主体部分应完整保留
    assert "某某审计" in normalize_client_name("某某审计有限公司")
