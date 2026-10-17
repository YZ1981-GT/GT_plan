"""审计报告正文模板后处理（spec ``deliverable-trio-generation-accuracy`` §3）。

为什么需要（2026-10-16 四个真实项目 × 五种意见逐份核对 + 34 个模板普查）
------------------------------------------------------------------
- 「带强调事项段的无保留意见」与标准无保留用同一份简版模板，交付件里没有强调事项段；
- 上市 / 三板模板的 ``##OPT`` 开闭标记错配（模板加工脚本倒序插入，相邻两段开闭交错；16 份里 12 份）：
  可选段落识别不到、标记原样进交付件，删段后章节序号也不顺延；
- 单体非标模板里 ``##NOTE:单体复核:…##`` 标记未闭合，原样进交付件；集团审计条款（「（6）…集团审计」）与
  「合并财务报表」措辞留在单体报告里；
- 证监会《监管规则适用指引》编制提示框（单格表）、「【非上市实体删除（项目合伙人）】」进交付件；
- 落款日期写死「二〇二六年 / 二○二二年 X 月XX日」；「股东权益变动表」不分企业组织形式。

preview（替换占位符之后、扫描可选段之前）：``prepare_report_body`` —— OPT 标记按章节标题重放 → 插入强调事项段 →
落款日期 → 权益变动表名称 → 章节序号。confirm（保存含指引副本之后）：``finalize_report_body`` —— 剥除编制提示与
残留标记、单体口径条款 → 章节序号（删可选段后再顺延）。只操作 python-docx 文档，不访问数据库。
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

__all__ = [
    "EMPHASIS_TEXT",
    "FIELD_LABELS",
    "GuidanceStripStats",
    "PrepareResult",
    "equity_statement_name",
    "finalize_report_body",
    "insert_emphasis_section",
    "missing_field_labels",
    "normalize_equity_statement_name",
    "normalize_optional_markers",
    "normalize_signing_dates",
    "parse_report_date",
    "pending_items",
    "placeholder_keys",
    "prepare_report_body",
    "renumber_section_headings",
    "strip_report_guidance",
    "toc_pending_pages",
]

_W_P, _W_TBL, _W_T, _W_TC = qn("w:p"), qn("w:tbl"), qn("w:t"), qn("w:tc")
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

#: 一级标题「一、审计意见」「X、强调事项」（详版模板的可选段用 X 占位序号）
_HEADING_RE = re.compile(r"^(?P<num>[一二三四五六七八九十]{1,3}|[XＸx×])\s*[、.．]\s*(?P<name>\S.*?)\s*$")
_HEADING_NUM_RE = re.compile(r"^(\s*)(?:[一二三四五六七八九十]{1,3}|[XＸx×])(?=\s*[、.．])")
_HEADING_MAX_LEN = 40
#: 报告分部标题（详版「二、按照相关法律法规的要求报告的事项」）不参与正文章节编号
_PART_HEADING_KEYS = ("按照相关法律法规的要求报告的事项", "对财务报表出具的审计报告")
_BASIS_RE = re.compile(r"^形成.{0,6}意见的基础$")
_GOING_CONCERN = "与持续经营相关的重大不确定性"
EMPHASIS_TITLE = "强调事项"
#: 与致同详版模板「X、强调事项」段同一措辞
EMPHASIS_TEXT = "我们提醒财务报表使用者关注，财务报表附注×描述了×影响。本段内容不影响已发表的审计意见。"
#: 可选段 id → 该段一级标题名（OPT 标记按标题重放）
OPT_SECTION_TITLES: dict[str, tuple[str, ...]] = {
    "key_audit_matters": ("关键审计事项",),
    "other_information": ("其他信息",),
    "emphasis": (EMPHASIS_TITLE,),
    "going_concern": (_GOING_CONCERN,),
    "other_matter": ("其他事项",),
}
_OPT_MARK_RE = re.compile(r"^##(?P<close>/?)OPT:(?P<id>[^:#]+)(?::(?P<desc>[^#]*))?##\s*$")
_PLACEHOLDER_RE = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")
_CN_DIGITS = "〇一二三四五六七八九"

#: 占位符 → 中文名（预览弹窗「待补充」只列模板实际使用且仍为空 / 方括号占位的字段）
FIELD_LABELS: dict[str, str] = {
    "company_full_name": "被审计单位全称",
    "company_short_name": "被审计单位简称",
    "responsibility_organ": "致送对象（治理层）",
    "signing_partner": "签字合伙人",
    "signing_cpa": "签字注册会计师",
    "signing_cpa_2": "签字注册会计师（第二位）",
    "report_scope": "报表口径",
    "audit_year": "审计年度",
    "prior_year": "上年度",
    "report_date": "报告日期",
    "firm_name": "会计师事务所名称",
    "firm_address": "会计师事务所地址",
    "report_number": "报告文号",
    "audit_period_end": "资产负债表日",
    "audit_period_start": "审计期间起始日",
    "prior_period_end": "上期资产负债表日",
}


# ── 段落工具 ──────────────────────────────────────────────────────────────────


def _ptext(el) -> str:
    return "".join(t.text or "" for t in el.iter(_W_T))


def _set_text(el, text: str) -> None:
    """整段文字写进首个 ``w:t``（其余清空）；没有 run 时新建。"""
    nodes = list(el.iter(_W_T))
    if not nodes:
        r = OxmlElement("w:r")
        t = OxmlElement("w:t")
        r.append(t)
        el.append(r)
        nodes = [t]
    nodes[0].text = text
    nodes[0].set(_XML_SPACE, "preserve")
    for t in nodes[1:]:
        t.text = ""


def _sub_text(el, pattern: re.Pattern[str], repl: Any) -> int:
    """段内正则替换：逐 ``w:t`` 替换的结果与整段替换一致时逐节点改（保留 run 格式），否则整段写回首个
    ``w:t``（命中跨 run）。返回整段命中数。"""
    expected, n = pattern.subn(repl, _ptext(el))
    if not n:
        return 0
    nodes = list(el.iter(_W_T))
    per = [pattern.sub(repl, t.text or "") for t in nodes]
    if "".join(per) == expected:
        for t, s in zip(nodes, per):
            if s != (t.text or ""):
                t.text = s
                t.set(_XML_SPACE, "preserve")
    else:
        _set_text(el, expected)
    return n


def _remove_para(el) -> None:
    """删段落；它是单元格里唯一的块级元素时只清空（``w:tc`` 至少要有一个段落，否则 Word 报内容损坏）。"""
    parent = el.getparent()
    if parent is None:
        return
    if parent.tag == _W_TC and sum(1 for c in parent if c.tag in (_W_P, _W_TBL)) == 1:
        for c in list(el):
            if c.tag != qn("w:pPr"):
                el.remove(c)
        return
    parent.remove(el)


def _new_para(text: str) -> Any:
    p = OxmlElement("w:p")
    _set_text(p, text)
    return p


def _clone_para(proto, text: str) -> Any:
    """沿用样例段落的段落属性与首个 run 格式写新文字；去掉书签与分节符（锚点 / 分节由后续步骤负责）。"""
    p = copy.deepcopy(proto)
    for tag in ("w:bookmarkStart", "w:bookmarkEnd"):
        for el in p.findall(".//" + qn(tag)):
            el.getparent().remove(el)
    ppr = p.find(qn("w:pPr"))
    if ppr is not None:
        for sp in ppr.findall(qn("w:sectPr")):
            ppr.remove(sp)
    _set_text(p, text)
    return p


def _append_body(body, el) -> None:
    last = body[-1] if len(body) else None
    if last is not None and last.tag == qn("w:sectPr"):
        last.addprevious(el)
    else:
        body.append(el)


def _cn_number(n: int) -> str:
    """1 → 一、10 → 十、11 → 十一、20 → 二十、31 → 三十一（章节序号、月、日）。"""
    if n <= 10:
        return "一二三四五六七八九十"[n - 1]
    tens, ones = divmod(n, 10)
    return ("" if tens == 1 else _CN_DIGITS[tens]) + "十" + (_CN_DIGITS[ones] if ones else "")


def _cn_year(year: int) -> str:
    return "".join(_CN_DIGITS[int(c)] for c in str(year))


# ── 章节标题 ──────────────────────────────────────────────────────────────────


def _heading(el) -> tuple[str, str] | None:
    """body 级段落是一级标题时返回 ``(序号, 名称)``。"""
    t = _ptext(el).strip()
    if not t or len(t) > _HEADING_MAX_LEN:
        return None
    m = _HEADING_RE.match(t)
    return (m.group("num"), m.group("name")) if m else None


def _headings(doc) -> list[tuple[Any, str, str]]:
    out = []
    for el in doc.element.body.iterchildren(_W_P):
        h = _heading(el)
        if h is not None:
            out.append((el, h[0], h[1]))
    return out


def _opt_mark(el):
    return _OPT_MARK_RE.match(_ptext(el).strip()) if el.tag == _W_P else None


def normalize_optional_markers(doc) -> int:
    """OPT 开闭标记按章节标题重放：出现过标记的可选段 → 开标记放在该段标题前，闭标记放在下一个一级标题前。

    开标记认其后首个同名标题，闭标记认其前最近的同名标题（模板错配时两种标记各自都还指着本该包住的那一段）；
    对不上标题的标记原样保留。幂等；返回重放的可选段数。
    """
    body = doc.element.body
    # 先持有全部子元素：lxml 代理对象没人引用就会回收、再取时 id() 变了（以 id 为键的位置表会 KeyError）
    children = list(body.iterchildren())
    order = {id(el): i for i, el in enumerate(children)}
    found = _headings(doc)
    heads = [h for h, _num, _name in found]
    names = {id(h): name for h, _num, name in found}
    marks = [(el, m) for el in body.iterchildren(_W_P) if (m := _opt_mark(el)) is not None]
    targets: dict[str, Any] = {}
    descs: dict[str, str] = {}
    for el, m in marks:
        sid = m.group("id").strip()
        if (m.group("desc") or "").strip():
            descs.setdefault(sid, m.group("desc").strip())
        cands = [h for h in heads if names[id(h)] in OPT_SECTION_TITLES.get(sid, ())]
        pos = order[id(el)]
        if m.group("close"):
            before = [h for h in cands if order[id(h)] < pos]
            hit = before[-1] if before else None
        else:
            hit = next((h for h in cands if order[id(h)] > pos), None)
        if hit is not None:
            targets.setdefault(sid, hit)
    if not targets:
        return 0
    for el, m in marks:
        if m.group("id").strip() in targets:
            body.remove(el)
    for sid, head in targets.items():  # 先放闭标记：相邻两段时闭标记要在下一段的开标记之前
        nxt = next((h for h in heads if order[id(h)] > order[id(head)]), None)
        close_el = _new_para(f"##/OPT:{sid}##")
        if nxt is not None:
            nxt.addprevious(close_el)
        else:
            _append_body(body, close_el)
    for sid, head in targets.items():
        head.addprevious(_new_para(f"##OPT:{sid}:{descs.get(sid) or OPT_SECTION_TITLES[sid][0]}##"))
    return len(targets)


def insert_emphasis_section(doc, *, text: str = EMPHASIS_TEXT) -> bool:
    """在「形成审计意见的基础」（及紧随的「与持续经营相关的重大不确定性」）之后插入「X、强调事项」段。

    标题沿用基础段标题的段落格式，正文沿用基础段首个正文段的格式；序号由 ``renumber_section_headings`` 顺延。
    插在下一节的 OPT 开标记之前（强调事项不属于该可选段）。已有强调事项段 / 找不到基础段或其后的标题时不动。
    """
    heads = _headings(doc)
    if any(name == EMPHASIS_TITLE for _el, _num, name in heads):
        return False
    idx = next((i for i, (_el, _num, name) in enumerate(heads) if _BASIS_RE.match(name)), None)
    if idx is None:
        return False
    j = idx + 1
    while j < len(heads) and heads[j][2] == _GOING_CONCERN:
        j += 1
    if j >= len(heads):
        return False
    basis, end = heads[idx][0], heads[j][0]
    proto = None
    el = basis.getnext()
    while el is not None and el is not end:
        if el.tag == _W_P and _ptext(el).strip() and _heading(el) is None and _opt_mark(el) is None:
            proto = el
            break
        el = el.getnext()
    anchor = end
    prev = anchor.getprevious()
    while prev is not None and (m := _opt_mark(prev)) is not None and not m.group("close"):
        anchor, prev = prev, prev.getprevious()
    anchor.addprevious(_clone_para(basis, f"X、{EMPHASIS_TITLE}"))
    anchor.addprevious(_clone_para(proto if proto is not None else basis, text))
    return True


def renumber_section_headings(doc) -> int:
    """正文一级标题序号按文档顺序重排（插入强调事项 / 删除可选段 / 详版「X、」之后连续）；分部标题不参与。

    返回改了序号的标题数。
    """
    n = changed = 0
    for el, num, name in _headings(doc):
        if any(k in name for k in _PART_HEADING_KEYS):
            continue
        n += 1
        want = _cn_number(n)
        if num != want and _sub_text(el, _HEADING_NUM_RE, lambda m, w=want: m.group(1) + w):
            changed += 1
    return changed


# ── 落款日期 / 权益变动表名称 ─────────────────────────────────────────────────

_SIGN_DATE_RE = re.compile(
    r"(?P<y>二[〇○零Ｏ０0][〇○零Ｏ０0一二三四五六七八九]{2})(?P<ys>\s*年)"
    r"(?P<m>\s*[X×xＸ\d一二三四五六七八九十]{1,3}\s*)月(?P<d>\s*[X×xＸ\d一二三四五六七八九十]{1,3}\s*)日"
)
_PENDING_DATE_RE = re.compile(r"[X×xＸ]")
_JOINT_STOCK_RE = re.compile(r"股份(?:有限)?公司")
_SHAREHOLDER_EQUITY_RE = re.compile("股东权益")


def parse_report_date(raw: Any) -> date | None:
    """``2026-03-15`` / ``2026年3月15日`` / ``date`` → ``date``；占位（「[报告日期]」）或无法解析返回 ``None``。"""
    if isinstance(raw, date):
        return raw
    m = re.match(r"^\s*(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})", str(raw or ""))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def normalize_signing_dates(doc, *, report_date: date | None, audit_year: int | None) -> int:
    """落款日期（模板写死「二〇二六年 X 月XX日」「二○二二年X月XX日」）：有报告日期写中文日期；否则年份改为
    审计年度 + 1、月日占位保留。返回改动的段落数。"""
    if report_date is not None:
        full = f"{_cn_year(report_date.year)}年{_cn_number(report_date.month)}月{_cn_number(report_date.day)}日"

        def _repl(m: re.Match[str]) -> str:
            return full
    elif audit_year:
        year = _cn_year(int(audit_year) + 1)

        def _repl(m: re.Match[str]) -> str:
            return f"{year}{m.group('ys')}{m.group('m')}月{m.group('d')}日"
    else:
        return 0
    changed = 0
    for p in list(doc.element.body.iter(_W_P)):
        before = _ptext(p)
        if "年" in before and _sub_text(p, _SIGN_DATE_RE, _repl) and _ptext(p) != before:
            changed += 1
    return changed


def equity_statement_name(company_name: str | None) -> str:
    """权益变动表名称按企业组织形式：股份有限公司 →「股东权益变动表」，其余 →「所有者权益变动表」。"""
    return "股东权益变动表" if _JOINT_STOCK_RE.search(company_name or "") else "所有者权益变动表"


def normalize_equity_statement_name(doc, company_name: str | None) -> int:
    """模板统一写「股东权益」：非股份公司改为「所有者权益」（报表名、目录与正文措辞，与财务报表一致）。

    返回改动的段落数。
    """
    if _JOINT_STOCK_RE.search(company_name or ""):
        return 0
    return sum(
        1 for p in list(doc.element.body.iter(_W_P))
        if "股东权益" in _ptext(p) and _sub_text(p, _SHAREHOLDER_EQUITY_RE, "所有者权益")
    )


# ── 编制提示与残留标记（confirm：含指引副本已另存） ───────────────────────────

_GUIDE_BOX_KEYS = ("监管规则适用指引", "【适用于")
_NOTE_PREFIX_RE = re.compile(r"^\s*##NOTE(?::[^#]*)?##\s*")
_MARKER_RE = re.compile(r"##/?(?:OPT|NOTE)(?::[^#]*)?##")
_CONSOLIDATED_RE = re.compile(r"合并(?=财务报表|资产负债表|利润表|现金流量表|股东权益变动表|所有者权益变动表)")
_BRACKET_RE = re.compile(r"【(?P<body>[^【】]{0,80})】")
_BRACKET_GUIDE_RE = re.compile(r"删除|适用|填写|选择|保留|参考|注[:：]")
_UNLISTED_DROP_RE = re.compile(r"非上市实体删除[（(](?P<what>[^（）()]{1,20})[）)]")
#: 无法表示意见模板（公众利益 / 非公众利益共用）的二选一措辞：「…独立性要求（如适用）/中国注册会计师独立性准则」，
#: 取「（如适用）」口径（与 C / D 类无保留模板一致，两类实体都适用）
_ALTERNATIVE_RE = re.compile(r"（如适用）\s*/\s*中国注册会计师独立性准则")


@dataclass
class GuidanceStripStats:
    """``strip_report_guidance`` 的处理计数（日志 / 测试用）。"""

    guide_boxes: int = 0
    group_clauses: int = 0
    consolidated_wording: int = 0
    bracket_notes: int = 0
    alternatives: int = 0
    markers: int = 0


def _bracket_repl(m: re.Match[str]) -> str:
    return "" if _BRACKET_GUIDE_RE.search(m.group("body")) else m.group(0)


def _drop_unlisted_text(p, what: str) -> int:
    """「【非上市实体删除（项目合伙人）】」：同一表格（无表格则全文）里正文恰为「（项目合伙人）」的段落删除。"""
    container = p
    while container is not None and container.tag != _W_TBL:
        container = container.getparent()
    root = container if container is not None else p.getroottree().getroot()
    wanted = {f"（{what}）", f"({what})"}
    hits = [q for q in root.iter(_W_P) if _ptext(q).strip() in wanted]
    for q in hits:
        _remove_para(q)
    return len(hits)


def strip_report_guidance(doc, *, standalone: bool, listed: bool) -> GuidanceStripStats:
    """交付件剥除编制提示（在 ``strip_guidance_notes`` 之后调用）：

    1. 证监会指引 / 「【适用于…】」编制提示框（单格表）整表删除；
    2. 「##NOTE:单体复核:…##」未闭合行内标记：单体报告删除集团审计条款（「…集团审计…」），其余段去标记，
       单体报告把「合并财务报表 / 合并资产负债表…」改为单体措辞；
    3. 无法表示意见模板的二选一措辞「（如适用）/中国注册会计师独立性准则」取「（如适用）」口径；
    4. 「【…】」编制提示（删除 / 适用 / 填写…）去掉；「【非上市实体删除（X）】」非上市实体同时删「（X）」；
    5. 残留的 ``##OPT`` / ``##NOTE`` 标记文字清除，清空后段落删除。
    """
    st = GuidanceStripStats()
    body = doc.element.body
    for tbl in list(body.iter(_W_TBL)):
        if tbl.getparent() is None:
            continue
        if len(tbl.findall(".//" + _W_TC)) == 1 and any(k in _ptext(tbl) for k in _GUIDE_BOX_KEYS):
            tbl.getparent().remove(tbl)
            st.guide_boxes += 1
    for p in list(body.iter(_W_P)):
        if p.getparent() is None:
            continue
        text = _ptext(p)
        if _NOTE_PREFIX_RE.match(text):
            if standalone and "集团审计" in _NOTE_PREFIX_RE.sub("", text, count=1):
                _remove_para(p)
                st.group_clauses += 1
                continue
            st.markers += _sub_text(p, _NOTE_PREFIX_RE, "")
            if standalone:
                st.consolidated_wording += _sub_text(p, _CONSOLIDATED_RE, "")
            text = _ptext(p)
        if "/" in text and _ALTERNATIVE_RE.search(text):
            st.alternatives += _sub_text(p, _ALTERNATIVE_RE, "（如适用）")
            text = _ptext(p)
        if "【" in text:
            for m in _BRACKET_RE.finditer(text):
                drop = _UNLISTED_DROP_RE.search(m.group("body"))
                if drop and not listed:
                    _drop_unlisted_text(p, drop.group("what"))
            n = _sub_text(p, _BRACKET_RE, _bracket_repl)
            if n and _ptext(p) != text:
                st.bracket_notes += 1
                text = _ptext(p)
                if not text.strip():
                    _remove_para(p)
                    continue
        if "##" in text and _MARKER_RE.search(text):
            st.markers += _sub_text(p, _MARKER_RE, "")
            if not _ptext(p).strip():
                _remove_para(p)
    return st


# ── 待补充清单 ────────────────────────────────────────────────────────────────


def placeholder_keys(doc) -> set[str]:
    """文档实际使用的 ``{{key}}``（正文含表格 + 页眉页脚）；在替换占位符之前调用。"""
    roots = [doc.element.body]
    for section in doc.sections:
        for part in (section.header, section.footer):
            try:
                roots.append(part._element)
            except Exception:  # noqa: BLE001 — 页眉页脚缺失
                continue
    keys: set[str] = set()
    for root in roots:
        for p in root.iter(_W_P):
            keys.update(_PLACEHOLDER_RE.findall(_ptext(p)))
    return keys


def missing_field_labels(missing_keys: list[str], used_keys: set[str]) -> list[str]:
    """``detect_missing_fields`` 的键 → 模板实际用到的那些的中文名（去重保序）。"""
    out: list[str] = []
    for key in missing_keys:
        label = FIELD_LABELS.get(key, key)
        if key in used_keys and label not in out:
            out.append(label)
    return out


#: 目录页码占位「1-X」「7-X」（34 份报告模板的目录表都有；页数取决于装订后的整本报告，生成时算不出）
_TOC_PAGE_X_RE = re.compile(r"^\s*\d+\s*[-－—–]\s*[XＸxｘ]\s*$")
_W_TR = qn("w:tr")


def toc_pending_pages(doc) -> list[str]:
    """目录表里页码仍为「n-X」的行 → 「审计报告 1-X」（取同行左侧最近的非空单元格作名称）。"""
    out: list[str] = []
    for tr in doc.element.body.iter(_W_TR):
        cells = ["".join(_ptext(p) for p in tc.iter(_W_P)).strip() for tc in tr.iterchildren(_W_TC)]
        for i, cell in enumerate(cells):
            if _TOC_PAGE_X_RE.match(cell):
                label = next((c for c in reversed(cells[:i]) if c), "")
                out.append(f"{label} {cell}".strip())
    return out


def pending_items(doc) -> list[str]:
    """生成后仍需人工补写的内容（中文；预览弹窗「待补充」与 ``report_body_json.missing_fields``）。"""
    out: list[str] = []
    paras = list(doc.element.body.iter(_W_P))
    texts = [_ptext(p) for p in paras]
    names = [name for _el, _num, name in _headings(doc)]
    if EMPHASIS_TITLE in names:
        out.append("强调事项段（所强调的事项与附注编号）")
    for name in names:
        if _BASIS_RE.match(name) and name != "形成审计意见的基础":
            out.append(f"{name}段（模板示例，须按实际事项改写）")
    residual = sorted({k for t in texts for k in _PLACEHOLDER_RE.findall(t)})
    if residual:
        out.append("未填充的占位符：" + "、".join(FIELD_LABELS.get(k, k) for k in residual))
    crosses = sum(t.count("×") for t in texts)
    if crosses:
        out.append(f"正文「×」待填 {crosses} 处（金额 / 附注编号等）")
    if any(_PENDING_DATE_RE.search(m.group("m") + m.group("d")) for t in texts for m in _SIGN_DATE_RE.finditer(t)):
        out.append("落款日期（月、日）")
    toc = toc_pending_pages(doc)
    if toc:
        out.append(f"目录页码（{'、'.join(toc)}，装订后按实际页数填写）")
    return out


# ── 编排 ──────────────────────────────────────────────────────────────────────


@dataclass
class PrepareResult:
    """``prepare_report_body`` 的处理计数。"""

    optional_sections: int = 0
    emphasis_inserted: bool = False
    dates: int = 0
    equity_renamed: int = 0
    renumbered: int = 0


def prepare_report_body(
    doc,
    *,
    opinion_choice: str | None,
    audit_year: int | None,
    company_name: str | None,
    report_date: Any = None,
) -> PrepareResult:
    """preview 阶段（替换占位符之后、扫描可选段之前）：OPT 标记重放 → 强调事项段 → 落款日期 → 权益表名称 → 序号。

    ``opinion_choice`` 为前端选择的意见类型（含 ``unqualified_with_emphasis``，manifest 已把它归一到无保留模板）。
    """
    res = PrepareResult()
    res.optional_sections = normalize_optional_markers(doc)
    if opinion_choice == "unqualified_with_emphasis":
        res.emphasis_inserted = insert_emphasis_section(doc)
    res.dates = normalize_signing_dates(doc, report_date=parse_report_date(report_date), audit_year=audit_year)
    res.equity_renamed = normalize_equity_statement_name(doc, company_name)
    res.renumbered = renumber_section_headings(doc)
    return res


def finalize_report_body(doc, *, standalone: bool, listed: bool) -> GuidanceStripStats:
    """confirm 阶段（应用可选段、另存含指引副本、``strip_guidance_notes`` 之后）：剥除编制提示 → 序号再顺延。"""
    st = strip_report_guidance(doc, standalone=standalone, listed=listed)
    renumber_section_headings(doc)
    return st
