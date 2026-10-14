"""附注文档解析器 — DOCX / PDF / Markdown-HTML-纯文本。

spec: disclosure-note-doc-upload-and-batch-fill Phase 3 Task 15~19

解析产出统一的 ``ParsedSection`` 列表，供 preview/apply 共用。
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from html import escape as html_escape
from pathlib import Path
from typing import IO, Any, BinaryIO

from app.services.note_html_sanitizer import sanitize_note_html as _sanitize

logger = logging.getLogger(__name__)

#: 平台 Word 模板的结构标记（导出引擎 ``note_word_exporter`` 用来定位 / 填充，不是业务正文）。
#: 四份模板约 75% 的章节带这些标记；用户把模板当来源上传时不剥掉就会被原样写进附注
#: （第二轮复盘浏览器实测发现：拟写入内容里出现「{{section:四、会计期间}}…##/SECTION」）。
_TEMPLATE_MARKER_RE = re.compile(r"##/?(?:SECTION|STYLE_REF)(?::[^#<]*)?##|\{\{(?:section|table|seq):[^{}<]*\}\}")
_EMPTY_PARAGRAPH_RE = re.compile(r"<p>(?:\s|&nbsp;)*</p>")


def sanitize_note_html(html: str) -> str:
    """消毒 + 剥掉平台模板标记（只在确有标记时才清理随之留下的空段落）。"""
    clean = _sanitize(html)
    stripped = _TEMPLATE_MARKER_RE.sub("", clean)
    return _EMPTY_PARAGRAPH_RE.sub("", stripped) if stripped != clean else clean

__all__ = [
    "ParsedSection",
    "ParseResult",
    "parse_docx",
    "parse_pdf",
    "parse_text_source",
    "ParseError",
]

# ── 容量限制（design §11.2 冻结值）────────────────────────────────────────

MAX_UPLOAD_BYTES = 50 * 1024 * 1024       # 50 MiB
MAX_PDF_PAGES = 500
MAX_DOCX_ZIP_ENTRIES = 2_000
MAX_DOCX_DECOMPRESS_BYTES = 200 * 1024 * 1024  # 200 MiB
MAX_SECTIONS = 500
MAX_SECTION_HTML_BYTES = 512 * 1024       # 512 KiB


class ParseError(Exception):
    """解析失败（含错误码和中文原因）。"""

    def __init__(self, code: str, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}")


@dataclass
class ParsedSection:
    source_id: str
    title: str
    level: int = 1
    html: str = ""
    confidence: str = "candidate"  # confirmed | candidate | manual_required
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseResult:
    sections: list[ParsedSection] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    needs_ocr: bool = False
    file_hash: str = ""


# ════════════════════════════════════════════════════════════════════════════
# DOCX 解析（Task 15~16）
# ════════════════════════════════════════════════════════════════════════════

_CN_HEADING_RE = re.compile(
    r"^[一二三四五六七八九十百千]+[、．.]"
    r"|^\d+[、．.]"
    r"|^（[一二三四五六七八九十百千]+）"
    r"|^\([一二三四五六七八九十百千\d]+\)"
)

_HEADING_STYLES = frozenset({
    "Heading 1", "Heading 2", "Heading 3", "Heading 4", "Heading 5",
    "标题 1", "标题 2", "标题 3", "标题 4", "标题 5",
})


def _validate_docx_zip(data: bytes) -> None:
    """在打开前检查 zip 安全性。"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ParseError("UNSUPPORTED_FILE", "文件损坏或不是有效的 DOCX 格式")

    entries = zf.infolist()
    if len(entries) > MAX_DOCX_ZIP_ENTRIES:
        raise ParseError("DOCX_ZIP_LIMIT", f"DOCX 内部文件数 {len(entries)} 超过上限 {MAX_DOCX_ZIP_ENTRIES}")

    total_size = sum(e.file_size for e in entries)
    if total_size > MAX_DOCX_DECOMPRESS_BYTES:
        raise ParseError(
            "DOCX_ZIP_LIMIT",
            f"DOCX 解压总字节 {total_size:,} 超过上限 {MAX_DOCX_DECOMPRESS_BYTES:,}",
        )
    zf.close()


def _heading_level_from_style(style_name: str | None) -> int | None:
    """从 Word 样式名推断标题层级。"""
    if not style_name:
        return None
    for prefix in ("Heading ", "标题 "):
        if style_name.startswith(prefix):
            try:
                return int(style_name[len(prefix):])
            except ValueError:
                pass
    if "GTNoteHeading" in style_name:
        return 2
    return None


def _run_to_html(run: Any) -> str:
    """将 python-docx Run 转为简单 HTML 片段。"""
    text = html_escape(run.text or "")
    if not text:
        return ""
    if run.bold:
        text = f"<strong>{text}</strong>"
    if run.italic:
        text = f"<em>{text}</em>"
    return text


