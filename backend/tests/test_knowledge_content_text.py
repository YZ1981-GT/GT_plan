"""知识库上传的正文抽取链（``knowledge_folders._extract_text_with_ocr``）。

现链路（2026-09-30 按实现重写；旧版按 bb7ea6cfe 时的「MinerU 优先」链写成，4 红 3 绿被当成常态）：

  1. anydoc（主路径）—— 成功即返回；``permanent``（加密 / 真不支持）即停
  2. MarkItDown —— anydoc 未命中且**不是**扫描件时
  3. MinerU OCR —— 仅 PDF；扫描件（anydoc ``needs_ocr``）靠它
  4. pypdf / python-docx —— 最后兜底（原为未声明也未安装的 PyPDF2，宽 ``try`` 把
     ``ModuleNotFoundError`` 吞掉，PDF 兜底静默恒返回 None）

判据要点：
  * anydoc 结果用真 ``AnydocResult`` 构造 —— MagicMock 的 ``needs_ocr`` 恒为真值，分支判据会空转。
  * pypdf / python-docx 不打补丁，喂**真**字节：PDF 手工拼装（xref 偏移逐字节计算，不依赖
    PyPDF2 / PyMuPDF / reportlab），docx 用 python-docx 生成。
  * 「链路在某处停下」用**本可成功的后续引擎**来证明：给 permanent 失败喂一份 pypdf 能抽出文本的 PDF，
    结果仍须为 None。

**Validates: spec environment-hygiene-deps-and-scratch-schemas Requirement 2–3**
"""
from __future__ import annotations

import io
import logging
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.knowledge_folders import _extract_text_with_ocr
from app.services.anydoc_service import AnydocResult

LIMIT = 50000
PDF_PATH = "/tmp/kb-test.pdf"
DOCX_PATH = "/tmp/kb-test.docx"


# ═══ 真实字节夹具 ═════════════════════════════════════════════════════════════


def make_text_pdf(text: str) -> bytes:
    """带文本层的最小 PDF：单页、单个 Tj。xref 偏移逐字节计算（pypdf 严格校验时也能读）。"""
    stream = f"BT /F1 18 Tf 72 700 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def make_blank_pdf() -> bytes:
    """无文本层的 PDF（扫描件的最小替身）。"""
    from pypdf import PdfWriter

    buf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(buf)
    return buf.getvalue()


def make_docx(*paragraphs: str) -> bytes:
    from docx import Document

    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_fixture_pdf_really_has_a_text_layer():
    """夹具自检：手工 PDF 的文本真能被 pypdf 读出，空白 PDF 读不出 —— 否则下面的兜底判据全是空转。"""
    from pypdf import PdfReader

    assert "KBFIXTURE" in PdfReader(io.BytesIO(make_text_pdf("KBFIXTURE 42"))).pages[0].extract_text()
    assert not (PdfReader(io.BytesIO(make_blank_pdf())).pages[0].extract_text() or "").strip()


# ═══ 引擎替身 ═════════════════════════════════════════════════════════════════

ANYDOC_MISS = AnydocResult(None, False, error_code="Malformed", message="miss")
ANYDOC_OCR = AnydocResult(
    None, False, error_code="Unsupported",
    message="PDF has no extractable text; OCR is required", needs_ocr=True,
)
ANYDOC_ENCRYPTED = AnydocResult(
    None, False, error_code="Encrypted", message="document is encrypted", permanent=True,
)


def _mineru(*, available: bool, text: str | None = None, error: Exception | None = None):
    svc = AsyncMock()
    svc.is_available.return_value = available
    if error is not None:
        svc.recognize_for_ocr.side_effect = error
    else:
        svc.recognize_for_ocr.return_value = {"text": text or "", "engine": "mineru", "regions": []}
    return svc


@contextmanager
def engines(*, anydoc, markitdown=None, mineru=None):
    """替换链上的三个外部引擎；返回各替身供断言调用情况。

    ``anydoc`` 为 AnydocResult 或 Exception；``markitdown`` 为返回值或 Exception。
    打补丁目标取**定义处**：被测函数在函数体内 ``from … import``，调用时才读模块属性。
    """
    anydoc_mock = MagicMock(
        side_effect=anydoc if isinstance(anydoc, Exception) else None,
        return_value=None if isinstance(anydoc, Exception) else anydoc,
    )
    md_mock = MagicMock(
        side_effect=markitdown if isinstance(markitdown, Exception) else None,
        return_value=None if isinstance(markitdown, Exception) else markitdown,
    )
    mineru_ctor = MagicMock(return_value=mineru or _mineru(available=False))
    with patch("app.services.anydoc_service.convert_bytes_detailed", anydoc_mock), \
            patch("app.services.markitdown_service.convert_bytes_to_markdown", md_mock), \
            patch("app.services.mineru_service.MinerUService", mineru_ctor):
        yield {"anydoc": anydoc_mock, "markitdown": md_mock, "mineru_ctor": mineru_ctor}


# ═══ 1. anydoc 主路径 ═════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_anydoc_success_short_circuits_the_chain():
    ok = AnydocResult("## 标题\n\nKB 正文", True)
    with engines(anydoc=ok) as e:
        result = await _extract_text_with_ocr(PDF_PATH, make_text_pdf("OTHER"), "a.pdf")

    assert result == "## 标题\n\nKB 正文"
    e["anydoc"].assert_called_once()
    e["markitdown"].assert_not_called()
    e["mineru_ctor"].assert_not_called()


