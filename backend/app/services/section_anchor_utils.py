"""段落锚点命名双向映射工具（出品物溯源与回填 - 组件 2）.

OOXML 书签名禁空格，用确定性替换保证可逆。
与前端 `useDeliverableLineage.ts` 的 `anchorNameFromSectionCode` /
`sectionCodeFromAnchor` 镜像一致。
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from docx.document import Document as DocumentObject
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

logger = logging.getLogger(__name__)

#: 章节锚点书签名前缀（与 ``anchor_name`` 一致；用于从文档中筛出本平台写入的锚点，
#: 避免把 Word 内部书签 / 附注 note bookmark 误当章节锚点）。
SECTION_ANCHOR_PREFIX = "sec_"

#: **其他交付件类型**的锚点命名空间 —— 同样以 ``sec_`` 开头，但其后不是附注章节码。
#:
#: 为什么要这张表：``scan_anchor_blocks`` 按 ``sec_`` 前缀收锚点，而报告正文的锚点
#: （``sec_rb_opinion``）也满足该前缀 → 若不排除，附注回填会把它反解成章节码
#: ``rb_opinion`` 去 ``disclosure_notes`` 里找（必然 0 行、落 failed 桶），
#: 更坏的情况是反解出的字符串恰好撞上某个真实章节 ⇒ **把报告正文的文字写进附注**。
#:
#: 新增交付件类型时必须在此登记；`report_body_section_blocks` 有交叉锁死守卫。
FOREIGN_ANCHOR_PREFIXES: tuple[str, ...] = ("sec_rb_",)

_NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


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
    namer: Callable[[str], str] | None = None,
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
    namer : Callable[[str], str] | None
        锚点命名器，默认 :func:`anchor_name`（附注命名空间 ``sec_``）。

        **报告正文必须传自己的命名器**（``report_body_anchor_name`` → ``sec_rb_*``）：
        报告正文的 section_id 是 ``opinion`` / ``basis`` 这类英文标识，若沿用附注命名器
        会写出 ``sec_opinion`` —— 与附注章节码域**撞命名空间**，导致附注回填的
        :func:`scan_anchor_blocks` 把它反解成章节码 ``opinion`` 并去 ``disclosure_notes``
        找该章节（必然 0 行 → 落 failed 桶）。见 ``FOREIGN_ANCHOR_PREFIXES``。

    Returns
    -------
    dict[str, str]
        section_code → anchor_name 的映射（供同步到 deliverable_section_state）。
    """
    body = doc.element.body
    anchor_map: dict[str, str] = {}
    name_of = namer or anchor_name

    for i, block in enumerate(kept_blocks):
        bm_name = name_of(block.section_code)
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


# ---------------------------------------------------------------------------
# 锚点区间扫描：scan_anchor_blocks（标记清理后唯一可用的章节定位手段）
# ---------------------------------------------------------------------------


@dataclass
class AnchorBlock:
    """由一对 ``sec_*`` 书签界定的章节区间。

    交付 docx 在导出末尾会 ``remove_section_markers`` 清掉 ``##SECTION:`` 标记，
    此后 ``scan_section_blocks`` 再也定位不到章节 —— 本结构是标记清理后唯一
    可用的定位手段（回填 / 增量刷新 / 溯源均依赖它）。

    ``containers`` 是 body 级容器元素（``w:p`` / ``w:tbl`` / ``w:sdt``），用于结构性
    插入 / 删除；``elements`` 是展平后的内容元素（``w:p`` / ``w:tbl``，含内容控件
    ``w:sdt`` 内部的），用于文字提取与哈希 —— 二者刻意分开：内容控件开启时章节
    内部内容被包进 ``w:sdt``，只看 body 级会把整节看成一个不可读的容器。
    """

    section_code: str
    anchor_name: str
    start_el: Any
    end_el: Any
    containers: list[Any] = field(default_factory=list)
    elements: list[Any] = field(default_factory=list)


def _flatten_content_elements(containers: list[Any]) -> list[Any]:
    """展平 body 级容器 → 内容元素（下钻 ``w:sdt/w:sdtContent``）。"""
    p_tag = qn("w:p")
    tbl_tag = qn("w:tbl")
    sdt_tag = qn("w:sdt")
    sdt_content_tag = qn("w:sdtContent")

    out: list[Any] = []
    for el in containers:
        if el.tag == sdt_tag:
            for content in el.iterchildren(sdt_content_tag):
                for child in content.iterchildren():
                    if child.tag in (p_tag, tbl_tag):
                        out.append(child)
        elif el.tag in (p_tag, tbl_tag):
            out.append(el)
    return out


