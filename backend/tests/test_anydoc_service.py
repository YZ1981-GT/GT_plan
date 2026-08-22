"""anydoc 文档抽取服务守卫

判据形态说明（全部落到**真实执行**，不用「符号存在」式弱判据）：
- 可用性探测必须真跑 `--version` 并校验 rc，不能只看文件存在
  （npm 包装脚本可能指向已被删除的 venv/exe）。
- 扫描件 PDF 必须回 `needs_ocr=True` —— 上层据此精准路由到 MinerU，
  这是「失败可归因」而非「静默返空」的关键信号。
- rc=0 但产出为空必须报 Malformed，不得返回空串冒充成功。

变异检验（2026-08-21）：4 条变异全 RED / 0 GREEN / 0 ANCHOR-MISS
  ① 破坏 _OCR_REQUIRED_MARKERS      → test_scanned_pdf_signals_needs_ocr 红
  ② permanent 恒 False              → test_classify_failure_* 红
  ③ 可用性探测不校验 rc              → test_unavailable_when_probe_exits_nonzero 红
  ④ 去掉空产出防御                   → test_empty_output_reports_malformed 红
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.services.anydoc_service import (
    SUPPORTED_EXTENSIONS,
    AnydocService,
    convert_bytes_detailed,
)

def _cli_available() -> bool:
    exe = shutil.which("anydoc")
    if not exe:
        return False
    try:
        return subprocess.run([exe, "--version"], capture_output=True, timeout=30).returncode == 0
    except Exception:
        return False


requires_cli = pytest.mark.skipif(
    not _cli_available(), reason="anydoc CLI 不可用（npm i -g @firecrawl/anydoc）"
)


# ---------------------------------------------------------------------------
# 纯函数：失败归因（不依赖 CLI，恒可运行）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("diag", "code", "permanent", "needs_ocr"),
    [
        ("anydoc: Encrypted: password protected", "Encrypted", True, False),
        ("anydoc: Unsupported: unknown format", "Unsupported", True, False),
        ("anydoc: Malformed: no extractable content", "Malformed", False, False),
        ("anydoc: ResourceLimit: nesting too deep", "ResourceLimit", False, False),
        ("anydoc: MissingPart: styles part absent", "MissingPart", False, False),
        (
            "anydoc: unsupported input: PDF has no extractable text "
            "(Scanned, 3 pages): OCR is required",
            "Unsupported",
            False,
            True,
        ),
    ],
)
def test_classify_failure_maps_diagnostics(diag, code, permanent, needs_ocr):
    """anydoc 诊断串 → 结构化归因。

    扫描件那条最关键：它虽然带 Unsupported 码，但 permanent 必须为 False
    且 needs_ocr 为 True —— 否则上层会把「该送去 OCR」误判成「永久放弃」。
    """
    r = AnydocService._classify_failure("probe", diag)
    assert r.error_code == code
    assert r.permanent is permanent
    assert r.needs_ocr is needs_ocr
    assert r.ok is False
    assert r.text is None


def test_scanned_pdf_is_not_permanent():
    """反向断言：扫描件不得被标为 permanent，否则永远不会进 OCR 分支。"""
    r = AnydocService._classify_failure(
        "scan.pdf",
        "anydoc: unsupported input: PDF has no extractable text (Scanned, 1 pages): OCR is required",
    )
    assert r.needs_ocr is True
    assert r.permanent is False, "扫描件必须可路由到 OCR，不能当永久失败放弃"


def test_supported_extensions_cover_legacy_binary_formats():
    """选 anydoc 当主路径的核心理由之一是覆盖旧二进制格式。"""
    for ext in (".doc", ".xls", ".ppt"):
        assert ext in SUPPORTED_EXTENSIONS, f"{ext} 应在支持列表内"


def test_unsupported_extension_short_circuits_as_permanent():
    """图片等非文档格式直接判 permanent，不启动子进程。"""
    r = convert_bytes_detailed(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32, "chart.png")
    assert r.ok is False
    assert r.permanent is True
    assert r.error_code == "Unsupported"


def test_empty_content_guarded():
    r = convert_bytes_detailed(b"", "x.docx")
    assert r.ok is False
    assert r.text is None


# ---------------------------------------------------------------------------
# 可用性探测：必须校验退出码
# ---------------------------------------------------------------------------


def test_unavailable_when_probe_exits_nonzero(monkeypatch, tmp_path):
    """假 exe 正常退出但 rc=3 → 必须判不可用。

    这里刻意用「正常退出且 rc!=0」的批处理，而不是一个会抛异常的命令：
    抛异常会走 except 分支，那样 rc 校验在不在都返回 False，判据就失去区分能力。
    """
    bat = tmp_path / "fake_anydoc.bat"
    bat.write_text("@echo off\r\nexit /b 3\r\n", encoding="ascii")

    monkeypatch.setattr(shutil, "which", lambda _name: str(bat))
    svc = AnydocService()
    assert svc.is_available() is False


def test_unavailable_when_cli_missing(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    svc = AnydocService()
    assert svc.is_available() is False


# ---------------------------------------------------------------------------
# 真实转换（需 CLI）
# ---------------------------------------------------------------------------


@requires_cli
def test_csv_roundtrip_preserves_table_and_cjk():
    """CSV → Markdown 表格，中文不得乱码（Windows 控制台编码坑）。"""
    blob = (
        "科目名称,科目代码,期末余额\n"
        "库存现金,1001,9871.40\n"
        "银行存款,1002,3980220.55\n"
    ).encode("utf-8")
    r = convert_bytes_detailed(blob, "tb.csv")
    assert r.ok is True
    assert r.text is not None
    assert "|" in r.text, "表格结构应保留"
    assert "库存现金" in r.text, "中文不得乱码"
    assert "9871.40" in r.text, "金额精度不得丢失"


@requires_cli
def test_docx_heading_and_table_preserved():
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    doc.add_heading("应收账款账龄分析", level=1)
    t = doc.add_table(rows=2, cols=2)
    t.cell(0, 0).text = "账龄"
    t.cell(0, 1).text = "金额"
    t.cell(1, 0).text = "1年以内"
    t.cell(1, 1).text = "780000.00"

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "aging.docx"
        doc.save(str(p))
        r = convert_bytes_detailed(p.read_bytes(), "aging.docx")

    assert r.ok is True
    assert r.text is not None
    assert "应收账款账龄分析" in r.text
    assert "780000.00" in r.text


@requires_cli
def test_empty_output_reports_malformed():
    """rc=0 但无内容 → 必须报失败，不得返回空串冒充成功。"""
    docx = pytest.importorskip("docx")
    blank = docx.Document()  # 无任何段落

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "blank.docx"
        blank.save(str(p))
        r = convert_bytes_detailed(p.read_bytes(), "blank.docx")

    assert r.ok is False
    assert r.text is None
    assert r.error_code == "Malformed"


@requires_cli
def test_scanned_pdf_signals_needs_ocr():
    """端到端：图片型 PDF → needs_ocr=True，供上层路由到 MinerU。"""
    pytest.importorskip("reportlab")
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "s.png"
        img = Image.new("RGB", (800, 240), "white")
        ImageDraw.Draw(img).text((24, 100), "SCANNED VOUCHER", fill="black")
        img.save(png)

        pdf = Path(td) / "scanned.pdf"
        c = canvas.Canvas(str(pdf), pagesize=A4)
        c.drawImage(ImageReader(str(png)), 40, 520, width=480, height=140)
        c.showPage()
        c.save()

        r = convert_bytes_detailed(pdf.read_bytes(), "scanned.pdf")

    assert r.ok is False
    assert r.needs_ocr is True, "扫描件必须给出 OCR 路由信号"
    assert r.permanent is False, "扫描件不是永久失败"
    assert r.message, "失败必须带可读诊断，不能静默"


@requires_cli
def test_service_reports_version_when_available():
    svc = AnydocService()
    assert svc.is_available() is True
    assert svc.version, "可用时应记录版本号，便于排障"
