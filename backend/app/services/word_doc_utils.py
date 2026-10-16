"""Word 模板占位符 / OPT / NOTE 底层工具（TemplateFillService 共用）."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from docx.document import Document as DocumentObject
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

PLACEHOLDER_RE = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")
OPT_OPEN_RE = re.compile(r"^##OPT:([^:#]+)(?::([^#]*))?##\s*$")
OPT_CLOSE_RE = re.compile(r"^##/OPT:([^#]+)##\s*$")
NOTE_OPEN_RE = re.compile(r"^##NOTE(?::([^#]*))?##\s*$")
NOTE_CLOSE_RE = re.compile(r"^##/NOTE(?::([^#]*))?##\s*$")
# 行内 NOTE（单行剥除）
NOTE_INLINE_RE = re.compile(r"##NOTE(?::[^#]*)?##.*?##/NOTE(?:#[^#]*)?##", re.DOTALL)

# 附注 ``##SECTION:code##`` / ``##/SECTION:code##`` 块（Phase 0.6.2 打标产出）
SECTION_OPEN_RE = re.compile(r"^##SECTION:(.+?)##\s*$")
SECTION_CLOSE_RE = re.compile(r"^##/SECTION:(.+?)##\s*$")
# 参考表样式标记（克隆后删除）
STYLE_REF_RE = re.compile(r"##/?STYLE_REF:[^#]*##")


@dataclass(frozen=True)
class OptionalSection:
    section_id: str
    description: str
    start_index: int
    end_index: int  # exclusive


def _iter_paragraphs(doc: DocumentObject) -> Iterable[Paragraph]:
    for para in doc.paragraphs:
        yield para
    for table in doc.tables:
        yield from _iter_table_paragraphs(table)
    for section in doc.sections:
        for part in (section.header, section.footer):
            if part is None:
                continue
            for para in part.paragraphs:
                yield para
            for table in part.tables:
                yield from _iter_table_paragraphs(table)


def _iter_table_paragraphs(table: Table) -> Iterable[Paragraph]:
    for row in table.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                yield para
            for nested in cell.tables:
                yield from _iter_table_paragraphs(nested)


def merge_runs_for_replace(paragraph: Paragraph) -> None:
    """合并段落内 runs，避免 ``{{key}}`` 被 Word 拆成多 run 无法替换.

    合并策略：将全部文本合并到第一个 run，清空后续 run。
    字体保留：使用**文本最长的 run** 的字体属性覆盖第一个 run（避免格式标记 run 的字体污染正文）。
    """
    if len(paragraph.runs) <= 1:
        return
    combined = paragraph.text
    if "{{" not in combined and "{" not in combined:
        return

    # 找到文本最长的 run 作为字体来源（正文 run 通常最长）
    longest_run = max(paragraph.runs, key=lambda r: len(r.text))
    first = paragraph.runs[0]
    first.text = combined

    # 如果最长 run 与第一个 run 不同，且最长 run 有显式字体设置，复制其字体属性
    if longest_run is not first and longest_run.font.name:
        from copy import deepcopy
        from docx.oxml.ns import qn
        # 复制 rPr (run properties) XML 元素
        source_rpr = longest_run._r.find(qn("w:rPr"))
        if source_rpr is not None:
            existing_rpr = first._r.find(qn("w:rPr"))
            if existing_rpr is not None:
                first._r.remove(existing_rpr)
            first._r.insert(0, deepcopy(source_rpr))

    for run in paragraph.runs[1:]:
        run.text = ""


def merge_runs_in_doc(doc: DocumentObject) -> None:
    for para in _iter_paragraphs(doc):
        merge_runs_for_replace(para)


def replace_placeholders_in_doc(doc: DocumentObject, mapping: dict[str, str]) -> int:
    """全文替换 ``{{canonical_key}}``；返回替换次数."""
    merge_runs_in_doc(doc)
    count = 0
    for para in _iter_paragraphs(doc):
        text = para.text
        if "{{" not in text:
            continue
        new_text = text
        for key, value in mapping.items():
            token = f"{{{{{key}}}}}"
            if token in new_text:
                count += new_text.count(token)
                new_text = new_text.replace(token, value or "")
        if new_text != text:
            if para.runs:
                para.runs[0].text = new_text
                for run in para.runs[1:]:
                    run.text = ""
            else:
                para.add_run(new_text)
    return count


def scan_optional_sections(doc: DocumentObject) -> list[OptionalSection]:
    """解析 ``##OPT:id:desc## … ##/OPT:id##`` 块（段落级）."""
    paras = list(doc.paragraphs)
    sections: list[OptionalSection] = []
    i = 0
    while i < len(paras):
        text = (paras[i].text or "").strip()
        m_open = OPT_OPEN_RE.match(text)
        if not m_open:
            i += 1
            continue
        sec_id = m_open.group(1).strip()
        desc = (m_open.group(2) or "").strip()
        j = i + 1
        while j < len(paras):
            close_text = (paras[j].text or "").strip()
            m_close = OPT_CLOSE_RE.match(close_text)
            if m_close and m_close.group(1).strip() == sec_id:
                sections.append(
                    OptionalSection(sec_id, desc, i, j + 1)
                )
                i = j + 1
                break
            j += 1
        else:
            i += 1
    return sections