def scan_anchor_blocks(doc: DocumentObject) -> list[AnchorBlock]:
    """按 Section_Anchor 扫描章节区间（body 级，含内容控件内部）。

    只认名以 ``sec_`` 开头的书签（``SECTION_ANCHOR_PREFIX``）；其余书签（Word 内部、
    附注 note bookmark）一律忽略。

    健壮性约定：

    - 无锚点 → 返回 ``[]``（不抛异常）；
    - 锚点名反解 ``section_code`` 失败 → 跳过该锚点 + warning，其余照常；
    - 同一 ``section_code`` 出现多个锚点 → 取**首个** + warning，**禁止静默合并**
      （合并会让回填把两段内容拼起来写回同一章节）；
    - ``bookmarkStart`` 无匹配 ``bookmarkEnd`` → 跳过 + warning。
    """
    body = doc.element.body
    bm_start_tag = qn("w:bookmarkStart")
    bm_end_tag = qn("w:bookmarkEnd")
    id_attr = qn("w:id")
    name_attr = qn("w:name")
    container_tags = (qn("w:p"), qn("w:tbl"), qn("w:sdt"))

    open_map: dict[str, dict[str, Any]] = {}
    results: list[AnchorBlock] = []
    seen_codes: set[str] = set()

    for child in body.iterchildren():
        tag = child.tag

        if tag == bm_start_tag:
            name = child.get(name_attr) or ""
            if not name.startswith(SECTION_ANCHOR_PREFIX):
                continue
            # 排除其他交付件类型的锚点命名空间（报告正文 sec_rb_* 等）。
            # 不排除会让附注回填反解出伪章节码并去 disclosure_notes 找，
            # 见 FOREIGN_ANCHOR_PREFIXES 的说明。
            if name.startswith(FOREIGN_ANCHOR_PREFIXES):
                continue
            bm_id = child.get(id_attr) or ""
            open_map[bm_id] = {
                "name": name,
                "start_el": child,
                "containers": [],
            }
            continue

        if tag == bm_end_tag:
            bm_id = child.get(id_attr) or ""
            info = open_map.pop(bm_id, None)
            if info is None:
                continue
            code = section_code_from_anchor(info["name"])
            if not code:
                logger.warning(
                    "scan_anchor_blocks: 锚点名无法反解 section_code，跳过: %s",
                    info["name"],
                )
                continue
            if code in seen_codes:
                logger.warning(
                    "scan_anchor_blocks: section_code 重复出现多个锚点，取首个: %s",
                    code,
                )
                continue
            seen_codes.add(code)
            containers = info["containers"]
            results.append(
                AnchorBlock(
                    section_code=code,
                    anchor_name=info["name"],
                    start_el=info["start_el"],
                    end_el=child,
                    containers=containers,
                    elements=_flatten_content_elements(containers),
                )
            )
            continue

        if tag in container_tags:
            for info in open_map.values():
                info["containers"].append(child)

    for bm_id, info in open_map.items():
        logger.warning(
            "scan_anchor_blocks: 锚点 %s (id=%s) 无匹配 bookmarkEnd，跳过",
            info["name"],
            bm_id,
        )

    return results


def anchor_block_content_host(block: AnchorBlock) -> tuple[Any, list[Any]]:
    """返回 ``(插入宿主元素, 宿主下当前内容元素列表)``。

    内容控件开启时章节内部内容被包在单个 ``w:sdt`` 里，刷新必须写进
    ``w:sdtContent`` **内部** —— 否则新内容落在控件外，Tag 覆盖不到它，
    光标跟随溯源对刷新后的内容失效。

    - 恰有一个 ``w:sdt`` 容器 → ``(sdtContent, 其 w:p/w:tbl 子元素)``；
    - 其余情形 → ``(body, block.containers)``。
    """
    sdt_tag = qn("w:sdt")
    sdt_content_tag = qn("w:sdtContent")
    p_tag = qn("w:p")
    tbl_tag = qn("w:tbl")

    sdts = [el for el in block.containers if el.tag == sdt_tag]
    if len(sdts) == 1:
        for content in sdts[0].iterchildren(sdt_content_tag):
            children = [
                c for c in content.iterchildren() if c.tag in (p_tag, tbl_tag)
            ]
            return content, children

    parent = block.start_el.getparent()
    return parent, list(block.containers)


# ---------------------------------------------------------------------------
# 块定位降级链：resolve_section_blocks
# ---------------------------------------------------------------------------

BlockLocateMode = Literal["anchor", "marker", "none"]


def resolve_section_blocks(
    doc: DocumentObject,
) -> tuple[BlockLocateMode, list[Any]]:
    """统一章节块定位：锚点优先、``##SECTION:`` 标记回退。

    交付件的正常形态是「标记已清、锚点存在」→ ``anchor``；存量交付件（本 spec
    接线前生成）两者皆无 → ``none``；模板 / 中间态文档标记仍在 → ``marker``。

    返回的块对象统一鸭子类型：``.section_code`` + ``.elements``（内容元素列表）。
    """
    anchors = scan_anchor_blocks(doc)
    if anchors:
        return "anchor", list(anchors)

    from app.services.word_doc_utils import scan_section_blocks

    markers = scan_section_blocks(doc)
    if markers:
        return "marker", list(markers)

    return "none", []


# ---------------------------------------------------------------------------
# 块内文字规范化与哈希（Rendered_Block_Hash 单一真源）
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"[ \t\u3000]+")


def block_text_of(elements: list[Any]) -> str:
    """提取块内段落文字（排除 ``##SECTION:``/``##/SECTION:`` 标记行、跳过表格）。

    只取 ``w:p``：表格数字不参与人工编辑判定，也不参与回填（合规护栏一律拒绝
    表格数字写回，改动只能走调整分录）。
    """
    p_tag = qn("w:p")
    parts: list[str] = []
    for el in elements:
        if el.tag != p_tag:
            continue
        text = "".join(t.text or "" for t in el.iter(f"{{{_NS_W}}}t")).strip()
        if not text or text.startswith("##"):
            continue
        parts.append(text)
    return "\n".join(parts)


def normalize_block_text(text: str) -> str:
    """规范化块内文字：统一换行 + 合并行内空白 + 去空行与首尾空白。"""
    if not text:
        return ""
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_WS_RE.sub(" ", line).strip() for line in unified.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def block_text_hash(elements: list[Any]) -> str:
    """Rendered_Block_Hash：``sha256(规范化块内文字)``。

    **导出侧与人工编辑检测侧必须共用本函数** —— 各写一份必然哈希域漂移
    （历史缺陷：``_detect_user_edits`` 拿 ``sha256(块内纯文本)`` 去比
    ``sha256(json{section_code,text_content,table_data,audited_amounts})``，
    两个哈希域根本不同 ⇒ 永远不等 ⇒ 刷新恒要求确认覆盖）。
    """
    normalized = normalize_block_text(block_text_of(elements))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
