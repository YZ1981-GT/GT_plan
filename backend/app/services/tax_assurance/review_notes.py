"""审核说明：样表「审核报告说明」规则表 → 段落（预览 + Word）。

规则表每行一段：A 标记（※ 必显 / ﹟ 无数据整节隐藏）、B 内容（``{0}{1}…`` 占位）、C 格式（2~9 标题层级、
文本1 / 文本2 正文）、E 是否加粗、G 编号格式（1~7）、H 缩进（厘米，「左,首行」）、I 占位数、J~X 占位值。
显示规则由案例 1 的缓存值与案例报告逐段对照反推（design §4），``layout`` 是不读库的纯函数，单测直接构造规则行。

人工修改（spec citar-table-manual-edit R8）：每段正文可改、可删除、可恢复；存 ``tax_workpaper_inputs`` 保留编号
``__review_notes__``；编号照旧自动（删段后重新编号），预览与 Word 用同一份段落。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from docx import Document
from docx.shared import Cm
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tax_workpaper_models import REVIEW_NOTES_SHEET_CODE
from app.services import tax_workpaper_service as tws
from app.services.tax_assurance.common import DATA_DIR, replace_in_document, save_docx, value_text, year_text
from app.services.tax_formula_engine import XlError
from app.services.tax_workbook import to_a1

RULES_SHEET = "审核报告说明"
HEADER_SHEET = "审核报告说明-页眉页脚"
TEMPLATE = DATA_DIR / "review_notes.docx"
FIRST_ROW = 2
VALUE_COL = 10  # J
MAX_VALUES = 15  # J~X

MARK_ALWAYS = "※"
MARK_HIDE_EMPTY = "﹟"
NONE_TEXT = "无。"

#: 编号格式 1~7（样表「格式编制说明」）
_CN_DIGITS = "零一二三四五六七八九"
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_ROMAN = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]

#: 内容格式 → Word 样式（案例 docx 的样式名；标题 2~9、文本1 / 文本2）
STYLE_NAMES = {**{str(n): f"致同标题{n}" for n in range(2, 10)}, "文本1": "致同文本1", "文本2": "致同文本2"}

#: 句尾引出下文的从句：「。具体调整数据如下：」「，计算过程如下：」「，其中：」
_LEAD_OUT_RE = re.compile(r"[，。]\s*(具体[^，。；：]*如下|计算过程如下|其中)：$")
#: 计算过程（结果为 0 时不列）
_CALC_RE = re.compile(r"[，。]\s*计算过程如下：")


def _cn_number(n: int) -> str:
    if n < 10:
        return _CN_DIGITS[n]
    tens, ones = divmod(n, 10)
    return ("" if tens == 1 else _CN_DIGITS[tens]) + "十" + (_CN_DIGITS[ones] if ones else "")


def _roman(n: int) -> str:
    out = ""
    for v, s in _ROMAN:
        while n >= v:
            out += s
            n -= v
    return out


def number_text(fmt: int, n: int) -> str:
    """编号格式 1~7：一、/（一）/1、/（1）/①/I./i."""
    if fmt == 1:
        return f"{_cn_number(n)}、"
    if fmt == 2:
        return f"（{_cn_number(n)}）"
    if fmt == 3:
        return f"{n}、"
    if fmt == 4:
        return f"（{n}）"
    if fmt == 5:
        return _CIRCLED[n - 1] if n <= len(_CIRCLED) else f"({n})"
    if fmt == 6:
        return f"{_roman(n)}."
    if fmt == 7:
        return f"{_roman(n).lower()}."
    return ""


@dataclass
class Rule:
    row: int
    mark: str
    template: str
    fmt: str
    bold: bool = False
    number_fmt: int | None = None
    indent: tuple[float | None, float | None] = (None, None)
    values: list[Any] = field(default_factory=list)
    #: ※ 标题下补的「无。」（不是规则表里的行；段落键带 -none）
    synthetic: bool = False

    @property
    def level(self) -> int | None:
        """标题层级（内容格式 2~9）；正文 None。"""
        return int(self.fmt) if self.fmt.isdigit() else None

    def render(self) -> str:
        """金额占位（后接「元」「万元」）按 #,##0.00；其余数字按常规格式（69 人不写成 69.00）。"""
        out = self.template
        money = {int(m.group(1)) for m in re.finditer(r"\{(\d+)\}万?元", self.template)}
        for i, v in enumerate(self.values):
            text = value_text(v) if i in money or not isinstance(v, Decimal) else general_number(v)
            out = out.replace("{" + str(i) + "}", text)
        return out.strip()