def _delete_paragraph(para: Paragraph) -> None:
    element = para._element
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def iter_all_paragraphs(doc: DocumentObject) -> list[Paragraph]:
    """body 下全部段落（文档顺序，含表格单元格与内容控件 ``w:sdt`` 里的段落）。

    ``doc.paragraphs`` / ``doc.tables`` 只给 body 直接子元素：交付导出把每节内容包进内容控件后
    （``DELIVERABLE_LINEAGE_CONTENT_CONTROL_ENABLED`` 默认开），块内段落全在 ``w:sdt`` 里，按它清理就漏掉
    ``##STYLE_REF##`` 与未填充占位符（第 26 组：真实项目交付件残留 100~200 处）。返回列表，调用方可删段落。
    """
    return [Paragraph(el, doc) for el in doc.element.body.iter(qn("w:p"))]


_BLOCK_LEVEL_TAGS = (qn("w:p"), qn("w:tbl"))
_KEPT_WHEN_CLEARED = (qn("w:pPr"), qn("w:bookmarkStart"), qn("w:bookmarkEnd"))


def _drop_paragraph(para: Paragraph) -> None:
    """删除标记段落。body 级照旧直接删；嵌套段落（单元格 / 内容控件里）删了会坏结构时只清空文字：
    它是容器里唯一的块级元素（``w:tc`` 至少要一个段落，否则 Word 报内容损坏），或段落里有书签。"""
    element = para._element
    parent = element.getparent()
    if parent is None:
        return
    if parent.tag != qn("w:body"):
        only_block = sum(1 for child in parent if child.tag in _BLOCK_LEVEL_TAGS) == 1
        has_bookmark = any(child.tag in _KEPT_WHEN_CLEARED[1:] for child in element)
        if only_block or has_bookmark:
            for child in list(element):
                if child.tag not in _KEPT_WHEN_CLEARED:
                    element.remove(child)
            return
    parent.remove(element)


def apply_optional_sections(
    doc: DocumentObject,
    selections: dict[str, bool],
) -> int:
    """删除未勾选 OPT 块；保留块去除开闭标记行。返回删除段落数."""
    removed = 0
    # 从后往前处理避免索引漂移
    for sec in reversed(scan_optional_sections(doc)):
        keep = selections.get(sec.section_id, False)
        paras = doc.paragraphs
        if keep:
            # 去掉标记行文字
            for idx in (sec.end_index - 1, sec.start_index):
                if 0 <= idx < len(paras):
                    paras[idx].clear()
            continue
        for idx in range(sec.end_index - 1, sec.start_index - 1, -1):
            if 0 <= idx < len(paras):
                _delete_paragraph(paras[idx])
                removed += 1
    return removed


def strip_guidance_notes(doc: DocumentObject) -> int:
    """删除 ``##NOTE:…##`` 块及行内 NOTE；合法 ``[注1]`` 保留。返回删除段落数."""
    removed = 0
    while True:
        paras = doc.paragraphs
        deleted_block = False
        for i, para in enumerate(paras):
            text = (para.text or "").strip()
            m_open = NOTE_OPEN_RE.match(text)
            if m_open:
                label = m_open.group(1)
                for j in range(i + 1, len(paras)):
                    close_text = (paras[j].text or "").strip()
                    m_close = NOTE_CLOSE_RE.match(close_text)
                    if m_close and (not label or m_close.group(1) == label):
                        for idx in range(j, i - 1, -1):
                            _delete_paragraph(doc.paragraphs[idx])
                            removed += 1
                        deleted_block = True
                        break
                if not deleted_block:
                    _delete_paragraph(paras[i])
                    removed += 1
                    deleted_block = True
                break
            if "##NOTE" in text and "##/NOTE" in text:
                new_text = NOTE_INLINE_RE.sub("", text).strip()
                if not new_text:
                    _delete_paragraph(para)
                    removed += 1
                else:
                    para.clear()
                    para.add_run(new_text)
                deleted_block = True
                break
        if not deleted_block:
            break
    return removed


