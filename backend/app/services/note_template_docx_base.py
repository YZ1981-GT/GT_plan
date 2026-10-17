"""附注模板模式 docx 底层工具（spec ``deliverable-trio-generation-accuracy`` §2；由 ``note_template_block_fill`` 拆出）。

段落文字、样式名与标题级别、块标记段、显式 / 样式编号判定、字面编号改写、编号重启转移。块重建
（``note_template_block_fill``）、跨块文档处理（``note_template_doc_ops``）、表格外观（``note_template_table_look``）
共用这些函数；本模块不访问数据库。
"""

from __future__ import annotations

import copy
import re
import unicodedata
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

__all__ = [
    "is_auto_numbered",
    "numbering_disabled",
    "paragraph_text",
    "style_map",
    "styles_by_id",
]

_W_P, _W_TBL = qn("w:p"), qn("w:tbl")
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
_OPEN_RE = re.compile(r"^##SECTION:(.+?)##$")
_CLOSE_RE = re.compile(r"^##/SECTION:(.+?)##$")
_HEADING_RE = re.compile(r"^(?:heading|标题)\s*(\d)", re.IGNORECASE)
#: 字面编号（标题文字自带、段落取消了自动编号）：「（3）按账龄披露」「2、或有资产」
_LIT_ENUM_RE = re.compile(r"^\s*(?:[（(](\d{1,2})[）)]|(\d{1,2})[、.．](?!\d))")
_ANY_ENUM_RE = re.compile(
    r"^\s*(?:[（(][一二三四五六七八九十\d]{1,3}[）)]|\d{1,2}[.、．]|[一二三四五六七八九十]{1,3}、)\s*"
)
_CONT_RE = re.compile(r"[（(]\s*续[^）)]*[）)]")


# ── 文字与样式 ───────────────────────────────────────────────────────────────


def _text(el) -> str:
    return "".join(t.text or "" for t in el.iter(qn("w:t"))).strip()


def _raw_text(el) -> str:
    return "".join(t.text or "" for t in el.iter(qn("w:t")))


def paragraph_text(el) -> str:
    """段落 / 表格的可见文字（``w:t`` 拼接、去首尾空白）。"""
    return _text(el) if el is not None else ""


def _style_map(doc) -> dict[str, str]:
    return {s.style_id: (s.name or "") for s in doc.styles if getattr(s, "style_id", None)}


def style_map(doc) -> dict[str, str]:
    """样式 id → 样式名（``_heading_level`` 等用）。"""
    return _style_map(doc)


def styles_by_id(doc) -> dict[str, Any]:
    return {s.get(qn("w:styleId")): s for s in doc.styles.element.findall(qn("w:style"))}


def _style_name(el, names: dict[str, str]) -> str:
    ppr = el.find(qn("w:pPr"))
    ps = ppr.find(qn("w:pStyle")) if ppr is not None else None
    if ps is None:
        return ""
    return names.get(ps.get(qn("w:val")), ps.get(qn("w:val")) or "")


def _heading_level(el, names: dict[str, str]) -> int | None:
    if el.tag != _W_P:
        return None
    m = _HEADING_RE.match(_style_name(el, names).strip())
    return int(m.group(1)) if m else None


def _remove(el) -> None:
    parent = el.getparent()
    if parent is not None:
        parent.remove(el)


def _norm_key(text: str) -> str:
    """表名 / 表题 / 子标题比对键：NFKC、去空白与序号、去「（续…）」与尾部括注。"""
    from app.services.note_deliverable_outline import title_key

    s = unicodedata.normalize("NFKC", text or "")
    s = _CONT_RE.sub("", s)
    s = _ANY_ENUM_RE.sub("", s)
    return title_key(s)


def _body_children(doc) -> list[Any]:
    return [el for el in doc.element.body.iterchildren() if el.tag in (_W_P, _W_TBL)]


def _has_sectpr(el) -> bool:
    """分节符段（``w:pPr/w:sectPr``）：页面方向、页眉页脚按节定义，删了会让其后内容并入下一节。"""
    if el.tag != _W_P:
        return False
    ppr = el.find(qn("w:pPr"))
    return ppr is not None and ppr.find(qn("w:sectPr")) is not None


# ── 块标记 ───────────────────────────────────────────────────────────────────


def _is_open(el) -> str | None:
    if el.tag != _W_P:
        return None
    m = _OPEN_RE.match(_text(el))
    return m.group(1).strip() if m else None


def _is_close(el) -> bool:
    return el.tag == _W_P and bool(_CLOSE_RE.match(_text(el)))


def _marker(text: str):
    p = OxmlElement("w:p")
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = text
    r.append(t)
    p.append(r)
    return p


