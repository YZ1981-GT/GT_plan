"""OnlyOffice 保存产物编号规范化（deliverable-writeback-and-online-edit-integrity AC-5.6）。

探针实证（design §0）：真 v15 的 numbering.xml 带 90 个 `<w:isLgl w:val="false"/>`，LibreOffice 据此把
japaneseCounting 的「七、」渲染成「7、」；删除显式 false 后恢复「七、」。本文件用合成 docx 钉行为，
真实 v15 + LibreOffice 复验见 test_onlyoffice_isLgl_libreoffice（soffice 可用时跑）。
"""
from __future__ import annotations

import shutil
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from app.services.onlyoffice_docx_normalize import normalize_onlyoffice_docx

_NUMBERING = "word/numbering.xml"
_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _docx(numbering_body: str, *, extra: dict[str, bytes] | None = None) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", f"<Types {_NS}/>")
        z.writestr(_NUMBERING, f"<w:numbering {_NS}>{numbering_body}</w:numbering>")
        for name, payload in (extra or {}).items():
            z.writestr(name, payload)
    return buf.getvalue()


def _read(content: bytes, part: str) -> bytes:
    with zipfile.ZipFile(BytesIO(content)) as z:
        return z.read(part)


def test_strips_only_false_islgl_variants():
    body = (
        '<w:abstractNum w:abstractNumId="0">'
        '<w:lvl w:ilvl="0"><w:isLgl w:val="false"/><w:numFmt w:val="japaneseCounting"/></w:lvl>'
        '<w:lvl w:ilvl="1"><w:isLgl w:val="0" /><w:numFmt w:val="decimal"/></w:lvl>'
        '<w:lvl w:ilvl="2"><w:isLgl w:val="off"/></w:lvl>'
        '<w:lvl w:ilvl="3"><w:isLgl w:val="true"/></w:lvl>'
        '<w:lvl w:ilvl="4"><w:numFmt w:val="bullet"/></w:lvl>'
        "</w:abstractNum>"
    )
    out = normalize_onlyoffice_docx(_docx(body))
    numbering = _read(out, _NUMBERING).decode()
    assert 'w:val="false"' not in numbering
    assert 'w:val="0"' not in numbering
    assert 'w:val="off"' not in numbering
    # 真值 isLgl 必须保留；其余结构不动
    assert '<w:isLgl w:val="true"/>' in numbering
    assert numbering.count("<w:numFmt") == 3


def test_no_false_islgl_returns_input_bytes_unchanged():
    content = _docx('<w:abstractNum w:abstractNumId="0"><w:isLgl w:val="true"/></w:abstractNum>')
    assert normalize_onlyoffice_docx(content) is content


def test_other_parts_are_byte_identical():
    extra = {"word/document.xml": b"<w:document>body</w:document>", "docProps/core.xml": b"<core/>"}
    out = normalize_onlyoffice_docx(_docx('<w:lvl><w:isLgl w:val="false"/></w:lvl>', extra=extra))
    for name, payload in extra.items():
        assert _read(out, name) == payload


@pytest.mark.parametrize("bad", [b"", b"not a zip", b"PK\x03\x04 truncated"])
def test_non_docx_or_corrupt_returns_input(bad):
    assert normalize_onlyoffice_docx(bad) == bad


def test_missing_numbering_part_returns_input():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", b"<w:document/>")
    content = buf.getvalue()
    assert normalize_onlyoffice_docx(content) is content


_SOFFICE = shutil.which("soffice") or r"C:\Program Files\LibreOffice\program\soffice.exe"
_V15 = Path(
    r"d:\GT_plan\backend\storage\deliverables"
    r"\0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49\f2238a0d-f52d-4762-aeb1-9b8e3ec3a01f\disclosure_notes_v15.docx"
)


@pytest.mark.skipif(not Path(_SOFFICE).exists() or not _V15.exists(), reason="需要 LibreOffice 与真实 v15")
def test_islgl_libreoffice_restores_chinese_chapter(tmp_path: Path):
    """真实 v15 经规范化后，LibreOffice 把章标题渲染回「七、」而非「7、」。"""
    normalized = tmp_path / "v15_fixed.docx"
    normalized.write_bytes(normalize_onlyoffice_docx(_V15.read_bytes()))
    subprocess.run(
        [_SOFFICE, "--headless", "--convert-to", "txt:Text (encoded):UTF8", "--outdir", str(tmp_path), str(normalized)],
        check=True, capture_output=True, timeout=180,
    )
    text = (tmp_path / "v15_fixed.txt").read_text(encoding="utf-8", errors="replace")
    hit = next((ln.strip() for ln in text.splitlines() if "财务报表主要项目注释" in ln), "")
    assert hit.startswith("七、"), f"规范化后仍非「七、」：{hit!r}"
