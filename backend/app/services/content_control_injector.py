"""交付 docx 章节内容控件注入器 — deliverable-lineage-content-control Task 2.

把交付 docx 中每节的 body 级块范围（open_el..close_el，来自
``word_doc_utils.scan_section_blocks``）外层包一个 Block Content Control
（``w:sdt``，``Tag = anchor_name(section_code)``），供前端 OnlyOffice 连接器
``onChangeContentControl`` / ``GetCurrentContentControl`` 实现真·光标跟随溯源。

设计铁律（deliverable-lineage-content-control design）：
- 纯 oxml 操作，不改章节可见文本/样式/段落顺序（仅在块范围外层加 w:sdt 包裹）。
- Tag 复用 ``section_anchor_utils.anchor_name`` 单一真源（与前端命名镜像一致）。
- 与既有 bookmark 并存（本模块不动 bookmark）。
- 空范围/无法定位/异常 → 逐节 fail-open（返回 False，不抛、不破坏其余章节）。
- 幂等：块已在同 Tag 的 w:sdtContent 内则跳过（不嵌套叠加）。
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from docx.document import Document as DocumentObject
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from app.services.section_anchor_utils import anchor_name

logger = logging.getLogger(__name__)

# w:sdt id 起始值（避开 bookmark id 段 1000+，且落在 32-bit 有符号范围内）
_SDT_ID_START = 900000


def _already_wrapped(open_el: Any, tag: str) -> bool:
    """open_el 是否已在同 Tag 的 w:sdtContent 内（幂等判定）。"""
    parent = open_el.getparent()
    if parent is None or parent.tag != qn("w:sdtContent"):
        return False
    sdt = parent.getparent()
    if sdt is None or sdt.tag != qn("w:sdt"):
        return False
    pr = sdt.find(qn("w:sdtPr"))
    if pr is None:
        return False
    tag_el = pr.find(qn("w:tag"))
    return tag_el is not None and tag_el.get(qn("w:val")) == tag


def _build_sdt(tag: str, sdt_id: int) -> Any:
    """构造带 Tag/alias/id 的空 w:sdt（含空 w:sdtContent）。"""
    sdt = OxmlElement("w:sdt")
    sdt_pr = OxmlElement("w:sdtPr")

    alias = OxmlElement("w:alias")
    alias.set(qn("w:val"), tag)
    tag_el = OxmlElement("w:tag")
    tag_el.set(qn("w:val"), tag)
    id_el = OxmlElement("w:id")
    id_el.set(qn("w:val"), str(sdt_id))

    sdt_pr.append(alias)
    sdt_pr.append(tag_el)
    sdt_pr.append(id_el)
    sdt.append(sdt_pr)

    sdt.append(OxmlElement("w:sdtContent"))
    return sdt


def wrap_block_range(
    body: Any,
    open_el: Any,
    close_el: Any,
    tag: str,
    *,
    sdt_id: int = _SDT_ID_START,
) -> bool:
    """把 body 级 [open_el..close_el] 元素范围包进一个 w:sdt（Tag=tag）。

    Returns
    -------
    bool
        True=已注入；False=无法定位/空范围/已包裹（幂等）—— 均不抛。
    """
    if body is None or open_el is None or close_el is None or not tag:
        return False

    children = list(body)
    try:
        open_idx = children.index(open_el)
        close_idx = children.index(close_el)
    except ValueError:
        # open/close 不是 body 直接子元素（如嵌套表格内）→ fail-open
        return False

    if open_idx > close_idx:
        return False

    if _already_wrapped(open_el, tag):
        return False

    # 先固定范围内元素引用（移动前）
    rng = children[open_idx : close_idx + 1]

    sdt = _build_sdt(tag, sdt_id)
    sdt_content = sdt.find(qn("w:sdtContent"))

    # 在 open_el 位置插入 sdt，再把范围元素依序移入 sdtContent（保持顺序与内容不变）
    body.insert(open_idx, sdt)
    for el in rng:
        body.remove(el)
        sdt_content.append(el)

    return True


def inject_content_controls_for_blocks(
    doc: DocumentObject,
    blocks: Iterable[Any],
    *,
    start_id: int = _SDT_ID_START,
) -> int:
    """为 ``scan_section_blocks`` 的每个块把「开闭标记之间的内部内容」包进 w:sdt。

    关键：**只包内部内容**（``block.elements[1:-1]``），保留开闭标记段落在 body 级，
    使后续 ``remove_section_markers``（遍历 body 级 doc.paragraphs，不下钻 SDT）
    仍能正常清理标记。无内部内容（仅开闭标记）的块跳过。

    Parameters
    ----------
    blocks : Iterable
        ``word_doc_utils.scan_section_blocks`` 输出（含 ``section_code`` / ``elements``）。

    Returns
    -------
    int
        成功注入的章节数。
    """
    body = doc.element.body
    count = 0
    for i, block in enumerate(blocks):
        code = getattr(block, "section_code", "") or ""
        els = list(getattr(block, "elements", None) or [])
        if not code or len(els) <= 2:
            # 无内部内容（仅开/闭标记）→ 无需包裹
            continue
        inner_first = els[1]
        inner_last = els[-2]
        tag = anchor_name(code)
        try:
            if wrap_block_range(body, inner_first, inner_last, tag, sdt_id=start_id + i):
                count += 1
        except Exception as e:  # noqa: BLE001 — 逐节 fail-open
            logger.debug("inject inner content control skipped section=%s: %s", code, e)
    return count


def wrap_all_sections(
    doc: DocumentObject,
    blocks: Iterable[Any],
    *,
    start_id: int = _SDT_ID_START,
) -> int:
    """为每个章节块注入内容控件；逐块 fail-open。

    Parameters
    ----------
    doc : DocumentObject
        python-docx Document。
    blocks : Iterable
        鸭子类型对象，需含 ``section_code`` / ``open_el`` / ``close_el``
        （来自 ``word_doc_utils.scan_section_blocks``）。
    start_id : int
        w:sdt id 起始值。

    Returns
    -------
    int
        成功注入的章节数。
    """
    body = doc.element.body
    count = 0
    for i, block in enumerate(blocks):
        code = getattr(block, "section_code", "") or ""
        open_el = getattr(block, "open_el", None)
        close_el = getattr(block, "close_el", None)
        if not code:
            continue
        tag = anchor_name(code)
        try:
            if wrap_block_range(body, open_el, close_el, tag, sdt_id=start_id + i):
                count += 1
        except Exception as e:  # noqa: BLE001 — 逐节 fail-open，不影响其余章节
            logger.debug("content control inject skipped section=%s: %s", code, e)
    return count