def _paragraph_to_html(para: Any) -> str:
    """将 python-docx Paragraph 转为 HTML。"""
    parts = [_run_to_html(r) for r in para.runs]
    inner = "".join(parts).strip()
    if not inner:
        return ""
    return f"<p>{inner}</p>"


def _table_to_html(table: Any) -> str:
    """将 python-docx Table 转为安全 HTML。"""
    rows_html: list[str] = []
    for row in table.rows:
        cells_html: list[str] = []
        for cell in row.cells:
            text = html_escape(cell.text or "").strip()
            cells_html.append(f"<td>{text}</td>")
        rows_html.append(f"<tr>{''.join(cells_html)}</tr>")
    if not rows_html:
        return ""
    return f"<table>{''.join(rows_html)}</table>"


def parse_docx(data: bytes) -> ParseResult:
    """解析 DOCX 附注文档，返回章节列表。

    按 XML body 顺序混排处理段落和表格（AC-1.2）。
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise ParseError("FILE_TOO_LARGE", f"文件 {len(data):,} 字节超过上限 {MAX_UPLOAD_BYTES:,}")

    _validate_docx_zip(data)

    file_hash = hashlib.sha256(data).hexdigest()

    import docx
    from docx.oxml.ns import qn

    doc = docx.Document(io.BytesIO(data))
    body = doc.element.body

    sections: list[ParsedSection] = []
    current: ParsedSection | None = None
    warnings: list[str] = []
    section_idx = 0

    for elem in body:
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

        if tag == "p":
            para = docx.text.paragraph.Paragraph(elem, doc)
            style_name = para.style.name if para.style else None

            # 检查 outlineLvl
            outline_lvl = None
            pPr = elem.find(qn("w:pPr"))
            if pPr is not None:
                outlineLvl_elem = pPr.find(qn("w:outlineLvl"))
                if outlineLvl_elem is not None:
                    try:
                        outline_lvl = int(outlineLvl_elem.get(qn("w:val"), "9"))
                    except (ValueError, TypeError):
                        pass

            level = _heading_level_from_style(style_name)
            if level is None and outline_lvl is not None and outline_lvl < 6:
                level = outline_lvl + 1

            text = (para.text or "").strip()

            if level is not None and text:
                # 新章节
                section_idx += 1
                sid = f"docx-s{section_idx}"
                confidence = "candidate"
                if level <= 2 and _CN_HEADING_RE.match(text):
                    confidence = "candidate"  # 标题格式匹配但仍需人工确认
                current = ParsedSection(
                    source_id=sid,
                    title=text,
                    level=level,
                    confidence=confidence,
                )
                sections.append(current)
            elif text:
                # 正文段落
                html = _paragraph_to_html(para)
                if html and current:
                    current.html += html
                elif html and not current:
                    # 文档开头无标题的段落
                    section_idx += 1
                    current = ParsedSection(
                        source_id=f"docx-s{section_idx}",
                        title="（无标题）",
                        level=1,
                        html=html,
                        confidence="manual_required",
                    )
                    sections.append(current)
                    warnings.append("文档开头段落无标题，已作为独立章节")

        elif tag == "tbl":
            table = docx.table.Table(elem, doc)
            html = _table_to_html(table)
            if html and current:
                current.html += html
            elif html:
                section_idx += 1
                current = ParsedSection(
                    source_id=f"docx-s{section_idx}",
                    title="（表格）",
                    level=1,
                    html=html,
                    confidence="manual_required",
                )
                sections.append(current)

    if not sections:
        raise ParseError("NO_PARSEABLE_TEXT", "未能从 DOCX 中解析出任何章节")

    if len(sections) > MAX_SECTIONS:
        warnings.append(f"解析章节数 {len(sections)} 超过上限 {MAX_SECTIONS}，已截断")
        sections = sections[:MAX_SECTIONS]

    # 消毒全部 HTML
    for s in sections:
        s.html = sanitize_note_html(s.html)
        if len(s.html.encode("utf-8")) > MAX_SECTION_HTML_BYTES:
            s.html = s.html[:MAX_SECTION_HTML_BYTES // 3]  # 粗略截断
            s.warnings.append("章节正文超过单章上限，已截断")

    return ParseResult(sections=sections, warnings=warnings, file_hash=file_hash)


# ════════════════════════════════════════════════════════════════════════════
# PDF 解析（Task 17~18）
# ════════════════════════════════════════════════════════════════════════════

def parse_pdf(data: bytes) -> ParseResult:
    """解析 PDF 附注文档。

    使用 PyMuPDF block/line/span 信息识别标题（AC-1.3）。
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise ParseError("FILE_TOO_LARGE", f"文件 {len(data):,} 字节超过上限 {MAX_UPLOAD_BYTES:,}")

    file_hash = hashlib.sha256(data).hexdigest()

    import pymupdf

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ParseError("UNSUPPORTED_FILE", f"无法打开 PDF：{exc}")

    if doc.is_encrypted:
        raise ParseError("UNSUPPORTED_FILE", "PDF 已加密，请提供未加密版本")

    if doc.page_count > MAX_PDF_PAGES:
        raise ParseError("FILE_TOO_LARGE", f"PDF 页数 {doc.page_count} 超过上限 {MAX_PDF_PAGES}")

    # 收集全文 span 的字号中位数
    all_sizes: list[float] = []
    page_texts: list[list[dict[str, Any]]] = []

    for page in doc:
        blocks = page.get_text("dict", sort=True).get("blocks", [])
        page_spans: list[dict[str, Any]] = []
        for block in blocks:
            if block.get("type") != 0:  # 非文本块（图像等）
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = (span.get("text") or "").strip()
                    if text:
                        size = span.get("size", 12.0)
                        flags = span.get("flags", 0)
                        is_bold = bool(flags & (1 << 4))  # TEXT_FONT_BOLD
                        all_sizes.append(size)
                        page_spans.append({
                            "text": text,
                            "size": size,
                            "bold": is_bold,
                            "y0": span.get("bbox", [0, 0, 0, 0])[1],
                        })
        page_texts.append(page_spans)

    # 检查是否扫描件
    has_text = any(spans for spans in page_texts)
    if not has_text:
        return ParseResult(
            warnings=["PDF 不含可提取文本，可能是扫描件；请上传文字版或先通过知识库 OCR"],
            needs_ocr=True,
            file_hash=file_hash,
        )

    median_size = sorted(all_sizes)[len(all_sizes) // 2] if all_sizes else 12.0

    sections: list[ParsedSection] = []
    current: ParsedSection | None = None
    section_idx = 0

    for page_spans in page_texts:
        for span in page_spans:
            text = span["text"]
            size = span["size"]
            is_bold = span["bold"]

            # 标题候选：字号明显大于中位数，或加粗 + 中文章节模式
            is_heading = False
            level = 2
            if size > median_size * 1.3:
                is_heading = True
                level = 1 if size > median_size * 1.6 else 2
            elif is_bold and _CN_HEADING_RE.match(text) and len(text) < 60:
                is_heading = True
                level = 2

            if is_heading:
                section_idx += 1
                current = ParsedSection(
                    source_id=f"pdf-s{section_idx}",
                    title=text,
                    level=level,
                    confidence="candidate",
                    metadata={"font_size": size, "bold": is_bold},
                )
                sections.append(current)
            else:
                html_text = f"<p>{html_escape(text)}</p>"
                if current:
                    current.html += html_text
                elif text:
                    section_idx += 1
                    current = ParsedSection(
                        source_id=f"pdf-s{section_idx}",
                        title="（无标题）",
                        level=1,
                        html=html_text,
                        confidence="manual_required",
                    )
                    sections.append(current)

    if not sections:
        # 降级纯文本
        return _parse_pdf_plaintext_fallback(doc, file_hash)

    if len(sections) > MAX_SECTIONS:
        sections = sections[:MAX_SECTIONS]

    for s in sections:
        s.html = sanitize_note_html(s.html)

    doc.close()
    return ParseResult(sections=sections, file_hash=file_hash)


def _parse_pdf_plaintext_fallback(doc: Any, file_hash: str) -> ParseResult:
    """PyMuPDF span 解析失败时的纯文本降级。"""
    full_text = ""
    for page in doc:
        full_text += page.get_text("text") + "\n"
    doc.close()

    full_text = full_text.strip()
    if not full_text:
        raise ParseError("NO_PARSEABLE_TEXT", "PDF 不含可提取文本")

    # 按中文章节模式尝试分章
    sections: list[ParsedSection] = []
    current_title = "（无标题）"
    current_lines: list[str] = []
    idx = 0

    for line in full_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if _CN_HEADING_RE.match(line) and len(line) < 80:
            if current_lines:
                idx += 1
                sections.append(ParsedSection(
                    source_id=f"pdf-fallback-s{idx}",
                    title=current_title,
                    level=2,
                    html="".join(f"<p>{html_escape(l)}</p>" for l in current_lines),
                    confidence="manual_required",
                    warnings=["纯文本降级解析，标题置信度低"],
                ))
                current_lines = []
            current_title = line
        else:
            current_lines.append(line)

    if current_lines:
        idx += 1
        sections.append(ParsedSection(
            source_id=f"pdf-fallback-s{idx}",
            title=current_title,
            level=2,
            html="".join(f"<p>{html_escape(l)}</p>" for l in current_lines),
            confidence="manual_required",
            warnings=["纯文本降级解析，标题置信度低"],
        ))

    if not sections:
        raise ParseError("NO_PARSEABLE_TEXT", "PDF 纯文本降级后仍无法分章")

    for s in sections:
        s.html = sanitize_note_html(s.html)

    return ParseResult(
        sections=sections,
        warnings=["使用纯文本降级解析，所有标题为低置信候选"],
        file_hash=file_hash,
    )


# ════════════════════════════════════════════════════════════════════════════
# Markdown / HTML / 纯文本解析（Task 19）
# ════════════════════════════════════════════════════════════════════════════

_MD_HEADING_RE = re.compile(r"^(#{1,5})\s+(.+)")
_HTML_HEADING_RE = re.compile(r"<h([1-5])[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)


def parse_text_source(
    text: str,
    *,
    source_kind: str = "knowledge",
    doc_id: str | None = None,
    doc_name: str | None = None,
) -> ParseResult:
    """解析 Markdown / HTML / 纯文本来源。"""
    if not text or not text.strip():
        return ParseResult(warnings=["来源正文为空"])

    # 尝试 Markdown heading
    sections = _parse_markdown_headings(text)
    if sections:
        for s in sections:
            s.html = sanitize_note_html(s.html)
            s.metadata["source_kind"] = source_kind
            if doc_id:
                s.metadata["doc_id"] = doc_id
        return ParseResult(sections=sections)

    # 尝试 HTML heading
    sections = _parse_html_headings(text)
    if sections:
        for s in sections:
            s.html = sanitize_note_html(s.html)
            s.metadata["source_kind"] = source_kind
            if doc_id:
                s.metadata["doc_id"] = doc_id
        return ParseResult(sections=sections)

    # 中文章节标题精确匹配
    sections = _parse_cn_headings(text)
    if sections:
        for s in sections:
            s.html = sanitize_note_html(s.html)
            s.metadata["source_kind"] = source_kind
            if doc_id:
                s.metadata["doc_id"] = doc_id
        return ParseResult(sections=sections)

    # 单段降级
    sid = f"text-s1"
    title = doc_name or "（无标题）"
    return ParseResult(
        sections=[
            ParsedSection(
                source_id=sid,
                title=title,
                level=1,
                html=sanitize_note_html(f"<p>{html_escape(text.strip()[:10_000])}</p>"),
                confidence="manual_required",
                metadata={"source_kind": source_kind, "doc_id": doc_id},
            )
        ],
        warnings=["无法识别标题结构，整篇作为单个候选章节"],
    )


def _parse_markdown_headings(text: str) -> list[ParsedSection]:
    """按 Markdown # 标题分章。"""
    sections: list[ParsedSection] = []
    current: ParsedSection | None = None
    idx = 0

    for line in text.split("\n"):
        m = _MD_HEADING_RE.match(line.strip())
        if m:
            idx += 1
            level = len(m.group(1))
            title = m.group(2).strip()
            current = ParsedSection(
                source_id=f"md-s{idx}",
                title=title,
                level=level,
                confidence="candidate",
            )
            sections.append(current)
        elif current and line.strip():
            current.html += f"<p>{html_escape(line.strip())}</p>"

    return sections


def _parse_html_headings(text: str) -> list[ParsedSection]:
    """按 HTML h1~h5 标签分章。"""
    matches = list(_HTML_HEADING_RE.finditer(text))
    if not matches:
        return []

    sections: list[ParsedSection] = []
    for i, m in enumerate(matches):
        level = int(m.group(1))
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        # 本标题到下一标题之间的内容
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append(ParsedSection(
            source_id=f"html-s{i + 1}",
            title=title,
            level=level,
            html=sanitize_note_html(body),
            confidence="candidate",
        ))

    return sections


def _parse_cn_headings(text: str) -> list[ParsedSection]:
    """按中文章节号模式分章（纯文本）。"""
    sections: list[ParsedSection] = []
    current_title = ""
    current_lines: list[str] = []
    idx = 0

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if _CN_HEADING_RE.match(line) and len(line) < 80:
            if current_lines or current_title:
                idx += 1
                sections.append(ParsedSection(
                    source_id=f"cn-s{idx}",
                    title=current_title or "（无标题）",
                    level=2,
                    html="".join(f"<p>{html_escape(l)}</p>" for l in current_lines),
                    confidence="candidate",
                ))
                current_lines = []
            current_title = line
        else:
            current_lines.append(line)

    if current_lines or current_title:
        idx += 1
        sections.append(ParsedSection(
            source_id=f"cn-s{idx}",
            title=current_title or "（无标题）",
            level=2,
            html="".join(f"<p>{html_escape(l)}</p>" for l in current_lines),
            confidence="candidate",
        ))

    return sections
