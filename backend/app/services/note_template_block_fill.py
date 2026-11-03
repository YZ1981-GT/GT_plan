"""附注模板模式：按模板结构重建保留章节块（spec ``deliverable-trio-generation-accuracy`` §2）。

为什么需要（2026-10-16 四个真实项目模板模式导出逐块核对）
------------------------------------------------------
附注 docx 模板每个 ``##SECTION:code##`` 块里是：``{{seq}}`` 段、块标题（自动编号）、子标题（「（1）按账龄披露…」）、
表题、``##STYLE_REF##`` 标记、``{{table:code:N}}`` 表位 + 一张**样例表**、``{{section:code}}`` 正文位，以及编制指引、
示例段落（「A、期末，本公司…贴现金额为XXX元」）。旧导出只替换占位符，其余原样保留 ⇒ 交付件里库内表格后面紧跟
一张空样例表、指引与示例全在、``{{seq}}`` 填出的「1」与标题自动编号「1、」重复；无附注 / 未勾选的章节按模板原貌
输出；块结束标记之后的参考表（「受限制的货币资金明细」）不受任何处理；库内续表 / 额外表丢失。

本模块的做法：
1. 预处理：块尾内容（块结束标记之后、下一个块 / 一级标题之前）收进前一块；模板里未打标记、但与块标题同级的
   标题（上市「财务报表项目附注」章的「公允价值变动收益」等）包成合成块（编码 ``~LOOSE:{序}``）。
2. 删除：未匹配 / 未勾选 / 无交付内容的块整块删除，**一级标题保留**（章号由 Word 自动编号，删了会让后续章号错位）。
3. 重建保留块：只留块标题、对应库内有数表的表位（子标题 / 表题 + 表格）、过滤后的正文；其余模板内容删除；
   未对应表位的有数表追加在块内；字面编号子标题按保留顺序重排；编号重启转移到首个保留标题。
4. 表格：沿用 ``NoteWordExporter._render_table``（多级表头 / 数值格式 / 公式降级），再套模板样例表外观
   （表属性、列宽、最小行高、表头行重复、取消固定字号），合计行加粗。

``note_word_exporter`` 只改接线；本模块不访问数据库。

拆分（2026-10-16，行数门禁）：底层工具在 ``note_template_docx_base``，表格外观在 ``note_template_table_look``，
跨块文档处理在 ``note_template_doc_ops``；本模块保留块结构解析与块重建，并转出三者的公开函数（调用方照旧
``import app.services.note_template_block_fill as tbf``）。
"""

from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from app.services.note_title_hint import split_title_hint
from app.services.note_template_docx_base import (
    _CONT_RE,
    _has_sectpr,
    _heading_level,
    is_auto_numbered,
    _LIT_ENUM_RE,
    _norm_key,
    numbering_disabled,
    paragraph_text,
    _raw_text,
    _remove,
    _set_literal_number,
    _set_paragraph_text,
    _style_map,
    style_map,
    styles_by_id,
    _text,
    _transfer_restarts,
    _W_P,
    _W_TBL,
    _XML_SPACE,
)
from app.services.note_template_table_look import (
    apply_template_table_look,
    render_cloned_table,
    _header_rows,
)
from app.services.note_template_doc_ops import (
    absorb_trailing_content,
    capture_title_order,
    chapter_contents,
    collapse_empty_sections,
    DeliveryReport,
    empty_chapters,
    fill_boilerplate,
    insert_synthetic_block,
    keep_only_h1,
    LOOSE_PREFIX,
    rename_block_markers,
    renumber_literal_titles,
    replace_doc_placeholders,
    rewrite_cross_refs,
    strip_loose_guidance,
    SyntheticBlock,
    transfer_title_restarts,
    wrap_loose_regions,
)

__all__ = [
    "BlockRebuildStats",
    "DeliveryReport",
    "LOOSE_PREFIX",
    "SyntheticBlock",
    "absorb_trailing_content",
    "apply_template_table_look",
    "render_cloned_table",
    "block_layout",
    "caption_like",
    "caption_text",
    "capture_title_order",
    "chapter_contents",
    "collapse_empty_sections",
    "empty_chapters",
    "fill_boilerplate",
    "insert_synthetic_block",
    "is_auto_numbered",
    "keep_only_h1",
    "note_tables_indexed",
    "numbering_disabled",
    "paragraph_text",
    "rebuild_block",
    "rename_block_markers",
    "renumber_literal_titles",
    "replace_doc_placeholders",
    "rewrite_cross_refs",
    "strip_loose_guidance",
    "strip_title_guidance",
    "structure_like",
    "structure_titles",
    "style_map",
    "styles_by_id",
    "transfer_title_restarts",
    "wrap_loose_regions",
]