# ── 编号 ─────────────────────────────────────────────────────────────────────


def _num_id(el) -> str | None:
    """段落显式 numId（无显式编号返回 None；「0」= 显式取消编号）。"""
    ppr = el.find(qn("w:pPr"))
    np_ = ppr.find(qn("w:numPr")) if ppr is not None else None
    nid = np_.find(qn("w:numId")) if np_ is not None else None
    return nid.get(qn("w:val")) if nid is not None else None


def _set_num_pr(el, num_pr) -> None:
    ppr = el.find(qn("w:pPr"))
    if ppr is None:
        ppr = OxmlElement("w:pPr")
        el.insert(0, ppr)
    for old in ppr.findall(qn("w:numPr")):
        ppr.remove(old)
    new = copy.deepcopy(num_pr)
    # numPr 须在 pStyle / keepNext 等之后、rPr 之前：放在 pStyle 后面最稳
    ps = ppr.find(qn("w:pStyle"))
    if ps is not None:
        ps.addnext(new)
    else:
        ppr.insert(0, new)


def _style_num_id(styles: dict[str, Any], style_id: str | None, depth: int = 0) -> str | None:
    if not style_id or depth > 10:
        return None
    st = styles.get(style_id)
    if st is None:
        return None
    ppr = st.find(qn("w:pPr"))
    np_ = ppr.find(qn("w:numPr")) if ppr is not None else None
    nid = np_.find(qn("w:numId")) if np_ is not None else None
    if nid is not None:
        return nid.get(qn("w:val"))
    based = st.find(qn("w:basedOn"))
    return _style_num_id(styles, based.get(qn("w:val")) if based is not None else None, depth + 1)


def numbering_disabled(el) -> bool:
    """段落显式取消了编号（``numId=0``）：标题文字自带「（1）」「1、」，不占 Word 自动编号。"""
    return _num_id(el) == "0"


def is_auto_numbered(el, styles: dict[str, Any]) -> bool:
    """段落是否带 Word 自动编号（显式 numPr 优先；numId=0 = 显式取消；否则看样式链）。"""
    explicit = _num_id(el)
    if explicit is not None:
        return explicit != "0"
    ppr = el.find(qn("w:pPr"))
    ps = ppr.find(qn("w:pStyle")) if ppr is not None else None
    nid = _style_num_id(styles, ps.get(qn("w:val")) if ps is not None else None)
    return nid is not None and nid != "0"


def _replace_head(el, old_len: int, new_head: str) -> None:
    """段首 ``old_len`` 个字符（可跨 run）替换为 ``new_head``，其余文字与 run 格式不动。"""
    remaining = old_len
    for i, t in enumerate(el.iter(qn("w:t"))):
        s = t.text or ""
        cut = min(len(s), remaining)
        remaining -= cut
        t.text = (new_head if i == 0 else "") + s[cut:]
        t.set(_XML_SPACE, "preserve")
        if remaining <= 0:
            break


def _set_paragraph_text(el, text: str) -> None:
    """整段文字改写进首个 ``w:t``（其余清空）：用于标题清理，标题通常只有一种格式。"""
    nodes = list(el.iter(qn("w:t")))
    if not nodes:
        return
    nodes[0].text = text
    nodes[0].set(_XML_SPACE, "preserve")
    for t in nodes[1:]:
        t.text = ""


def _set_literal_number(el, n: int) -> bool:
    """段首字面编号改成 ``n``（「（3）」→「（1）」、「2、」→「1、」）；没有字面编号或已是 ``n`` 返回 False。"""
    raw = _raw_text(el)
    m = _LIT_ENUM_RE.match(raw)
    if not m:
        return False
    g = 1 if m.group(1) is not None else 2
    if int(m.group(g)) == n:
        return False
    head = raw[: m.start(g)] + str(n) + raw[m.end(g): m.end()]
    _replace_head(el, m.end(), head)
    return True


def _transfer_restarts(seq: list[Any], alive, styles: dict[str, Any]) -> int:
    """编号重启（显式 numPr、numId≠0）所在段被删 → 转给其后首个保留的、靠样式编号的同级段。

    ``seq``：同一编号序列里的段落（模板顺序）；``alive(el)``：是否保留。
    """
    moved = 0
    pending = None
    for el in seq:
        nid = _num_id(el)
        holder = nid is not None and nid != "0"
        if holder:
            pending = None if alive(el) else el.find(qn("w:pPr")).find(qn("w:numPr"))
            continue
        # 字面编号段（numId=0）不参与自动编号：跳过，重启留给其后首个自动编号段
        if pending is not None and alive(el) and is_auto_numbered(el, styles):
            _set_num_pr(el, pending)
            moved += 1
            pending = None
    return moved
