"""附注文档解析器 — DOCX / PDF / Markdown-HTML-纯文本。

spec: disclosure-note-doc-upload-and-batch-fill Phase 3 Task 15~19

解析产出统一的 ``ParsedSection`` 列表，供 preview/apply 共用。
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from html import escape as html_escape
from typing import Any

from app.services.note_html_sanitizer import sanitize_note_html as _sanitize
from app.services.note_pdf_outline import locate_heading_lines, outline_headings

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
#: 2026-10-15 拍板 500 → 1000：四份权威模板 315 / 322 / 382 / 412 章，原上限对国企合并只剩 18% 余量。
#: 解析结果原样回传预览 / 写入，请求体上限（``ParsedSource.sections`` / ``manual_mappings``）须同值。
MAX_SECTIONS = 1000
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

#: 标题编号排位（AC-1.6）：「一、」>「（一）」>「1.」/「1、」>「（1）」>「①」。PDF 与纯文字的标题据此定层级
#: 以成树（DOCX 用标题样式）；只定层级，是不是标题仍按 ``_CN_HEADING_RE`` / 字号判（「（1）」开头的正文段很常见）
_HEADING_RANKS: tuple[tuple[int, re.Pattern[str]], ...] = (
    (1, re.compile(r"^[一二三四五六七八九十百千]+[、．.]")),
    (2, re.compile(r"^[（(][一二三四五六七八九十百千]+[）)]")),
    (3, re.compile(r"^(?:\d{1,3}(?:[、．]|\.(?!\d))|[Xx][、．])")),  # 「X、数据资源」：国企模板里编号待定的节
    (4, re.compile(r"^[（(]\d{1,3}[）)]")),
    (5, re.compile(r"^[①-⑳]")),
)


def heading_rank(text: str | None) -> int | None:
    """标题编号排位；不带编号返回 None。"""
    stripped = (text or "").strip()
    for rank, pattern in _HEADING_RANKS:
        if pattern.match(stripped):
            return rank
    return None


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


def _style_chain_level(style: Any, cache: dict[str, int | None]) -> int | None:
    """段落样式沿基样式链继承的大纲级别 → 标题层级（第 23 组）。

    国企单体 Word「同一控制下的企业合并」用「样式2」（基于 Heading 4，自身不设大纲级别）：Word 导航窗格与
    LibreOffice 书签都当 4 级标题，首版只认样式名与段落自带大纲级别 ⇒ 并进上一节正文。
    """
    from docx.oxml.ns import qn

    key = getattr(style, "style_id", None) or ""
    if key in cache:
        return cache[key]
    level: int | None = None
    seen: set[str] = set()
    current = style
    while current is not None and (current.style_id or "") not in seen and len(seen) < 20:
        seen.add(current.style_id or "")
        level = _heading_level_from_style(current.name)
        ppr = current.element.find(qn("w:pPr"))
        outline = ppr.find(qn("w:outlineLvl")) if ppr is not None else None
        if level is None and outline is not None:
            try:
                value = int(outline.get(qn("w:val"), "9"))
            except (TypeError, ValueError):
                value = 9
            level = value + 1 if value < 6 else None
        if level is not None or outline is not None:
            break
        current = current.base_style
    cache[key] = level
    return level


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
    style_levels: dict[str, int | None] = {}

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
            if level is None and outline_lvl is None and para.style is not None:  # 段落自设的大纲级别优先于样式
                level = _style_chain_level(para.style, style_levels)

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
            # 粗略按字符截断后**再消毒**：截断点可能落在标签中间，由消毒负责闭合 / 丢弃半个标签
            s.html = sanitize_note_html(s.html[:MAX_SECTION_HTML_BYTES // 3])
            s.warnings.append("章节正文超过单章上限，已截断")

    return ParseResult(sections=sections, warnings=warnings, file_hash=file_hash)


# ════════════════════════════════════════════════════════════════════════════
# PDF 解析（Task 17~18）
# ════════════════════════════════════════════════════════════════════════════

def _body_font_size(spans: list[dict[str, Any]]) -> float:
    """正文字号 = 按**字数**加权的字号中位数（并列取较小字号）。

    首版按 span 个数取中位数：标题行占比高的短文档（一个标题 + 一段正文 = 2 个 span，取上中位）取到的是
    标题字号，标题全判不出来、整篇进「（无标题）」（第 17 组真实写入验收「会计期间说明.pdf」）。正文字数远多于标题。
    """
    weighted = sorted((span["size"], len(span["text"])) for span in spans)
    total = sum(chars for _, chars in weighted)
    accumulated = 0
    for size, chars in weighted:
        accumulated += chars
        if accumulated * 2 >= total:
            return size
    return 12.0


#: 页眉 / 页脚所在的页面上下边带（占页高比例）
_RUNNING_BAND = 0.12
_DIGITS = re.compile(r"\d+")


def _drop_running_lines(page_texts: list[list[dict[str, Any]]], heights: list[float]) -> None:
    """去掉页眉页脚（第 23 组）：页面上下边带里、去掉数字后在过半页面上重复出现的行（公司名 / 「财务报表附注」/ 页码）。

    首版当正文：跨页的节中间插一段页眉；章标题在页底、首个下级在下页页首时，章正文只剩页眉页脚
    ⇒ 多出一条「章首正文」要用户手工处理（国企单体 PDF 每页 3 行页眉 + 页码）。少于 3 页不判。
    """
    pages = len(page_texts)
    if pages < 3:
        return

    def key(line: dict[str, Any], height: float) -> str | None:
        if line["y0"] < height * _RUNNING_BAND or line["y1"] > height * (1 - _RUNNING_BAND):
            return _DIGITS.sub("#", re.sub(r"\s+", "", line["text"]))
        return None

    counts: Counter[str] = Counter()
    for lines, height in zip(page_texts, heights):
        counts.update({k for line in lines if (k := key(line, height)) is not None})
    running = {k for k, n in counts.items() if n >= 3 and n * 2 >= pages}
    for index, (lines, height) in enumerate(zip(page_texts, heights)):
        page_texts[index] = [line for line in lines if key(line, height) not in running]


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

    # 收集全文 span（字号 / 加粗），正文字号见 _body_font_size；标题按「行」判定：Word 自动编号导出 PDF 后
    # 编号与标题文字常是同一行的两个 span，逐 span 判会把「1.」当标题、「会计期间」当正文（第 23 组）
    page_texts: list[list[dict[str, Any]]] = []
    heights: list[float] = []

    for page in doc:
        heights.append(page.rect.height)
        blocks = page.get_text("dict", sort=True).get("blocks", [])
        page_lines: list[dict[str, Any]] = []
        for block in blocks:
            if block.get("type") != 0:  # 非文本块（图像等）
                continue
            for line in block.get("lines", []):
                spans = []
                for span in line.get("spans", []):
                    text = (span.get("text") or "").strip()
                    if text:
                        spans.append({
                            "text": text,
                            "size": span.get("size", 12.0),
                            "bold": bool(span.get("flags", 0) & (1 << 4)),  # TEXT_FONT_BOLD
                        })
                if spans:
                    bbox = line.get("bbox") or (0.0, 0.0, 0.0, 0.0)
                    page_lines.append({
                        "text": "".join(s["text"] for s in spans),
                        "size": max(s["size"] for s in spans),
                        "bold": all(s["bold"] for s in spans),
                        "spans": spans,
                        "y0": bbox[1],
                        "y1": bbox[3],
                    })
        page_texts.append(page_lines)
    _drop_running_lines(page_texts, heights)
    all_spans = [span for page_lines in page_texts for line in page_lines for span in line["spans"]]

    # 检查是否扫描件
    has_text = any(lines for lines in page_texts)
    if not has_text:
        return ParseResult(
            warnings=["PDF 不含可提取文本，可能是扫描件；请上传文字版或先通过知识库 OCR"],
            needs_ocr=True,
            file_hash=file_hash,
        )

    warnings: list[str] = []
    try:
        toc = doc.get_toc(simple=True)
    except Exception:  # 书签目录损坏：按字号识别
        logger.warning("PDF 书签目录读取失败，改按字号识别标题", exc_info=True)
        toc = []
    sections = _sections_from_outline(page_texts, toc, warnings) if toc else []
    if not sections:
        sections = _sections_from_fonts(page_texts, all_spans)

    # 有可提取文本时必产出章节（无标题正文进「（无标题）」人工确认章）——这就是降级形态。
    # 原「纯文本降级」分支挂在 `if not sections` 之后，永远不可达，第 7 组整体复盘删除。
    if len(sections) > MAX_SECTIONS:
        warnings.append(f"解析章节数 {len(sections)} 超过上限 {MAX_SECTIONS}，已截断")  # 首版静默截断
        sections = sections[:MAX_SECTIONS]

    for s in sections:
        s.html = sanitize_note_html(s.html)

    doc.close()
    return ParseResult(sections=sections, warnings=warnings, file_hash=file_hash)


def _sections_from_outline(page_texts: list[list[dict[str, Any]]], toc: list[list],
                           warnings: list[str]) -> list[ParsedSection]:
    """按书签目录切章（AC-1.6）：书签 = 作者给的章节树，标题 / 层级取书签，正文 = 两个标题行之间的行。"""
    headings, noise = outline_headings(toc, heading_rank)
    if noise:
        names = "、".join(f"「{entry.title}」" for entry in noise[:5]) + (" 等" if len(noise) > 5 else "")
        warnings.append(f"PDF 书签有 {len(noise)} 条无编号条目与带编号的同级书签并列"
                        f"（多为表格单元格误设了大纲级别），未作为标题：{names}")
    lines = [line["text"] for page_lines in page_texts for line in page_lines]
    page_starts = [0]
    for page_lines in page_texts:
        page_starts.append(page_starts[-1] + len(page_lines))
    hits, missing = locate_heading_lines(lines, page_starts, headings)
    warnings.extend(missing)
    if not hits:
        warnings.append("PDF 书签与正文对不上，改按字号 / 加粗识别标题")
        return []

    def body(start: int, stop: int) -> str:
        return "".join(f"<p>{html_escape(text)}</p>" for text in lines[start:stop])

    sections: list[ParsedSection] = []
    if hits[0][1] > 0:
        sections.append(ParsedSection(source_id="pdf-s1", title="（无标题）", level=1, html=body(0, hits[0][1]),
                                      confidence="manual_required"))
    for n, (heading, _first, last) in enumerate(hits):
        stop = hits[n + 1][1] if n + 1 < len(hits) else len(lines)
        sections.append(ParsedSection(source_id=f"pdf-s{len(sections) + 1}", title=heading.title, level=heading.level,
                                      html=body(last + 1, stop), confidence="candidate",
                                      metadata={"page": heading.page}))
    return sections


def _sections_from_fonts(page_texts: list[list[dict[str, Any]]],
                         all_spans: list[dict[str, Any]]) -> list[ParsedSection]:
    """无书签时按字号 / 加粗识别标题（AC-1.3）。"""
    body_size = _body_font_size(all_spans)

    sections: list[ParsedSection] = []
    current: ParsedSection | None = None
    section_idx = 0

    for page_lines in page_texts:
        for line in page_lines:
            text = line["text"]
            size = line["size"]
            is_bold = line["bold"]

            # 标题候选：字号明显大于正文字号，或加粗 + 中文章节模式；层级按编号排位，无编号按字号（AC-1.6）
            is_heading = False
            level = 2
            if size > body_size * 1.3:
                is_heading = True
                level = heading_rank(text) or (1 if size > body_size * 1.6 else 2)
            elif is_bold and _CN_HEADING_RE.match(text) and len(text) < 60:
                is_heading = True
                level = heading_rank(text) or 2

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
    return sections


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
    """解析 Markdown / HTML / 纯文本来源。

    依次尝试 Markdown 标题 → HTML 标题 → 中文章节号 → 整篇单段降级；**所有分支只有一个出口**做消毒、
    剥模板标记与来源标识（首版每个分支各自消毒，HTML 分支的原始标签只靠其中一道，去掉也没有测试发现）。
    """
    if not text or not text.strip():
        return ParseResult(warnings=["来源正文为空"])

    warnings: list[str] = []
    sections = _parse_markdown_headings(text) or _parse_html_headings(text) or _parse_cn_headings(text)
    if not sections:
        sections = [ParsedSection(
            source_id="text-s1",
            title=doc_name or "（无标题）",
            level=1,
            html=f"<p>{html_escape(text.strip()[:10_000])}</p>",
            confidence="manual_required",
        )]
        warnings.append("无法识别标题结构，整篇作为单个候选章节")

    for s in sections:
        s.html = sanitize_note_html(s.html)
        s.metadata["source_kind"] = source_kind
        if doc_id:
            s.metadata["doc_id"] = doc_id
    return ParseResult(sections=sections, warnings=warnings)


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
            html=body,  # 原始 HTML，由 parse_text_source 统一出口消毒
            confidence="candidate",
        ))

    return sections


def _parse_cn_headings(text: str) -> list[ParsedSection]:
    """按中文章节号模式分章（纯文本）；层级按编号排位成树（AC-1.6，首版一律 2 级、不成树）。"""
    sections: list[ParsedSection] = []
    current_title = ""
    current_lines: list[str] = []
    idx = 0

    def flush() -> None:
        nonlocal idx
        idx += 1
        sections.append(ParsedSection(
            source_id=f"cn-s{idx}",
            title=current_title or "（无标题）",
            level=(heading_rank(current_title) or 2) if current_title else 1,
            html="".join(f"<p>{html_escape(body)}</p>" for body in current_lines),
            confidence="candidate" if current_title else "manual_required",
        ))

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if _CN_HEADING_RE.match(line) and len(line) < 80:
            if current_lines or current_title:
                flush()
                current_lines = []
            current_title = line
        else:
            current_lines.append(line)

    if current_lines or current_title:
        flush()

    return sections