_STYLE_REF_RE = re.compile(r"^##STYLE_REF:[^#]*##$")
_SEQ_ONLY_RE = re.compile(r"^\{\{seq:[^}]+\}\}$")
_TABLE_PH_RE = re.compile(r"^\{\{table:(.+?)(?::(\d+))?\}\}$")
_SECTION_PH_RE = re.compile(r"^\{\{section:(.+?)\}\}$")
#: 表题只移除编制指引括注；「按费用性质列示」「损失以—号填列」「单位：万股」等是正式表题内容。
#: 章节标题采用更宽的 ``split_title_hint`` 用户口径，两者不能共用同一正则。
_CAPTION_GUIDE_RE = re.compile(
    r"\s*[（(]\s*(?:参考格式|注意\s*[:：]|针对|仅限于|可选择|注\s*[:：]|如无|如有|应当|以下不适用|不适用|只写|"
    r"披露格式参考|若)[^（）()]*[）)]"
)


@dataclass
class BlockRebuildStats:
    """单块重建统计（汇总进导出提醒）。"""

    tables_rendered: int = 0
    tables_cloned: int = 0  # 走克隆路径（列数一致、直接克隆样例表行）的表数
    extra_tables: int = 0
    unmatched_slots: int = 0
    template_elements_removed: int = 0
    text_rendered: bool = False


# ── 块结构 ───────────────────────────────────────────────────────────────────


@dataclass
class _Slot:
    order: int
    index: int | None = None  # {{table:code:N}} 的 N
    anchor: Any = None  # 表位占位段
    table: Any = None  # 模板样例表
    caption: Any = None  # 表题段
    subheading: Any = None  # 所属子标题段
    keys: tuple[str, ...] = ()


@dataclass
class _Layout:
    title: Any = None
    title_level: int | None = None
    h1: list[Any] = field(default_factory=list)
    seq: list[Any] = field(default_factory=list)
    seq_inline: list[Any] = field(default_factory=list)
    section_anchor: Any = None
    section_sub: Any = None  # 正文位所属子标题
    slots: list[_Slot] = field(default_factory=list)
    subheadings: list[Any] = field(default_factory=list)
    order: list[tuple[str, Any]] = field(default_factory=list)  # 模板顺序：("slot", _Slot) / ("text", None) / ("sub", el)


def _sub_parents(subs: list[Any], names: dict[str, str]) -> dict[int, Any]:
    """子标题 → 上级子标题（模板顺序里前面最近的更高级别标题）。"""
    out: dict[int, Any] = {}
    stack: list[tuple[int, Any]] = []
    for el in subs:
        lvl = _heading_level(el, names) or 99
        while stack and stack[-1][0] >= lvl:
            stack.pop()
        if stack:
            out[id(el)] = stack[-1][1]
        stack.append((lvl, el))
    return out