def general_number(v: Decimal) -> str:
    """Excel 常规格式：整数不带小数，其余去掉末尾 0。"""
    if v == v.to_integral_value():
        return str(int(v))
    return format(v.normalize(), "f")


# ── 显示判断 ──
def _is_dead_value(v: Any) -> bool:
    """规则表用 IF(…,"0",…) 表示「不适用」：占位值是字符串 "0" 或空。"""
    return v is None or (isinstance(v, str) and v.strip() in ("", "0"))


def is_dead(rule: Rule) -> bool:
    """占位值全是「不适用」⇒ 这一行不出（※ 也不出）。"""
    return bool(rule.values) and all(_is_dead_value(v) for v in rule.values)


def _money_slots(rule: Rule) -> list[int]:
    """后面紧跟「元」的占位（人、万元、项目名不算金额）。"""
    return [int(m.group(1)) for m in re.finditer(r"\{(\d+)\}元", rule.template) if int(m.group(1)) < len(rule.values)]


def _nonzero(v: Any) -> bool:
    if isinstance(v, Decimal):
        return abs(v) >= Decimal("0.005")
    if isinstance(v, str):
        s = v.replace(",", "").replace("元", "").strip()
        try:
            return abs(Decimal(s)) >= Decimal("0.005")
        except InvalidOperation:  # 不是数字的文字
            return bool(s) and s != "0"
    if isinstance(v, XlError):
        return False
    return bool(v)


def has_data(rule: Rule) -> bool:
    """有金额占位看金额是否非零；没有金额占位看任一占位非空非零；没有占位的固定文字算有。"""
    if not rule.values:
        return True
    slots = _money_slots(rule)
    if slots:
        return any(_nonzero(rule.values[i]) for i in slots)
    return any(_nonzero(v) and not _is_dead_value(v) for v in rule.values)


@dataclass
class _Node:
    rule: Rule | None
    children: list[_Node] = field(default_factory=list)
    visible: bool = False


def _build_tree(rules: list[Rule]) -> _Node:
    root = _Node(None)
    stack: list[tuple[int, _Node]] = [(0, root)]
    for rule in rules:
        level = rule.level
        if level is None:
            stack[-1][1].children.append(_Node(rule))
            continue
        while stack[-1][0] >= level:
            stack.pop()
        node = _Node(rule)
        stack[-1][1].children.append(node)
        stack.append((level, node))
    return root


def _body_visible(rule: Rule) -> bool:
    if is_dead(rule):
        return False
    return rule.mark == MARK_ALWAYS or has_data(rule)


def _resolve(node: _Node, parent_visible: bool) -> None:
    """标题：※ 随上级；其余 = 自带占位看自身有无数据，否则看其下第一个正文行（紧跟子标题时看任一子标题）。"""
    for child in node.children:
        rule = child.rule
        if rule.level is None:
            child.visible = parent_visible and _body_visible(rule)
            continue
        if not parent_visible or is_dead(rule):
            _resolve(child, False)
            child.visible = False
            continue
        if rule.mark == MARK_ALWAYS:
            child.visible = True
            _resolve(child, True)
            continue
        if rule.values:
            child.visible = has_data(rule)
            _resolve(child, child.visible)
            continue
        # 先按「上级可见」解出下级，再据下级决定本标题；「不适用」的引导句（如 IF(…,"0","具体计算过程如下：")）跳过
        _resolve(child, True)
        first = next((c for c in child.children if c.rule.level is not None or not is_dead(c.rule)), None)
        if first is None:
            child.visible = False
        elif first.rule.level is None:
            child.visible = first.visible
        else:
            child.visible = any(c.visible for c in child.children if c.rule.level is not None)
        if not child.visible:
            _resolve(child, False)


def _flatten(node: _Node, out: list[tuple[Rule, int | None]], parent_level: int | None = None) -> None:
    """可见行按顺序展开；每行带所属标题层级（正文用）。※ 标题下没有可见正文时补「无。」。"""
    for child in node.children:
        if not child.visible:
            continue
        rule = child.rule
        if rule.level is None:
            out.append((rule, parent_level))
            continue
        out.append((rule, rule.level))
        start = len(out)
        _flatten(child, out, rule.level)
        # 有下文规则但一条都不显示的 ※ 标题（重大事项、其他事项披露）：补「无。」；本身没有下文的（附件1）不补
        if rule.mark == MARK_ALWAYS and child.children and not any(r.level is None for r, _ in out[start:]):
            out.append((Rule(row=rule.row, mark=MARK_ALWAYS, template=NONE_TEXT, fmt="文本1", synthetic=True), rule.level))


