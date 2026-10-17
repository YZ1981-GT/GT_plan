"""附注模板模式跨块文档处理（spec ``deliverable-trio-generation-accuracy`` §2；由 ``note_template_block_fill`` 拆出）。

- 预处理：块外同级标题包成合成块、块尾内容收进前一块、块间编制指引删除、样板章落款与页眉页脚占位替换；
- 删块：整块删除但一级标题保留（章号靠 Word 自动编号）；
- 跨块：章内节编号重启转移、字面编号节标题重排、合成块认领附注后改标记、正文交叉引用按交付编号改写；
- 分节：删块后变空的横向节并掉；
- 导出提醒（``DeliveryReport``）与章级附注的合成块。

本模块不访问数据库。
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable

from docx.oxml.ns import qn

from app.services.note_template_docx_base import (
    _body_children,
    _CLOSE_RE,
    _has_sectpr,
    _heading_level,
    is_auto_numbered,
    _is_close,
    _is_open,
    _LIT_ENUM_RE,
    _marker,
    _OPEN_RE,
    _raw_text,
    _remove,
    _set_literal_number,
    _set_paragraph_text,
    _style_map,
    _text,
    _transfer_restarts,
    _W_P,
    _W_TBL,
    _XML_SPACE,
)

if TYPE_CHECKING:
    from app.services.note_template_block_fill import (
        _Layout,
    )

__all__ = [
    "DeliveryReport",
    "LOOSE_PREFIX",
    "SyntheticBlock",
    "absorb_trailing_content",
    "capture_title_order",
    "chapter_contents",
    "collapse_empty_sections",
    "empty_chapters",
    "fill_boilerplate",
    "insert_synthetic_block",
    "keep_only_h1",
    "rename_block_markers",
    "renumber_literal_titles",
    "replace_doc_placeholders",
    "rewrite_cross_refs",
    "strip_loose_guidance",
    "transfer_title_restarts",
    "wrap_loose_regions",
]

LOOSE_PREFIX = "~LOOSE:"
_COMPANY_PH_RE = re.compile(r"[×xXＸ]{2,}(?:股份)?有限(?:责任)?公司")
_BOILERPLATE_PH_RE = re.compile(r"[×xXＸ]{2,}|20\d[Xx×]|\[[^\]]{0,20}\]")
_XREF_RE = re.compile(r"(附注\s*)([一二三四五六七八九十]{1,3}、\d{1,3})(?!\d)")


# ── 预处理 ───────────────────────────────────────────────────────────────────


def wrap_loose_regions(doc, outline) -> dict[str, Any]:
    """把模板里没打 ``##SECTION##`` 标记、与块标题同级的标题（轮廓里 ``code is None`` 的节）包成合成块。

    合成块编码 ``~LOOSE:{region.order}``；范围 = 该标题到下一个块开始标记 / 一级标题 / 另一个合成块标题之前。
    返回 ``{合成编码: OutlineRegion}``。按文档顺序与轮廓的块外节一一对应（轮廓由同一份未改动的模板解析）。
    """
    names = _style_map(doc)
    loose = [r for r in outline.regions if r.code is None]
    if not loose:
        return {}
    by_title: dict[str, list[Any]] = {}
    for r in loose:
        by_title.setdefault(r.title, []).append(r)
    out: dict[str, Any] = {}
    children = _body_children(doc)
    depth = 0
    starts: list[tuple[int, Any]] = []
    for i, el in enumerate(children):
        if _is_open(el):
            depth += 1
            continue
        if _is_close(el):
            depth = max(0, depth - 1)
            continue
        if depth or el.tag != _W_P:
            continue
        lvl = _heading_level(el, names)
        if not lvl or lvl < 2:
            continue
        cands = by_title.get(_text(el))
        if cands:
            starts.append((i, cands.pop(0)))
    for idx, (i, region) in enumerate(starts):
        code = f"{LOOSE_PREFIX}{region.order}"
        end = len(children)
        nxt = starts[idx + 1][0] if idx + 1 < len(starts) else None
        for j in range(i + 1, len(children)):
            el = children[j]
            if (nxt is not None and j >= nxt) or _is_open(el) or _heading_level(el, names) == 1:
                end = j
                break
        children[i].addprevious(_marker(f"##SECTION:{code}##"))
        last = children[end - 1]
        last.addnext(_marker(f"##/SECTION:{code}##"))
        out[code] = region
    return out


def absorb_trailing_content(doc) -> int:
    """块结束标记之后、下一个块 / 一级标题之前的内容（参考表、表题、指引）移进前一块。返回移动元素数。"""
    names = _style_map(doc)
    moved = 0
    children = _body_children(doc)
    for i, el in enumerate(children):
        if not _is_close(el):
            continue
        tail = []
        for nxt in children[i + 1:]:
            if _is_open(nxt) or _is_close(nxt) or _heading_level(nxt, names) == 1:
                break
            tail.append(nxt)
        if not any(t.tag == _W_TBL or _text(t) for t in tail):
            continue
        for t in tail:
            el.addprevious(t)  # 依次插到结束标记前，保持原顺序
            moved += 1
    return moved


def strip_loose_guidance(doc, names: dict[str, str]) -> int:
    """块外（深度 0、非一级标题）的模板内容：所在章有块 → 是块间编制指引（「【企业应当在附注中披露…】」
    「披露内容参考如下：」），删除；所在章没有块 → 是该章的正文样板（「财务报表之批准」），保留。

    首个一级标题之前（文档标题「财务报表附注」、目录）不动。须在块预处理之后、删块之前调用。
    """
    chapters: list[tuple[list[Any], bool]] = []  # (块外元素, 本章是否有块)
    depth = 0
    for el in _body_children(doc):
        if _is_open(el):
            depth += 1
            if chapters:
                chapters[-1] = (chapters[-1][0], True)
            continue
        if _is_close(el):
            depth = max(0, depth - 1)
            continue
        if _heading_level(el, names) == 1:
            chapters.append(([], depth > 0))  # 一级标题在块内（「一、1 公司基本情况」）⇒ 本章有块
            continue
        if depth:
            continue
        if chapters:
            chapters[-1][0].append(el)
    removed = 0
    for loose, has_blocks in chapters:
        if not has_blocks:
            continue
        for el in loose:
            if _has_sectpr(el):
                for child in list(el):
                    if child.tag != qn("w:pPr"):
                        el.remove(child)
                continue
            _remove(el)
            removed += 1
    return removed


def fill_boilerplate(doc, names: dict[str, str], company: str | None) -> list[str]:
    """没有块的章（「财务报表之批准」）保留模板样板文字：落款「××××有限公司」换成公司全称；
    返回仍含待填写内容（「第××届」「202X年×月×日」）的章标题（导出提醒）。须在删块之前调用。"""
    out: list[str] = []
    title: str | None = None
    has_blocks = False
    paras: list[Any] = []

    def _flush() -> None:
        if title is None or has_blocks:
            return
        pending = False
        for p in paras:
            raw = _raw_text(p)
            if company and _COMPANY_PH_RE.search(raw):
                raw = _COMPANY_PH_RE.sub(company, raw)
                _set_paragraph_text(p, raw)
            pending = pending or bool(_BOILERPLATE_PH_RE.search(raw))
        if pending:
            out.append(title)

    depth = 0
    for el in _body_children(doc):
        if _is_open(el):
            depth += 1
            has_blocks = True
            continue
        if _is_close(el):
            depth = max(0, depth - 1)
            continue
        if _heading_level(el, names) == 1:
            _flush()
            title, has_blocks, paras = _text(el), depth > 0, []
            continue
        if not depth and el.tag == _W_P and _text(el):
            paras.append(el)
    _flush()
    return out


def keep_only_h1(block, names: dict[str, str]) -> int:
    """删除整块，但块内一级标题段保留（章号靠 Word 自动编号）。返回删除元素数。"""
    removed = 0
    for el in block.elements:
        if el.tag == _W_P and _heading_level(el, names) == 1:
            continue
        if _has_sectpr(el):
            for child in list(el):
                if child.tag != qn("w:pPr"):
                    el.remove(child)  # 分节符段只清空文字，保留分节
            continue
        _remove(el)
        removed += 1
    return removed


def _replace_in_paragraph(p, values: dict[str, str]) -> bool:
    runs = p.findall(qn("w:r"))
    full = "".join(_raw_text(r) for r in runs)  # 不去空白：run 之间的空格是页眉文字的一部分
    if "{{" not in full:
        return False
    changed = False
    for r in runs:  # 先逐 run 替换（保留各 run 格式）
        for t in r.findall(qn("w:t")):
            new = t.text or ""
            for k, v in values.items():
                new = new.replace("{{" + k + "}}", v)
            if new != (t.text or ""):
                t.text = new
                changed = True
    full = "".join(_raw_text(r) for r in runs)
    if any("{{" + k + "}}" in full for k in values):  # 占位被拆在多个 run 里：并到首个 run
        merged = full
        for k, v in values.items():
            merged = merged.replace("{{" + k + "}}", v)
        first = True
        for r in runs:
            for t in r.findall(qn("w:t")):
                t.text = merged if first else ""
                if first:
                    t.set(_XML_SPACE, "preserve")
                first = False
        changed = True
    return changed


def replace_doc_placeholders(doc, values: dict[str, str]) -> int:
    """正文 / 页眉 / 页脚（含表格单元格）里的 ``{{key}}`` 按 ``values`` 替换；未知 key 原样保留。"""
    values = {k: v for k, v in values.items() if isinstance(v, str) and v}
    if not values:
        return 0
    roots = [doc.element.body]
    for section in doc.sections:
        for part in (section.header, section.footer, section.first_page_header, section.first_page_footer,
                     section.even_page_header, section.even_page_footer):
            try:
                if part is not None and not part.is_linked_to_previous:
                    roots.append(part._element)
            except Exception:  # noqa: BLE001 — 页眉页脚缺失
                continue
    count = 0
    seen: set[int] = set()
    for root in roots:
        if id(root) in seen:
            continue
        seen.add(id(root))
        for p in root.iter(_W_P):
            count += _replace_in_paragraph(p, values)
    return count


# ── 跨块：编号重启、字面编号、标记改名、交叉引用 ─────────────────────────────


def capture_title_order(doc, layouts: Iterable[_Layout], names: dict[str, str]) -> list[tuple[int, Any]]:
    """块标题（非一级标题）按文档顺序 → ``[(所在一级标题序号, 标题段)]``；须在删除 / 重建之前调用。"""
    titles = [lay.title for lay in layouts if lay.title is not None and (lay.title_level or 0) >= 2]
    wanted = {id(t) for t in titles}
    out: list[tuple[int, Any]] = []
    h1 = 0
    for el in _body_children(doc):
        if _heading_level(el, names) == 1:
            h1 += 1
            continue
        if id(el) in wanted:
            out.append((h1, el))
    return out


def transfer_title_restarts(order: list[tuple[int, Any]], styles: dict[str, Any]) -> int:
    """章内节编号重启（「八、1」标题的显式 numPr）所在块被删 → 转给本章首个保留的节标题。不跨章。"""
    moved = 0
    by_chapter: dict[int, list[Any]] = {}
    for chap, el in order:
        by_chapter.setdefault(chap, []).append(el)
    for seq in by_chapter.values():
        moved += _transfer_restarts(seq, lambda e: e.getparent() is not None, styles)
    return moved


def renumber_literal_titles(order: list[tuple[int, Any]], styles: dict[str, Any]) -> int:
    """各章保留下来的字面编号节标题（「1、或有负债」、取消了自动编号）按保留顺序从 1 起重排。"""
    changed = 0
    counters: dict[int, int] = {}
    for chap, el in order:
        if el.getparent() is None or is_auto_numbered(el, styles) or not _LIT_ENUM_RE.match(_raw_text(el)):
            continue
        counters[chap] = counters.get(chap, 0) + 1
        changed += _set_literal_number(el, counters[chap])
    return changed


def rename_block_markers(block, code: str) -> None:
    """合成块（``~LOOSE:``）认领了库内附注 → 标记改成附注编号（锚点 / 章节状态按真实编号落）。"""
    for el, text in ((block.open_el, f"##SECTION:{code}##"), (block.close_el, f"##/SECTION:{code}##")):
        _set_paragraph_text(el, text)
    block.section_code = code


def rewrite_cross_refs(elements: Iterable[Any], display: dict[str, str]) -> tuple[int, list[str]]:
    """正文里的「附注八、10」按交付件实际编号改写（单体国企「八、10」→「七、9」；删块后节号顺延）。

    只改 ``display`` 里有的编号；指向未导出章节的引用原样保留并返回（导出提醒）。
    """
    changed = 0
    dangling: list[str] = []

    def _sub(m: re.Match[str]) -> str:
        target = display.get(m.group(2))
        return m.group(1) + target if target else m.group(0)

    for root in elements:
        for p in ([root] if root.tag == _W_P else list(root.iter(_W_P))):
            raw = _raw_text(p)
            if "附注" not in raw:
                continue
            hits = list(_XREF_RE.finditer(raw))
            dangling.extend(m.group(2) for m in hits if display.get(m.group(2)) is None)
            expected = _XREF_RE.sub(_sub, raw)
            if expected == raw:
                continue
            nodes = list(p.iter(qn("w:t")))
            per_node = [_XREF_RE.sub(_sub, n.text or "") for n in nodes]
            if "".join(per_node) == expected:  # 编号都在单个 run 内：逐 run 改，保留粗斜体
                for n, s in zip(nodes, per_node):
                    if s != (n.text or ""):
                        n.text = s
            else:  # 编号被拆在多个 run：整段写回首个 run
                _set_paragraph_text(p, expected)
            changed += 1
    return changed, dangling


# ── 分节 ─────────────────────────────────────────────────────────────────────


#: 节属性里「随节继承 / 只在节首生效」的子元素：节被并掉时转给下一节（下一节已有同类则不动）
_SECT_MOVABLE = ("w:headerReference", "w:footerReference", "w:pgNumType", "w:titlePg")
_SECT_LAYOUT = ("w:pgSz", "w:pgMar", "w:cols")
_SECT_SUCCESSORS = {
    "w:pgNumType": ("w:cols", "w:formProt", "w:vAlign", "w:noEndnote", "w:titlePg", "w:textDirection", "w:bidi",
                    "w:rtlGutter", "w:docGrid", "w:printerSettings", "w:sectPrChange"),
    "w:titlePg": ("w:textDirection", "w:bidi", "w:rtlGutter", "w:docGrid", "w:printerSettings", "w:sectPrChange"),
}


def _sections(body) -> list[tuple[Any, Any, list[Any]]]:
    """正文按分节拆开 → ``[(结束元素, sectPr, 节内元素)]``；最后一节的结束元素是 body 级 ``w:sectPr``。"""
    out: list[tuple[Any, Any, list[Any]]] = []
    content: list[Any] = []
    for el in body.iterchildren():
        if el.tag == qn("w:sectPr"):
            out.append((el, el, content))
            content = []
            continue
        content.append(el)
        if _has_sectpr(el):
            out.append((el, el.find(qn("w:pPr")).find(qn("w:sectPr")), content))
            content = []
    return out


def _visible(el) -> bool:
    if el.tag == _W_TBL:
        return True
    if el.tag == qn("w:sdt"):  # 目录等内容控件
        return bool(_text(el)) or el.find(".//" + _W_TBL) is not None
    if el.tag != _W_P:
        return False
    return bool(_text(el)) or el.find(".//" + qn("w:drawing")) is not None or el.find(".//" + qn("w:pict")) is not None


def _layout_key(sp) -> str:
    from lxml import etree

    parts = []
    for tag in _SECT_LAYOUT:
        el = sp.find(qn(tag))
        parts.append(etree.tostring(el, method="c14n").decode() if el is not None else "")
    return "|".join(parts)


def _move_section_props(src, dst) -> None:
    """``src`` 节被并入 ``dst``：页眉页脚引用（按类型）、起始页码、首页不同转给 ``dst``（``dst`` 已有的不动）。"""
    for tag in _SECT_MOVABLE:
        for el in src.findall(qn(tag)):
            kind = el.get(qn("w:type"))
            exists = [e for e in dst.findall(qn(tag)) if e.get(qn("w:type")) == kind]
            if exists:
                continue
            new = copy.deepcopy(el)
            if tag in ("w:headerReference", "w:footerReference"):
                dst.insert(0, new)  # 页眉页脚引用在 sectPr 最前
            else:
                # CT_SectPr 子元素有序：pgNumType 在 cols 前、titlePg 在 textDirection / docGrid 前
                successors = _SECT_SUCCESSORS[tag]
                anchor = next((c for c in dst if c.tag in {qn(s) for s in successors}), None)
                if anchor is not None:
                    anchor.addprevious(new)
                else:
                    dst.append(new)


def _drop_section_break(end_el, sp) -> None:
    ppr = end_el.find(qn("w:pPr"))
    ppr.remove(sp)
    if not _visible(end_el):
        _remove(end_el)


def collapse_empty_sections(doc) -> int:
    """删块后变空的分节（横向表所在节）并掉，避免交付件出现空白横向页；相邻同版式节随之合并（去掉多余分页）。"""
    body = doc.element.body
    merged = 0
    while True:
        secs = _sections(body)
        hit = next((i for i, (end, sp, content) in enumerate(secs[:-1])
                    if end.tag == _W_P and not any(_visible(e) for e in content)), None)
        if hit is None:
            return merged
        end, sp, _content = secs[hit]
        nxt_sp = secs[hit + 1][1]
        _move_section_props(sp, nxt_sp)
        _drop_section_break(end, sp)
        merged += 1
        if hit > 0:
            prev_end, prev_sp, _ = secs[hit - 1]
            if prev_end.tag == _W_P and _layout_key(prev_sp) == _layout_key(nxt_sp):
                _move_section_props(prev_sp, nxt_sp)
                _drop_section_break(prev_end, prev_sp)
                merged += 1


# ── 导出提醒与章级合成块 ─────────────────────────────────────────────────────


def _head(items: list[str], limit: int = 6) -> str:
    uniq = list(dict.fromkeys(i for i in items if i))
    shown = "、".join(uniq[:limit])
    return shown + (f" 等 {len(uniq)} 处" if len(uniq) > limit else "")


@dataclass
class DeliveryReport:
    """一次模板模式导出的交付统计 → 导出提醒（中文，只提示不阻断）。"""

    filtered_lines: int = 0
    filtered_sections: list[str] = field(default_factory=list)
    placeholder_sections: list[str] = field(default_factory=list)
    fs_zero_dropped: list[str] = field(default_factory=list)
    fs_balance_without_table: list[str] = field(default_factory=list)
    selected_not_exported: list[str] = field(default_factory=list)
    unplaced: list[str] = field(default_factory=list)
    #: 章级附注（编号只有章号）未放进交付件：交付中心勾选树里叫「本章整体说明」，单列一条免得读成「整章未导出」
    chapter_text_unplaced: list[str] = field(default_factory=list)
    empty_chapters: list[str] = field(default_factory=list)
    dangling_refs: list[str] = field(default_factory=list)
    boilerplate_pending: list[str] = field(default_factory=list)
    tables_rendered: int = 0
    extra_tables: int = 0

    def warnings(self) -> list[str]:
        out: list[str] = []
        if self.filtered_lines:
            out.append(
                f"交付过滤：{len(set(self.filtered_sections))} 个章节共剔除 {self.filtered_lines} 行编制提示 / "
                f"大模型草稿 / 与标题重复的首行（库内正文未改动）。"
            )
        if self.placeholder_sections:
            out.append(f"以下章节正文仍有待补充占位（如「[请补充]」「XX」）：{_head(self.placeholder_sections)}，出具前请补全。")
        if self.fs_balance_without_table:
            out.append(f"以下报表项目有余额，但附注没有表格数据：{_head(self.fs_balance_without_table)}。")
        if self.fs_zero_dropped:
            out.append(f"以下章节报表余额为 0 且没有表格数据，未导出：{_head(self.fs_zero_dropped)}。")
        if self.selected_not_exported:
            out.append(f"以下已勾选章节没有可出具的内容，未导出：{_head(self.selected_not_exported)}。")
        if self.unplaced:
            out.append(f"以下章节库内有内容，但附注模板里没有对应位置，未导出：{_head(self.unplaced)}。")
        if self.chapter_text_unplaced:
            out.append(
                "以下各章的「本章整体说明」未导出（该章已按分节出具、章名与模板不符或只剩提示文字）："
                f"{_head(self.chapter_text_unplaced)}。"
            )
        if self.empty_chapters:
            out.append(f"以下各章没有可出具的内容，交付件只保留章标题：{_head(self.empty_chapters)}。")
        if self.dangling_refs:
            out.append(f"正文引用了未导出的附注章节：{_head(['附注' + c for c in self.dangling_refs])}，请核对。")
        if self.boilerplate_pending:
            out.append(f"以下章节为模板样板文字，仍有待填写内容（如批准机构、批准日期）：{_head(self.boilerplate_pending)}。")
        return out


def chapter_contents(doc, names: dict[str, str]) -> list[tuple[Any, bool]]:
    """一级标题（文档顺序）→ 该章（到下一个一级标题前）有没有可见内容（块标记不算）。"""
    out: list[tuple[Any, bool]] = []
    for el in _body_children(doc):
        if _heading_level(el, names) == 1:
            out.append((el, False))
            continue
        if not out or out[-1][1]:
            continue
        text = _text(el)
        if el.tag == _W_TBL or (text and not _OPEN_RE.match(text) and not _CLOSE_RE.match(text)):
            out[-1] = (out[-1][0], True)
    return out


def empty_chapters(doc, names: dict[str, str]) -> list[str]:
    """一级标题之后到下一个一级标题之前没有任何可见内容的章（标题文字）。"""
    return [_text(h1) for h1, has in chapter_contents(doc, names) if not has]


def insert_synthetic_block(after, code: str):
    """在 ``after`` 之后插入只有正文位的合成块（``##SECTION:code##`` + ``{{section:code}}``），供 ``rebuild_block`` 填充。

    用于章级附注（编号只有章号「九」）：模板该章的块都没有可出具内容时，章级正文（「截至 2025 年 12 月 31 日，
    本公司无需要披露的重大或有事项。」）放在章标题之后。
    """
    open_el = _marker(f"##SECTION:{code}##")
    anchor = _marker("{{section:" + code + "}}")
    close_el = _marker(f"##/SECTION:{code}##")
    after.addnext(open_el)
    open_el.addnext(anchor)
    anchor.addnext(close_el)
    return SyntheticBlock(section_code=code, open_el=open_el, close_el=close_el, elements=[open_el, anchor, close_el])


@dataclass
class SyntheticBlock:
    """与 ``word_doc_utils.SectionBlock`` 同形状的合成块（``rebuild_block`` 只用这四个属性）。"""

    section_code: str
    open_el: Any
    close_el: Any
    elements: list[Any]