def _layout(block, names: dict[str, str]) -> _Layout:
    inner = block.elements[1:-1]
    lay = _Layout()
    levels = [lv for lv in (_heading_level(el, names) for el in inner) if lv and lv >= 2]
    has_h1 = any(_heading_level(el, names) == 1 for el in inner)
    # 块内含一级标题（「一、1 公司基本情况」）：一级标题就是块标题，其余标题都是子标题
    title_level = 1 if has_h1 else (min(levels) if levels else None)
    pending_caption = None
    pending_anchor: tuple[Any, int | None] | None = None
    current_sub = None
    in_bracket = False
    for el in inner:
        if el.tag == _W_TBL:
            slot = _Slot(order=len(lay.slots), table=el, caption=pending_caption, subheading=current_sub)
            if pending_anchor is not None:
                slot.anchor, slot.index = pending_anchor
            lay.slots.append(slot)
            lay.order.append(("slot", slot))
            pending_caption = pending_anchor = None
            continue
        text = _text(el)
        lvl = _heading_level(el, names)
        if lvl == 1:
            lay.h1.append(el)
            if lay.title is None:
                lay.title, lay.title_level = el, 1
            continue
        if _STYLE_REF_RE.match(text):
            continue
        if _SEQ_ONLY_RE.match(text):
            lay.seq.append(el)
            continue
        if "{{seq:" in text:
            lay.seq_inline.append(el)
            continue
        m = _TABLE_PH_RE.match(text)
        if m:
            if pending_anchor is not None:  # 连续两个表位、前一个没有样例表
                slot = _Slot(order=len(lay.slots), anchor=pending_anchor[0], index=pending_anchor[1],
                             caption=pending_caption, subheading=current_sub)
                lay.slots.append(slot)
                lay.order.append(("slot", slot))
                pending_caption = None
            pending_anchor = (el, int(m.group(2)) if m.group(2) else 0)
            continue
        if _SECTION_PH_RE.match(text):
            if lay.section_anchor is None:
                lay.section_anchor = el
                lay.section_sub = current_sub
                lay.order.append(("text", None))
            continue
        if lvl and lvl >= 2:
            if lay.title is None and lvl == title_level:
                lay.title, lay.title_level = el, lvl
                continue
            current_sub = el
            lay.subheadings.append(el)
            lay.order.append(("sub", el))
            pending_caption = None
            continue
        if text:
            # 【…】编制指引（可跨段）里的段落不当表题；表题候选要短、不以句号结尾、不是指引；
            # 指引 / 说明段不清掉已有候选（「受限制的货币资金明细」后跟「（注：…）」再跟表）
            if in_bracket or text.startswith("【"):
                in_bracket = "】" not in text
                pending_caption = None
            elif _caption_like(text):
                pending_caption = el
    if pending_anchor is not None:
        slot = _Slot(order=len(lay.slots), anchor=pending_anchor[0], index=pending_anchor[1],
                     caption=pending_caption, subheading=current_sub)
        lay.slots.append(slot)
        lay.order.append(("slot", slot))
    if lay.title is None and not lay.h1 and title_level is None:
        # 合成模板 / 无标题样式：首个普通文字段当标题
        for el in inner:
            if el.tag == _W_P and _text(el) and not _text(el).startswith(("{{", "##")):
                lay.title = el
                break
    for slot in lay.slots:
        keys = []
        for el in (slot.caption, slot.subheading):
            if el is not None:
                k = _norm_key(_text(el))
                if k:
                    keys.append(k)
        slot.keys = tuple(keys)
    return lay


def caption_like(text: str) -> bool:
    """模板段落像表题：短、不以句号结尾、不含【】、不是编制指引。"""
    from app.services.note_deliverable_filter import is_guidance_line

    t = unicodedata.normalize("NFKC", text).strip()
    if not t or len(t) > 60 or "【" in t or "】" in t or t.endswith(("。", "；", ";")):
        return False
    return not is_guidance_line(t)


_caption_like = caption_like


def structure_like(text: str) -> bool:
    """模板表题 / 子标题可作「正文重复短行」比对：像表题，且不是引导句（「…如下：」、带逗号的陈述、整句括注）。"""
    t = unicodedata.normalize("NFKC", text or "").strip()
    if not caption_like(t) or t.endswith((":", "：")) or "," in t:
        return False
    return not (t.startswith("(") and not re.match(r"^\(\s*[\d一二三四五六七八九十]{1,3}\s*\)", t))


def block_layout(block, names: dict[str, str]) -> _Layout:
    """块结构（标题 / 子标题 / 表位 / 正文位）；重建前先算好可供跨块编号重启记录复用。"""
    return _layout(block, names)


def structure_titles(lay: _Layout) -> list[str]:
    """模板块里的子标题与表题文字（正文过滤据此删同名短行）。"""
    out = [_text(s) for s in lay.subheadings]
    out.extend(_text(s.caption) for s in lay.slots if s.caption is not None and structure_like(_text(s.caption)))
    return [t for t in out if t]