def _cut_zero_calculation(flat: list[tuple[Rule, int | None]]) -> list[tuple[Rule, int | None, str]]:
    """结果为 0 时不列计算过程：「…0.00元，计算过程如下：…」截到「…0.00元。」，句尾引出的计算行一并不出。"""
    out: list[tuple[Rule, int | None, str]] = []
    skipping = False
    for rule, owner in flat:
        if rule.level is not None:
            skipping = False
        elif skipping:
            continue
        text = rule.render()
        m = _CALC_RE.search(text) if rule.level is None else None
        if m and rule.values and not _nonzero(rule.values[0]):
            skipping = m.end() == len(text)
            text = text[: m.start()] + "。"
        out.append((rule, owner, text))
    return out


def _list_lengths(items: list[tuple[Rule, int | None, str]]) -> list[int]:
    """每个带编号正文行所在列表（连续、同编号格式）的项数；单独一项不编号。"""
    lengths = [0] * len(items)
    i = 0
    while i < len(items):
        rule = items[i][0]
        if rule.level is not None or not rule.number_fmt:
            i += 1
            continue
        j = i
        while j + 1 < len(items) and items[j + 1][0].level is None and items[j + 1][0].number_fmt == rule.number_fmt:
            j += 1
        for k in range(i, j + 1):
            lengths[k] = j - i + 1
        i = j + 1
    return lengths


def paragraph_key(rule: Rule) -> str:
    """段落键：规则表行号；※ 标题下补的「无。」带 -none。人工修改按它存。"""
    return f"r{rule.row}-none" if rule.synthetic else f"r{rule.row}"


def _visible_items(rules: list[Rule]) -> list[tuple[Rule, int | None, str]]:
    root = _build_tree(rules)
    _resolve(root, True)
    flat: list[tuple[Rule, int | None]] = []
    _flatten(root, flat)
    return _cut_zero_calculation(flat)


def _same_text(a: Any, b: Any) -> bool:
    """比自动文字是否变化：不计句末标点（删掉相邻段会改「；」/「。」）。"""
    return str(a or "").strip().rstrip("。；，：") == str(b or "").strip().rstrip("。；，：")


def layout(rules: list[Rule], edits: dict[str, dict] | None = None) -> list[dict]:
    """规则行 → 段落：显示判断、编号、句末标点。

    ``edits``：人工修改 {段落键: {"text": 正文 | None(删除本段), "auto": 修改时的自动正文}}（spec citar-table-manual-edit R8）。
    显示判断不受影响；删除的段不出、不占编号；改过的段用人工正文（编号前缀照旧自动、不再做句末标点处理）。
    """
    return _layout_items(_visible_items(rules), edits or {})


def _layout_items(all_items: list[tuple[Rule, int | None, str]], edits: dict[str, dict]) -> list[dict]:
    deleted = {k for k, e in edits.items() if e.get("text") is None}
    items = [it for it in all_items if paragraph_key(it[0]) not in deleted]
    list_lengths = _list_lengths(items)

    paragraphs: list[dict] = []
    counters: dict[int, int] = {}
    for i, (rule, owner_level, text) in enumerate(items):
        nxt = items[i + 1][0] if i + 1 < len(items) else None
        if rule.level is None:
            # 引出下文的句尾（具体…如下：/ 计算过程如下：/ 其中：）后面没有本节内容 ⇒ 去掉
            ends_section = nxt is None or (nxt.level is not None and owner_level is not None and nxt.level <= owner_level)
            if ends_section and _LEAD_OUT_RE.search(text):
                text = _LEAD_OUT_RE.sub("", text).rstrip("，；。") + "。"
            # 列表最后一项「；」改「。」
            if text.endswith("；") and (nxt is None or nxt.level is not None or nxt.number_fmt != rule.number_fmt or nxt.fmt != rule.fmt):
                text = text[:-1] + "。"
        prefix = ""
        if rule.level is not None and rule.level <= 3:
            # 「附件1」、大标题、第 N 部分：编号计数全部清零
            counters.clear()
        if rule.number_fmt and (rule.level is not None or list_lengths[i] > 1):
            n = counters.get(rule.number_fmt, 0) + 1
            counters[rule.number_fmt] = n
            for k in [k for k in counters if k > rule.number_fmt]:
                del counters[k]
            prefix = number_text(rule.number_fmt, n)
        key = paragraph_key(rule)
        edit = edits.get(key)
        body = edit["text"] if edit is not None else text
        paragraphs.append({
            "key": key,
            "row": rule.row,
            "text": prefix + body,
            "number": prefix,
            "body": body,
            "auto_body": text,
            "edited": edit is not None,
            # 改过的段：自动文字（数据）在修改之后又变了
            "auto_changed": edit is not None and not _same_text(edit.get("auto"), text),
            "style": rule.fmt,
            "level": rule.level,
            "bold": rule.bold,
            "indent": list(rule.indent),
        })
    return paragraphs