@pytest.mark.asyncio
async def test_anydoc_permanent_failure_stops_the_chain():
    """加密 / 真不支持 ⇒ 不再试任何引擎。喂一份 pypdf 本可抽出文本的 PDF 来证明链路真的停了。"""
    with engines(anydoc=ANYDOC_ENCRYPTED, markitdown="不该被用到") as e:
        result = await _extract_text_with_ocr(PDF_PATH, make_text_pdf("KBPERMANENT"), "enc.pdf")

    assert result is None
    e["markitdown"].assert_not_called()
    e["mineru_ctor"].assert_not_called()


# ═══ 2. MarkItDown ════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("anydoc", [ANYDOC_MISS, RuntimeError("anydoc CLI crashed")], ids=["miss", "raises"])
async def test_markitdown_takes_over_when_anydoc_misses(anydoc):
    with engines(anydoc=anydoc, markitdown="MarkItDown 正文") as e:
        result = await _extract_text_with_ocr(DOCX_PATH, make_docx("python-docx 不该被用到"), "a.docx")

    assert result == "MarkItDown 正文"
    e["markitdown"].assert_called_once()
    e["mineru_ctor"].assert_not_called()


# ═══ 3. 扫描件 → MinerU ═══════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_scanned_pdf_skips_markitdown_and_uses_mineru_truncated():
    mineru = _mineru(available=True, text="扫" * 60000)
    with engines(anydoc=ANYDOC_OCR, markitdown="不该被用到", mineru=mineru) as e:
        result = await _extract_text_with_ocr(PDF_PATH, make_blank_pdf(), "scan.pdf")

    assert result == "扫" * LIMIT
    e["markitdown"].assert_not_called()  # 扫描件无文本层，MarkItDown 同样提不出，直接进 OCR
    mineru.recognize_for_ocr.assert_awaited_once_with(PDF_PATH)


@pytest.mark.asyncio
async def test_scanned_pdf_without_ocr_engine_logs_error_and_returns_none(caplog):
    """已确知是扫描件却无 OCR 引擎：结果为空，且必须留 ERROR —— 不能让「没抽到」看起来像「文档没内容」。"""
    with caplog.at_level(logging.ERROR, logger="app.routers.knowledge_folders"), \
            engines(anydoc=ANYDOC_OCR, markitdown="不该被用到", mineru=_mineru(available=False)) as e:
        result = await _extract_text_with_ocr(PDF_PATH, make_blank_pdf(), "scan.pdf")

    assert result is None
    e["markitdown"].assert_not_called()
    assert any("是扫描件但 MinerU 不可用" in r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR)


# ═══ 4. 最后兜底：pypdf / python-docx ═══════════════════════════════════════════


@pytest.mark.asyncio
async def test_pdf_falls_back_to_pypdf_when_other_engines_miss():
    with engines(anydoc=ANYDOC_MISS, markitdown=None, mineru=_mineru(available=False)):
        result = await _extract_text_with_ocr(PDF_PATH, make_text_pdf("KBFALLBACK unique 12345"), "a.pdf")

    assert result is not None and "KBFALLBACK unique 12345" in result


@pytest.mark.asyncio
async def test_pypdf_fallback_truncates_to_limit():
    long_text = "KB0123456789" * 5000  # 60000 字
    with engines(anydoc=ANYDOC_MISS, markitdown=None, mineru=_mineru(available=False)):
        result = await _extract_text_with_ocr(PDF_PATH, make_text_pdf(long_text), "long.pdf")

    assert result is not None
    assert len(result) == LIMIT and result == long_text[:LIMIT]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mineru",
    [
        _mineru(available=True, error=RuntimeError("MinerU crashed")),
        _mineru(available=True, text="   "),
    ],
    ids=["mineru-raises", "mineru-empty"],
)
async def test_mineru_failure_falls_back_to_pypdf(mineru):
    with engines(anydoc=ANYDOC_MISS, markitdown=None, mineru=mineru):
        result = await _extract_text_with_ocr(PDF_PATH, make_text_pdf("KBAFTERMINERU"), "a.pdf")

    mineru.recognize_for_ocr.assert_awaited_once_with(PDF_PATH)
    assert result is not None and "KBAFTERMINERU" in result


@pytest.mark.asyncio
async def test_docx_falls_back_to_python_docx_and_never_calls_mineru():
    content = make_docx("第一段 KBDOCX", "   ", "第二段")
    with engines(anydoc=ANYDOC_MISS, markitdown=None) as e:
        result = await _extract_text_with_ocr(DOCX_PATH, content, "a.docx")

    assert result == "第一段 KBDOCX\n第二段"  # 空白段落被丢弃
    e["mineru_ctor"].assert_not_called()  # MinerU 只接 PDF


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "name"),
    [(b"%PDF-1.4 truncated", "broken.pdf"), (bytes(range(256)) * 4, "garbage.docx")],
    ids=["broken-pdf", "garbage-docx"],
)
async def test_unreadable_file_returns_none_without_raising(content, name):
    """兜底解析失败也只返回 None（上传不因抽取失败而中断）。"""
    with engines(anydoc=ANYDOC_MISS, markitdown=None, mineru=_mineru(available=False)):
        assert await _extract_text_with_ocr(f"/tmp/{name}", content, name) is None