def _match_tables(lay: _Layout, tables: list[tuple[int, dict]]) -> tuple[dict[int, list[dict]], list[dict]]:
    """库内表（原序号, 表）→ 表位：表名对表题 / 子标题 → 表位序号 N；续表跟主表。

    返回 ``({slot.order: [表…]}, 额外表)``；空表照常参与对位（占住表位序号），由调用方决定是否渲染。
    """
    assigned: dict[int, list[dict]] = {}
    taken: set[int] = set()
    extras: list[dict] = []
    last_slot: int | None = None
    for idx, t in tables:
        name = str(t.get("name") or "")
        if (_CONT_RE.search(name) or t.get("continuation_of_index") is not None) and last_slot is not None:
            # 续表：模板在主表之后有同名「（续）」表位 → 归该表位（沿用模板表题）；否则紧跟主表
            key = _norm_key(name)
            cont = next(
                (s for s in lay.slots
                 if s.order > last_slot and s.order not in taken and key and key in s.keys
                 and s.caption is not None and _CONT_RE.search(_text(s.caption))),
                None,
            )
            if cont is not None:
                taken.add(cont.order)
                assigned.setdefault(cont.order, []).append(t)
                last_slot = cont.order
            else:
                assigned.setdefault(last_slot, []).append(t)
            continue
        key = _norm_key(name)
        hit = None
        if key:
            hit = next((s for s in lay.slots if s.order not in taken and key in s.keys), None)
        if hit is None:
            # 按序号兜底只在不会张冠李戴时用：库内表没表名，或该表位没有表题 / 子标题（块标题下的主表）
            hit = next((s for s in lay.slots
                        if s.order not in taken and s.index == idx and (not key or not s.keys)), None)
        if hit is None:
            extras.append(t)
            last_slot = None
            continue
        taken.add(hit.order)
        assigned.setdefault(hit.order, []).append(t)
        last_slot = hit.order
    return assigned, extras


def note_tables_indexed(exporter, note) -> list[tuple[int, dict, bool]]:
    """库内表（含底稿投影与表头投影）→ ``[(原序号, 表, 是否空表)]``；``export_enabled=false`` 的表不导出。"""
    from app.services.note_deliverable_filter import table_blank_for_delivery
    from app.services.note_header_projector import project_headers

    td = exporter._effective_table_data(note)
    if not isinstance(td, dict):
        return []
    tables = td.get("_tables") or ([td] if td.get("rows") else [])
    out: list[tuple[int, dict, bool]] = []
    for idx, t in enumerate(tables):
        if not isinstance(t, dict) or not t.get("export_enabled", True):
            continue
        try:
            projected = project_headers(
                t,
                section_number=getattr(note, "note_section", None),
                source_template=getattr(note, "source_template", None),
                table_index=idx,
            )
        except Exception:  # noqa: BLE001 — 表头投影失败按原表
            projected = None
        final = projected if projected is not None else t
        empty = (not final.get("rows")) or table_blank_for_delivery(final.get("rows"), final.get("columns"))
        out.append((idx, final, empty))
    # 期间层（spec note-pull-header-formula-closure R4）：按期间拆开的表合成一张（与 Word 样例表同列数 ⇒ 克隆其表头）
    from app.services.note_period_layout import apply_period_layout_indexed

    return apply_period_layout_indexed(out, getattr(note, "source_template", None), getattr(note, "note_section", None))


# ── 块内编号与标题清理 ───────────────────────────────────────────────────────


def strip_title_guidance(el) -> bool:
    """交付件标题去掉尾部括号 / 中括号提示；与种子 ``title_hint`` 拆分共用一个口径。"""
    raw = _raw_text(el)
    new, _hint = split_title_hint(raw)
    if new == raw or not new.strip():
        return False
    _set_paragraph_text(el, new.rstrip())
    return True


def caption_text(name: str) -> str:
    """库内表名 → 额外表 / 续表的表题：剔除编制指引括注（「（注意：是报表项目）」「（只写现金分配，…）」，规则同标题）。"""
    cleaned = _CAPTION_GUIDE_RE.sub("", name).strip()
    return cleaned or name.strip()


def _literal_number(el) -> int | None:
    m = _LIT_ENUM_RE.match(_raw_text(el)) if el is not None else None
    return int(m.group(1) or m.group(2)) if m else None