def layout_with_edits(rules: list[Rule], edits: dict[str, dict]) -> dict:
    """段落 + 已删除的段（本该显示，可恢复）+ 数据变化后不再显示的修改（可丢弃）。"""
    items = _visible_items(rules)
    paragraphs = _layout_items(items, edits)
    auto = {p["key"]: p for p in _layout_items(items, {})}
    deleted = [
        {"key": k, "row": auto[k]["row"], "auto_text": auto[k]["text"]}
        for k in auto if k in edits and edits[k].get("text") is None
    ]
    orphans = [
        {"key": k, "text": e.get("text"), "auto": e.get("auto")}
        for k, e in edits.items() if k not in auto
    ]
    return {"paragraphs": paragraphs, "deleted": deleted, "orphans": orphans}


# ── 人工修改的存储（tax_workpaper_inputs 保留编号 __review_notes__） ──
_KEY_RE = re.compile(r"^r\d{1,5}(-none)?$")
MAX_EDITS = 2000
MAX_EDIT_TEXT = 2000


def _stored_edits(row) -> dict[str, dict]:
    raw = (row.inputs or {}).get(REVIEW_NOTES_SHEET_CODE, {}) if row else {}
    return {k: v for k, v in raw.items() if isinstance(v, dict)}


def _clean_edits(edits: dict[str, Any]) -> dict[str, dict]:
    if len(edits or {}) > MAX_EDITS:
        raise HTTPException(status_code=422, detail="修改的段落过多")
    clean: dict[str, dict] = {}
    for key, raw in (edits or {}).items():
        if not _KEY_RE.match(str(key)) or not isinstance(raw, dict):
            raise HTTPException(status_code=422, detail=f"段落键无效：{key}")
        text, auto = raw.get("text"), raw.get("auto")
        for label, v in (("正文", text), ("自动文字", auto)):
            if v is not None and not isinstance(v, str):
                raise HTTPException(status_code=422, detail=f"{label}只能是文字")
            if isinstance(v, str) and len(v) > MAX_EDIT_TEXT:
                raise HTTPException(status_code=422, detail=f"{label}超过 {MAX_EDIT_TEXT} 字")
        if isinstance(text, str) and not text.strip():
            raise HTTPException(status_code=422, detail="段落文字不能为空；不要这一段请点「删除本段」")
        clean[str(key)] = {"text": text.strip() if isinstance(text, str) else None, "auto": auto}
    return clean


async def save_edits(db: AsyncSession, project_id: UUID, year: int, version: int, edits: dict[str, Any], user_id: UUID) -> None:
    """整份替换本项目本年度审核说明的人工修改；不在 ``edits`` 里的段恢复自动文字。"""
    await tws._project(db, project_id)
    clean = _clean_edits(edits)
    await tws._upsert(db, project_id, year, REVIEW_NOTES_SHEET_CODE, version, {REVIEW_NOTES_SHEET_CODE: clean}, user_id)


# ── 读规则表 ──
def _indent(raw: Any) -> tuple[float | None, float | None]:
    if raw in (None, ""):
        return (None, None)
    parts = [p.strip() for p in str(raw).replace("，", ",").split(",")]
    nums: list[float | None] = []
    for p in parts[:2]:
        try:
            nums.append(float(p))
        except ValueError:
            nums.append(None)
    while len(nums) < 2:
        nums.append(None)
    return (nums[0], nums[1])