def copy_template_to_workdir(src: Path, dest_dir: Path) -> Path:
    """复制模板到工作目录，保留元数据."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    return dest


# ---------------------------------------------------------------------------
# ##SECTION:code## 块解析（附注模板模式专用）
# ---------------------------------------------------------------------------


@dataclass
class SectionBlock:
    """一个 ``##SECTION:code##…##/SECTION:code##`` 块.

    ``elements`` 为块内（含开闭标记段落）的 body 级 XML 元素列表，
    按文档顺序排列（``<w:p>`` 段落与 ``<w:tbl>`` 表格交错）。
    ``open_el`` / ``close_el`` 为开闭标记段落的 XML 元素。
    """

    section_code: str
    open_el: Any
    close_el: Any
    elements: list[Any]


def _body_block_elements(doc: DocumentObject) -> list[Any]:
    """按文档顺序返回 body 下的段落 / 表格 XML 元素."""
    body = doc.element.body
    result: list[Any] = []
    p_tag = qn("w:p")
    tbl_tag = qn("w:tbl")
    for child in body.iterchildren():
        if child.tag in (p_tag, tbl_tag):
            result.append(child)
    return result


def scan_section_blocks(doc: DocumentObject) -> list[SectionBlock]:
    """解析全文 ``##SECTION:code##…##/SECTION:code##`` 块（body 级，含表格）.

    与 ``scan_optional_sections`` 不同：SECTION 块需覆盖块内**表格**（附注主体内容），
    因此遍历 body 级 XML 元素而非仅 ``doc.paragraphs``。
    标记文本写在 ``<w:p>`` 段落里；表格元素无标记文本会落入当前打开块的 elements。
    """
    p_tag = qn("w:p")
    blocks: list[SectionBlock] = []
    elements = _body_block_elements(doc)

    open_idx: int | None = None
    open_code: str | None = None
    for i, el in enumerate(elements):
        if el.tag != p_tag:
            continue
        text = (Paragraph(el, doc).text or "").strip()
        if open_idx is None:
            m_open = SECTION_OPEN_RE.match(text)
            if m_open:
                open_idx = i
                open_code = m_open.group(1).strip()
            continue
        # 已在块内，找匹配 close
        m_close = SECTION_CLOSE_RE.match(text)
        if m_close and m_close.group(1).strip() == open_code:
            blocks.append(
                SectionBlock(
                    section_code=open_code or "",
                    open_el=elements[open_idx],
                    close_el=el,
                    elements=elements[open_idx : i + 1],
                )
            )
            open_idx = None
            open_code = None
    return blocks


def delete_section_block(block: SectionBlock) -> int:
    """删除整个 SECTION 块（含开闭标记 + 块内所有段落 / 表格）。返回删除元素数."""
    removed = 0
    for el in block.elements:
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)
            removed += 1
    return removed


def remove_section_markers(doc: DocumentObject) -> int:
    """删除保留章节里残留的 ``##SECTION:##`` / ``##/SECTION:##`` 标记段落.

    同时清理行内 ``##STYLE_REF:##`` 标记文本。返回删除 / 清理的段落数。
    """
    touched = 0
    # 下钻内容控件与表格单元格：只看 doc.paragraphs 会漏掉 w:sdt 里的 ##STYLE_REF##（第 26 组）
    for para in iter_all_paragraphs(doc):
        text = (para.text or "").strip()
        if SECTION_OPEN_RE.match(text) or SECTION_CLOSE_RE.match(text):
            _drop_paragraph(para)
            touched += 1
            continue
        if "##STYLE_REF:" in text:
            new_text = STYLE_REF_RE.sub("", para.text).strip()
            if not new_text:
                _drop_paragraph(para)
            else:
                para.clear()
                para.add_run(new_text)
            touched += 1
    return touched