def _literal_groups(subs: list[Any], styles: dict[str, Any], names: dict[str, str]) -> dict[int, tuple[int, int]]:
    """字面编号子标题（无自动编号）→ 编号组（级别, 该级第几段）：上级子标题换了，下级就是新的一段。"""
    out: dict[int, tuple[int, int]] = {}
    segment: dict[int, int] = {}
    for el in subs:
        lvl = _heading_level(el, names) or 0
        for deeper in [k for k in segment if k > lvl]:
            segment[deeper] += 1
        segment.setdefault(lvl, 0)
        if not is_auto_numbered(el, styles) and _literal_number(el) is not None:
            out[id(el)] = (lvl, segment[lvl])
    return out


def _renumber_literals(subs: list[Any], styles: dict[str, Any], names: dict[str, str],
                       template_subs: list[Any] | None = None) -> int:
    """保留下来的字面编号子标题（「（3）按账龄披露」、无自动编号）按保留顺序从 1 起重排。

    按模板分组（同级、同一上级段）重排，且只重排模板里本来从 1 连续的组：上市 五、71「（7）供应商融资安排」接在
    自动编号子标题后面，单独一个「（7）」不是从 1 起 ⇒ 不动（原先一律从 1 重排，成了「（1）」）。``template_subs``
    = 模板块全部子标题（保留前），缺省同 ``subs``；元素须一直被持有（按 ``id`` 认组）。
    """
    template = template_subs if template_subs is not None else subs
    groups = _literal_groups(template, styles, names)
    numbers: dict[tuple[int, int], list[int | None]] = {}
    for el in template:
        if id(el) in groups:
            numbers.setdefault(groups[id(el)], []).append(_literal_number(el))
    consecutive = {k for k, v in numbers.items() if v == list(range(1, len(v) + 1))}
    counters: dict[tuple[int, int], int] = {}
    changed = 0
    for el in subs:
        key = groups.get(id(el))
        if key not in consecutive:
            continue
        counters[key] = counters.get(key, 0) + 1
        if _set_literal_number(el, counters[key]):
            changed += 1
    return changed


# ── 块重建 ───────────────────────────────────────────────────────────────────


def _render_table_elements(doc, exporter, table: dict) -> list[Any]:
    """用 ``exporter._render_table`` 渲染一张表，取出它追加在正文末尾的元素（去掉表后空段）。"""
    body = doc.element.body
    has_sect = len(body) and body[-1].tag == qn("w:sectPr")
    before = len(body)
    exporter._render_table(doc, table)
    added = len(body) - before
    if added <= 0:
        return []
    end = len(body) - (1 if has_sect else 0)
    els = list(body)[end - added:end]
    for el in els:
        body.remove(el)
    return [el for el in els if el.tag == _W_TBL or _text(el)]


def _caption_para(text: str, proto) -> Any:
    """额外表 / 续表的表题段：沿用块内模板表题的段落属性，无模板表题时按模板正文格式。"""
    p = OxmlElement("w:p")
    if proto is not None and proto.find(qn("w:pPr")) is not None:
        ppr = copy.deepcopy(proto.find(qn("w:pPr")))
        for np_ in ppr.findall(qn("w:numPr")):
            ppr.remove(np_)
        p.append(ppr)
    else:
        p.append(_body_ppr(keep_next=True))
    r = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts")
    for attr in ("w:ascii", "w:hAnsi"):
        fonts.set(qn(attr), "Arial Narrow")
    fonts.set(qn("w:eastAsia"), "仿宋_GB2312")
    rpr.append(fonts)
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), "24")
    rpr.append(sz)
    r.append(rpr)
    t = OxmlElement("w:t")
    t.text = text
    t.set(_XML_SPACE, "preserve")
    r.append(t)
    p.append(r)
    return p


def _body_ppr(*, keep_next: bool = False) -> Any:
    """模板正文段落格式：段后 0.9 行（模板示例段同款）。"""
    ppr = OxmlElement("w:pPr")
    if keep_next:
        ppr.append(OxmlElement("w:keepNext"))
    sp = OxmlElement("w:spacing")
    sp.set(qn("w:after"), "216")
    sp.set(qn("w:afterLines"), "90")
    ppr.append(sp)
    return ppr


def _is_in(el, items: Iterable[Any]) -> bool:
    return any(el is x for x in items if x is not None)


