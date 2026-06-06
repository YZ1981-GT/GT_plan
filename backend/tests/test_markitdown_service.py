"""MarkItDown 文档转 Markdown 服务测试

覆盖：
- is_supported 白名单判定（扩展名大小写不敏感 + 拒绝非白名单）
- convert_bytes 真实转换：html / csv / json / xlsx 四类小样本
- 降级路径：空内容 / 非白名单 / 不可用时返回 None
- 便捷函数 convert_bytes_to_markdown 单例往返
- 输出截断 max_chars 生效

markitdown[all] 已装入 venv（本地纯 Python，无远端调用）；若环境缺失则整体 skip。
"""

from __future__ import annotations

import io

import pytest

from app.services.markitdown_service import (
    MarkItDownService,
    convert_bytes_to_markdown,
)

# markitdown 缺失则跳过真实转换用例（白名单/降级用例不依赖 markitdown）
_md_available = MarkItDownService.get_instance().is_available()
requires_md = pytest.mark.skipif(
    not _md_available, reason="markitdown 未安装/不可用"
)


# ─────────────────────── is_supported 白名单 ───────────────────────

@pytest.mark.parametrize(
    "filename,expected",
    [
        ("report.pdf", True),
        ("data.XLSX", True),  # 大小写不敏感
        ("notes.docx", True),
        ("page.html", True),
        ("table.csv", True),
        ("payload.json", True),
        ("archive.zip", False),  # 不在白名单
        ("photo.png", False),
        ("clip.mp3", False),
        ("", False),
        ("noext", False),
    ],
)
def test_is_supported(filename: str, expected: bool):
    assert MarkItDownService.is_supported(filename) is expected


# ─────────────────────── 降级路径（不依赖 markitdown） ───────────────────────

def test_empty_content_returns_none():
    assert convert_bytes_to_markdown(b"", "a.html") is None


def test_unsupported_extension_returns_none():
    # 非白名单扩展名：即使有内容也直接返回 None（不尝试转换）
    assert convert_bytes_to_markdown(b"<html>hi</html>", "a.zip") is None


def test_singleton_identity():
    a = MarkItDownService.get_instance()
    b = MarkItDownService.get_instance()
    assert a is b


# ─────────────────────── 真实转换：html / csv / json / xlsx ───────────────────────

@requires_md
def test_convert_html():
    html = b"<html><body><h1>Title</h1><p>Hello world</p></body></html>"
    out = convert_bytes_to_markdown(html, "page.html")
    assert out is not None
    assert "Title" in out
    assert "Hello world" in out


@requires_md
def test_convert_csv():
    csv = b"name,amount\nCash,100\nBank,200\n"
    out = convert_bytes_to_markdown(csv, "data.csv")
    assert out is not None
    assert "Cash" in out
    assert "200" in out


@requires_md
def test_convert_json():
    payload = b'{"account": "Cash", "balance": 12345}'
    out = convert_bytes_to_markdown(payload, "payload.json")
    assert out is not None
    assert "Cash" in out
    assert "12345" in out


@requires_md
def test_convert_xlsx():
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["科目", "金额"])
    ws.append(["库存现金", 8888])
    buf = io.BytesIO()
    wb.save(buf)
    out = convert_bytes_to_markdown(buf.getvalue(), "book.xlsx")
    assert out is not None
    assert "库存现金" in out
    assert "8888" in out


@requires_md
def test_max_chars_truncation():
    # 构造超长 html，验证截断到 max_chars
    body = "x" * 5000
    html = f"<html><body><p>{body}</p></body></html>".encode()
    out = convert_bytes_to_markdown(html, "big.html", max_chars=100)
    assert out is not None
    assert len(out) <= 100