def _int(raw: Any) -> int | None:
    if raw in (None, "") or isinstance(raw, bool):
        return None
    try:
        return int(Decimal(str(raw)))
    except InvalidOperation:  # 文字
        return None


def read_rules(wb, value_of) -> list[Rule]:
    """``value_of(ref)``：规则表某格的最终值（公式已求值）。"""
    sheet = wb.model["sheets"].get(RULES_SHEET)
    if not sheet:
        raise HTTPException(status_code=500, detail="计算模型缺少审核报告说明规则表，请重新运行生成脚本")
    last = max(int(re.sub(r"\D", "", ref)) for ref in sheet["cells"])
    rules: list[Rule] = []
    for r in range(FIRST_ROW, last + 1):
        template = value_of(f"B{r}")
        if template in (None, ""):
            continue
        n = _int(value_of(f"I{r}")) or 0
        rules.append(Rule(
            row=r,
            mark=str(value_of(f"A{r}") or "").strip(),
            template=str(template),
            fmt=str(value_of(f"C{r}") or "").strip(),
            bold=str(value_of(f"E{r}") or "").strip() == "是",
            number_fmt=_int(value_of(f"G{r}")),
            indent=_indent(value_of(f"H{r}")),
            values=[value_of(to_a1(r, VALUE_COL + i)) for i in range(min(n, MAX_VALUES))],
        ))
    return rules


def blank_text_slots(rules: list[Rule], blank_keys) -> None:
    """只引用一个空格的公式：金额占位（后接「元」）按 0 参与（「账载金额0.00元」），文字占位留空（信用代码未填不写「0」）。"""
    for rule in rules:
        money = {int(m.group(1)) for m in re.finditer(r"\{(\d+)\}万?元", rule.template)}
        for i in range(len(rule.values)):
            if i not in money and (RULES_SHEET, rule.row, VALUE_COL + i) in blank_keys:
                rule.values[i] = None


async def build(db: AsyncSession, project_id: UUID, year: int) -> dict:
    wb = tws.load_workbook()
    seeds = [k for k in wb.formulas if k[0] in (RULES_SHEET, HEADER_SHEET)]
    rows = await tws._rows(db, project_id, year)
    # 人工修改与版本立即取成普通值（之后取数查询失败时会话里的 ORM 对象会过期）
    own = rows.get(REVIEW_NOTES_SHEET_CODE)
    version = own.version if own else 0
    edits = _stored_edits(own)
    ev = await tws.evaluate_keys(db, project_id, year, seeds, rows)
    rules = read_rules(wb, lambda ref: ev.calc_value(RULES_SHEET, ref))
    blank_text_slots(rules, getattr(ev.computed, "blank", set()))
    for rule in rules:
        rule.template = year_text(rule.template, year)
        rule.values = [year_text(v, year) if isinstance(v, str) else v for v in rule.values]
    header = [year_text(value_text(ev.value(HEADER_SHEET, f"A{r}")), year) for r in (2, 3)]
    footer = [value_text(ev.value(HEADER_SHEET, f"B{r}")) for r in (2, 3, 4)]
    laid = layout_with_edits(rules, edits)
    return {
        "year": year,
        "version": version,
        "header": [h for h in header if h],
        "footer": [f for f in footer if f],
        "paragraphs": laid["paragraphs"],
        "edits": edits,
        "deleted": laid["deleted"],
        "orphans": laid["orphans"],
        "notices": ev.notices,
    }


# ── Word ──
def export_docx(data: dict) -> bytes:
    if not TEMPLATE.is_file():
        raise HTTPException(status_code=500, detail="审核说明模板缺失，请运行 gen_tax_assurance_templates.py")
    doc = Document(str(TEMPLATE))
    styles = {s.name for s in doc.styles}
    header = data["header"]
    replace_in_document(doc, {
        "{{client}}": header[0] if header else "",
        "{{header_title}}": header[1] if len(header) > 1 else "",
    })
    for p in data["paragraphs"]:
        style = STYLE_NAMES.get(p["style"])
        para = doc.add_paragraph(style=style if style in styles else None)
        run = para.add_run(p["text"])
        if p["bold"]:
            run.bold = True
        left, first = p["indent"]
        if left is not None:
            para.paragraph_format.left_indent = Cm(left)
        if first is not None:
            para.paragraph_format.first_line_indent = Cm(first - (left or 0))
    return save_docx(doc)