def _fill_text(doc, host, note, *, run_style, text_filter) -> list[Any]:
    """在 ``host`` 段原位渲染正文（过滤后），返回产出的元素（含 host）；无可输出内容返回 []。"""
    from app.services.note_text_word_render import fill_paragraph_with_note_text

    text = (getattr(note, "text_content", None) or "").strip()
    if not text:
        return []
    if host.find(qn("w:pPr")) is None:
        host.insert(0, _body_ppr())
    sentinel = OxmlElement("w:p")
    host.addnext(sentinel)
    fill_paragraph_with_note_text(Paragraph(host, doc), text, run_style=run_style, block_filter=text_filter)
    produced = []
    el = host
    while el is not None and el is not sentinel:
        produced.append(el)
        el = el.getnext()
    _remove(sentinel)
    if not any(e.tag == _W_TBL or _text(e) for e in produced):
        return []
    return produced


@dataclass
class _Rebuilt:
    stats: BlockRebuildStats
    title: Any
    text_elements: list[Any]


def rebuild_block(
    doc,
    block,
    note,
    *,
    exporter,
    run_style=None,
    text_filter=None,
    names: dict[str, str] | None = None,
    styles: dict[str, Any] | None = None,
    layout: _Layout | None = None,
) -> _Rebuilt:
    """按模板结构重建保留块：标题 + 有数表（含表题 / 子标题）+ 过滤后的正文，其余模板内容删除（design §2.3）。"""
    names = names if names is not None else _style_map(doc)
    styles = styles if styles is not None else styles_by_id(doc)
    lay = layout if layout is not None else _layout(block, names)
    st = BlockRebuildStats()
    open_el, close_el = block.elements[0], block.elements[-1]
    inner = block.elements[1:-1]

    # 1. 库内表 → 表位（只渲染非空表）
    indexed = note_tables_indexed(exporter, note)
    empty_ids = {id(t) for _i, t, e in indexed if e}
    assigned, extras = _match_tables(lay, [(i, t) for i, t, _e in indexed])
    proto = next((s.caption for s in lay.slots if s.caption is not None), None)
    first_sample = next((s.table for s in lay.slots if s.table is not None), None)
    # 补的表题 → (所属表位带字面编号的子标题 / 表题, 它重排前的编号)：子标题重排后表题编号跟着改
    numbered_captions: list[tuple[Any, Any, int | None]] = []

    def _render(tables: list[dict], sample, *, first_caption: bool, caption_proto, head=None) -> list[Any]:
        """渲染若干表；第二张起（续表 / 期初表）、或 ``first_caption`` 时首张，按表名补表题（剔除编制指引）。

        克隆路径（design §2.4）：样例表叶子列数 = 库内表列数时，直接克隆样例表行写值（保留表头合并 / 列宽 /
        字体 / 边框）；列数不一致或无样例表时回退到 ``_render_table`` 结构 + ``apply_template_table_look``。
        """
        out: list[Any] = []
        for t in tables:
            cloned = render_cloned_table(sample, t, header_rows=_header_rows(t)) if sample is not None else None
            if cloned is not None:
                els: list[Any] = [cloned]
                st.tables_cloned += 1
            else:
                els = _render_table_elements(doc, exporter, t)
                if not any(e.tag == _W_TBL for e in els):
                    continue
                for e in els:
                    if e.tag == _W_TBL:
                        apply_template_table_look(e, sample, header_rows=_header_rows(t))
            name = str(t.get("name") or "").strip()
            if name and (out or first_caption):
                cap = _caption_para(caption_text(name), caption_proto)
                out.append(cap)
                if head is not None:
                    numbered_captions.append((cap, head, _literal_number(head)))
            out.extend(els)
            st.tables_rendered += 1
        return out

    slot_out: dict[int, list[Any]] = {}
    for slot in lay.slots:
        ts = [t for t in assigned.get(slot.order, []) if id(t) not in empty_ids]
        # 首张沿用模板表题 / 子标题 / 块标题，不另补
        head = next((e for e in (slot.subheading, slot.caption) if _literal_number(e) is not None), None)
        rendered = _render(ts, slot.table if slot.table is not None else first_sample, first_caption=False,
                           caption_proto=slot.caption if slot.caption is not None else proto, head=head)
        if rendered:
            slot_out[slot.order] = rendered
    extra_out = _render([t for t in extras if id(t) not in empty_ids], first_sample,
                        first_caption=True, caption_proto=proto)
    st.extra_tables = sum(1 for e in extra_out if e.tag == _W_TBL)
    st.unmatched_slots = len(lay.slots) - len(slot_out)

    # 2. 正文：模板正文位原位渲染；无正文位时放在标题后
    host = lay.section_anchor
    temp_host = None
    if host is None:
        temp_host = OxmlElement("w:p")
        (lay.title if lay.title is not None else open_el).addnext(temp_host)
        host = temp_host
    text_els = _fill_text(doc, host, note, run_style=run_style, text_filter=text_filter)
    st.text_rendered = bool(text_els)

    # 3. 子标题：其下有保留表位或正文才保留（连同上级子标题）
    kept_subs = [s.subheading for s in lay.slots if s.order in slot_out and s.subheading is not None]
    if text_els and lay.section_sub is not None:
        kept_subs.append(lay.section_sub)
    parents = _sub_parents(lay.subheadings, names)
    for sub in list(kept_subs):
        p = parents.get(id(sub))
        while p is not None and not _is_in(p, kept_subs):
            kept_subs.append(p)
            p = parents.get(id(p))
    # 独立成段的 {{seq}}：块标题是标题样式（自动编号，或标题文字自带「1、」）时编号已在标题里 → 删段；
    # 标题是普通段落（合成模板）才沿用旧填号
    seq_keep = lay.title is None or not _heading_level(lay.title, names)

    # 4. 按模板顺序组装
    slot_of: list[tuple[Any, _Slot]] = []
    for s in lay.slots:
        for e in (s.caption, s.anchor, s.table):
            if e is not None:
                slot_of.append((e, s))
    out: list[Any] = []
    done: set[int] = set()
    insert_extra_at: int | None = None
    for el in inner:
        if _is_in(el, lay.h1) or el is lay.title:
            out.append(el)
            if el is lay.title and temp_host is not None:
                out.extend(text_els)
                insert_extra_at = len(out)
            continue
        if _has_sectpr(el) and el is not lay.section_anchor:
            # 分节符段保留（只清文字）：删了会让其后内容并入下一节（页面方向 / 页眉随之改变）
            for child in list(el):
                if child.tag != qn("w:pPr"):
                    el.remove(child)
            out.append(el)
            continue
        if el is lay.section_anchor:
            out.extend(text_els)
            if text_els:
                insert_extra_at = len(out)
            continue
        hit = next((s for e, s in slot_of if e is el), None)
        if hit is not None:
            if hit.order not in done:
                done.add(hit.order)
                if hit.order in slot_out:
                    if hit.caption is not None:
                        out.append(hit.caption)
                    out.extend(slot_out[hit.order])
                    insert_extra_at = len(out)
            continue
        if _is_in(el, kept_subs):
            out.append(el)
            continue
        if _is_in(el, lay.seq):
            if seq_keep:
                out.append(el)
            continue
        if _is_in(el, lay.seq_inline):
            out.append(el)
            continue
    if temp_host is not None and lay.title is None and text_els:
        out[0:0] = text_els
        insert_extra_at = (insert_extra_at + len(text_els)) if insert_extra_at is not None else len(text_els)
    if extra_out:
        pos = insert_extra_at if insert_extra_at is not None else len(out)
        out[pos:pos] = extra_out

    # 5. 块内替换：开闭标记之间只留组装结果
    el = open_el.getnext()
    while el is not None and el is not close_el:
        nxt = el.getnext()
        _remove(el)
        el = nxt
    anchor = open_el
    for e in out:
        anchor.addnext(e)
        anchor = e
    st.template_elements_removed = sum(1 for e in inner if not _is_in(e, out))

    # 5. 编号：子标题字面编号重排、块内编号重启转移；标题 / 子标题里的编制指引括注剔除
    kept_sub_order = [e for e in lay.subheadings if _is_in(e, kept_subs)]
    _renumber_literals(kept_sub_order, styles, names, lay.subheadings)
    for cap, head, old in numbered_captions:
        new = _literal_number(head)
        if old is not None and new is not None and new != old and _literal_number(cap) == old:
            _set_literal_number(cap, new)  # 续表表题「（2）…（续：期初数）」跟着所属子标题改号
    _transfer_restarts(lay.subheadings, lambda e: _is_in(e, kept_subs), styles)
    for e in [lay.title, *kept_sub_order]:
        if e is not None and e.tag == _W_P:
            strip_title_guidance(e)
    return _Rebuilt(stats=st, title=lay.title, text_elements=text_els)
