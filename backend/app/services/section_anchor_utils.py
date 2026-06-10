"""段落锚点命名双向映射工具（出品物溯源与回填 - 组件 2）.

OOXML 书签名禁空格，用确定性替换保证可逆。
与前端 `useDeliverableLineage.ts` 的 `anchorNameFromSectionCode` /
`sectionCodeFromAnchor` 镜像一致。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from docx.document import Document as DocumentObject
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph


# ---------------------------------------------------------------------------
# 双向映射：section_code ↔ anchor_name
# ---------------------------------------------------------------------------


def anchor_name(section_code: str) -> str:
    """section_code → 安全锚点名。'八、1' → 'sec_八_1'。

    OOXML 书签名禁空格，用确定性替换保证可逆。
    规则：strip + '、' → '_' + 空格去除 + '·' → '_'
    """
    safe = section_code.strip().replace("、", "_").replace(" ", "").replace("·", "_")
    return f"sec_{safe}"


def section_code_from_anchor(name: str) -> str | None:
    """逆映射：'sec_八_1' → '八、1'（结合 section_code_index 校验存在性）。

    规则：去 'sec_' 前缀 → 找中文字符后紧跟的首个 '_' 恢复为 '、'。
    与前端 useDeliverableLineage.ts 逻辑镜像一致。
    """
    if not name or not name.startswith("sec_"):
        return None
    body = name[4:]  # strip "sec_"
    if not body:
        return None
    # 找中文字符后紧跟的 '_' → 恢复为 '、'
    m = re.search(r"([\u4e00-\u9fff])_", body)
    if m:
        pos = m.start() + 1  # '_' 的位置
        return body[:pos] + "、" + body[pos + 1 :]
    # Fallback: 替换第一个 '_' 为 '、'
    idx = body.find("_")
    if idx > 0:
        return body[:idx] + "、" + body[idx + 1 :]
    return body


# ---------------------------------------------------------------------------
# 书签写入：write_section_anchors
# ---------------------------------------------------------------------------


@dataclass
class SectionBlock:
    """一个 SECTION 块引用（用于锚点写入）。"""

    section_code: str
    open_el: Any
    close_el: Any


def write_section_anchors(
    doc: DocumentObject,
    kept_blocks: list[SectionBlock],
    *,
    start_id: int = 1000,
) -> dict[str, str]:
    """为每个保留章节写入隐藏书签（bookmarkStart / bookmarkEnd）。

    在 open_el 前插入 ``<w:bookmarkStart>``，close_el 后插入 ``<w:bookmarkEnd>``。
    书签名 = ``anchor_name(section_code)``。

    仅对 kept_blocks 写锚点（被裁剪删除章节不写）。
    书签保持隐藏不影响可见正文。

    Parameters
    ----------
    doc : DocumentObject
        python-docx Document 对象。
    kept_blocks : list[SectionBlock]
        保留章节的块列表（含 open_el / close_el）。
    start_id : int
        书签 ID 起始值（避免与 Word 内部书签冲突）。

    Returns
    -------
    dict[str, str]
        section_code → anchor_name 的映射（供同步到 deliverable_section_state）。
    """
    body = doc.element.body
    anchor_map: dict[str, str] = {}

    for i, block in enumerate(kept_blocks):
        bm_name = anchor_name(block.section_code)
        bm_id = start_id + i

        # 创建 bookmarkStart
        bm_start = OxmlElement("w:bookmarkStart")
        bm_start.set(qn("w:id"), str(bm_id))
        bm_start.set(qn("w:name"), bm_name)

        # 创建 bookmarkEnd
        bm_end = OxmlElement("w:bookmarkEnd")
        bm_end.set(qn("w:id"), str(bm_id))

        # 在 open_el 之前插入 bookmarkStart
        body.insert(list(body).index(block.open_el), bm_start)

        # 在 close_el 之后插入 bookmarkEnd
        close_idx = list(body).index(block.close_el)
        body.insert(close_idx + 1, bm_end)

        anchor_map[block.section_code] = bm_name

    return anchor_map
