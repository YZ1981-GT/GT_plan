# Feature: formula-management-library, Property 16: 中文文件名 RFC 5987 编码往返
"""属性测试 P16：中文文件名 RFC 5987 编码往返（Req 18.5）。

*对任意* 含非 ASCII 字符（中文等）的文件名，经
``delivery_export.content_disposition_attachment`` 构造的 ``Content-Disposition``
头，其 ``filename*=UTF-8''...`` 分段按 RFC 5987 规则解码后，必须**无损还原**为原始
文件名（去除首尾空白后的规范形态）。这保证浏览器下载时中文文件名不乱码、不丢字符。

被测：``app.services.formula_management.delivery_export.content_disposition_attachment``
（Task 10.1 已实现，``filename*=UTF-8''`` 百分号编码 + 纯 ASCII 回退名）。

验证手段：
- 用正则解析头中的 RFC 5987 ext-value（``charset'lang'pct-encoded``），
  以 ``urllib.parse.unquote(value, encoding=charset)`` 解码，断言等于原始名。
- 交叉用字节级路径（``unquote_to_bytes`` → ``.decode(charset)``）独立复核，验证
  百分号编码的字节序列正是原始名的 UTF-8 编码（真实客户端的解码语义），
  确保不是单一解码器的巧合。

Framework: hypothesis（遵循 conftest fast profile，max_examples 可经
HYPOTHESIS_MAX_EXAMPLES 覆盖）。

**Validates: Requirements 18.5**
"""

from __future__ import annotations

import re
from urllib.parse import unquote, unquote_to_bytes

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.formula_management.delivery_export import (
    content_disposition_attachment,
)

# ─────────────────────────────────────────────────────────────────────────────
# RFC 5987 ext-value 解析：filename*=<charset>'<lang>'<pct-encoded>
# （客户端/浏览器据此解码真实文件名）
# ─────────────────────────────────────────────────────────────────────────────
_EXT_VALUE_RE = re.compile(
    r"filename\*=(?P<charset>[\w-]+)'(?P<lang>[\w-]*)'(?P<value>[^;]*)"
)


def _decode_rfc5987(header: str) -> str:
    """从 Content-Disposition 头解出 RFC 5987 ``filename*`` 的真实文件名。"""
    m = _EXT_VALUE_RE.search(header)
    assert m is not None, f"头缺少 filename* 分段: {header!r}"
    charset = m.group("charset")
    return unquote(m.group("value"), encoding=charset, errors="strict")


def _decode_rfc5987_bytewise(header: str) -> str:
    """字节级独立复核：百分号解码为字节序列后按声明 charset 解码。

    这条路径不依赖 ``unquote`` 的 encoding 参数，直接验证「编码后的字节 == 原始名
    的 charset 字节」，即真实客户端「先反百分号得字节、再按 charset 解码」的语义。
    """
    m = _EXT_VALUE_RE.search(header)
    assert m is not None, f"头缺少 filename* 分段: {header!r}"
    raw = unquote_to_bytes(m.group("value"))
    return raw.decode(m.group("charset"))


# ─────────────────────────────────────────────────────────────────────────────
# 智能生成器：含非 ASCII（中文/日文假名/emoji 等）的文件名，去空白后非空。
# ─────────────────────────────────────────────────────────────────────────────
# 非 ASCII 字符：常用中文 + 若干需转义的宽字符范围。
_NON_ASCII = st.one_of(
    st.characters(min_codepoint=0x4E00, max_codepoint=0x9FFF),  # CJK 统一表意
    st.characters(min_codepoint=0x3040, max_codepoint=0x30FF),  # 日文假名
    st.sampled_from(list("测试报表财务附注审计底稿导出①②③—、（）")),
)
# ASCII 部分：字母数字 + 常见文件名字符（含会被 quote 转义的空格/括号/引号）。
_ASCII_PART = st.text(
    alphabet="ABCabc0123 _-().[]'!",
    min_size=0,
    max_size=12,
)


@st.composite
def _chinese_filename(draw) -> str:
    """构造含 ≥1 个非 ASCII 字符、去首尾空白后非空的文件名。"""
    prefix = draw(_ASCII_PART)
    core = draw(st.text(alphabet=_NON_ASCII, min_size=1, max_size=15))
    suffix = draw(st.sampled_from([".xlsx", ".docx", ".pdf", "", ".zip"]))
    name = f"{prefix}{core}{suffix}"
    # 保证去首尾空白后仍非空（函数会 strip；空则退化为 "download" 破坏往返前提）。
    if not name.strip():
        name = f"报表{suffix}"
    return name


@given(_chinese_filename())
@settings(max_examples=200)
def test_rfc5987_filename_roundtrip(filename: str):
    """P16：中文文件名 RFC 5987 编码后可无损解码还原。

    **Validates: Requirements 18.5**
    """
    header = content_disposition_attachment(filename)

    # 函数对输入做 strip 归一（空白不作为有效文件名的一部分传输）。
    expected = filename.strip()

    # 1) 头形态契约：attachment + 双名（ASCII 回退 + RFC 5987 filename*）。
    assert header.startswith("attachment;")
    assert "filename=" in header
    assert "filename*=UTF-8''" in header

    # 2) 自解析 RFC 5987 ext-value → 无损还原原始名。
    decoded = _decode_rfc5987(header)
    assert decoded == expected

    # 3) 字节级独立解码路径一致（先反百分号得字节，再按 charset 解码）。
    assert _decode_rfc5987_bytewise(header) == expected


# ─────────────────────────────────────────────────────────────────────────────
# 单元测试：具体示例 + 边界（覆盖属性测试不易命中的固定场景）。
# ─────────────────────────────────────────────────────────────────────────────
def test_pure_chinese_filename_roundtrip():
    """纯中文文件名往返还原。"""
    name = "财务报表附注.xlsx"
    header = content_disposition_attachment(name)
    assert _decode_rfc5987(header) == name
    assert _decode_rfc5987_bytewise(header) == name


def test_mixed_chinese_ascii_roundtrip():
    """中英混合 + 空格 + 括号往返还原。"""
    name = "2025 审计报告 (final).docx"
    header = content_disposition_attachment(name)
    assert _decode_rfc5987(header) == name
    # ASCII 回退名不含中文（老客户端可读），且去除了破坏 quoted-string 的引号。
    ascii_m = re.search(r'filename="(?P<v>[^"]*)"', header)
    assert ascii_m is not None
    assert all(ord(c) < 128 for c in ascii_m.group("v"))


def test_empty_filename_falls_back_to_download():
    """空/纯空白文件名退化为 ASCII 回退名 download，头仍合法可解码。"""
    header = content_disposition_attachment("   ")
    assert _decode_rfc5987(header) == "download"
    assert _decode_rfc5987_bytewise(header) == "download"


def test_filename_with_quote_does_not_break_ascii_fallback():
    """含双引号的名不会破坏 quoted-string 的 ASCII 回退名。"""
    header = content_disposition_attachment('a"b报表.xlsx')
    # ASCII 回退名剥离了双引号，头整体仍是单一 quoted-string。
    assert re.search(r'filename="[^"]*"', header) is not None
    # RFC 5987 分段仍无损还原（含引号）。
    assert _decode_rfc5987(header) == 'a"b报表.xlsx'
