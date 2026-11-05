"""纳税调整汇总表（CITAR 税审底稿 · 纳税调整汇总表）：把二~五类税审底稿里的纳税调整逐项列出，并验算纳税调整后所得。

- 二类（综合利润类）：底稿里手填的「审核调整额」。每组（一行，或按列排的表一列）去掉后重算申报表 A100000「利润总额」，
  差额为正记调增、为负记调减；「利润总额」行取全部审核调整额去掉后的数（审核调整前）。不影响利润总额的（成本归集表等）不列；
  影响利润总额、账上有数但没调整的表列一行 0。
- 三类（纳税调整类）：按申报表 A105000 各明细行的调增 / 调减列（与 A100000 纳税调整增加额 / 减少额同口径，合计必然对得上）；
  「账载 − 税收」直接取附表合计的行（职工薪酬 A105050、资产折旧摊销 A105080、未按权责发生制确认的收入 A105020）按附表明细逐项列；
  没有调整的明细行列 0。调整底稿位置 = 沿公式往上找到的第一张底稿的格子。
- 五类（税收优惠）：A100000「免税、减计收入及加计扣除」各行引用的 5-01-01 审核确认额，按 5-01-01 G 列汇总成免税 / 减计 / 加计
  三行，名称统一「免税、减计收入及加计扣除」（样表写法）。
- 四类（境外所得）：现阶段不计入验算（样表注明）。列一行「境外所得税纳税调整 / 抵免」（4-01 可抵免所得税额），标 ``excluded``。
无金额的行也返回（用户 2026-11-05：没有金额的项也显示），页面可勾「只看有金额的项」。

验算：利润总额 + 调增 − 调减 − 免税 − 减计 − 加计 = 纳税调整后所得，并与申报表 A100000「纳税调整后所得」（剔除境外部分）核对。
只读，不写任何数据。
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tax_workpaper_models import RESERVED_SHEET_CODES
from app.services import tax_workpaper_service as tws
from app.services.tax_formula_engine import iter_refs, number_text
from app.services.tax_workbook import Key, TaxWorkbook, parse_a1, to_a1

EPS = Decimal("0.005")
CENT = Decimal("0.01")
ZERO = Decimal(0)

MAIN = "A100000"
DETAIL = "A105000"
WP_PREFERENCE = "5-01-01"
NOT_APPLICABLE = "不适用"
INCREASE, DECREASE = "调增", "调减"
EXEMPT, REDUCE, PLUS = "免税", "减计", "加计"
FLIP = {INCREASE: DECREASE, DECREASE: INCREASE}

# A100000 用到的行（按 C 列文字定位，不写死行号）
_MAIN_LABELS = {
    "profit": r"^三、利润总额",
    "foreign": r"^减：境外所得（",
    "inc": r"^加：纳税调整增加额",
    "dec": r"^减：纳税调整减少额",
    "free": r"^减：免税、减计收入及加计扣除",
    "offset": r"^加：境外应税所得抵减境内亏损",
    "result": r"^四、纳税调整后所得",
}


# ── 文字处理 ──
_SPACE = re.compile(r"\s+")
_PREFIX = re.compile(r"^(?:[（(][一二三四五六七八九十\d]+[）)]|[一二三四五六七八九十]+、|\d+(?:\.\d+)*[.、．](?!\d)|其中[：:]|减[：:]|加[：:])\s*")
_TAIL = re.compile(r"[（(](?:[^（）()]*填写A\d+[^（）()]*|[\d+＋\-－×*…\s.]+)[）)]\s*$")
_TITLE_SUFFIX = ("明细审核表", "审核表", "明细表")


def _squash(text: Any) -> str:
    return _SPACE.sub("", str(text or "")).strip()


def clean_label(text: Any) -> str:
    """去掉行次编号、「其中：」与「（填写A105050）」「（2+3）」这类尾注。"""
    s = _squash(text)
    for _ in range(4):
        t = _TAIL.sub("", _PREFIX.sub("", s))
        if t == s:
            break
        s = t
    return s.strip("：:")


def subject_of(title: Any) -> str:
    """底稿标题 → 科目名：「管理费用审核表」→「管理费用」，「审核表（其他损益类科目）」→「其他损益类科目」。"""
    s = _squash(title)
    for suffix in _TITLE_SUFFIX:
        if s.endswith(suffix):
            return s[: -len(suffix)]
    m = re.search(r"[（(]([^）)]+)[）)]", s)
    if m:
        return m.group(1)
    return s


def money(v: Decimal | None) -> str | None:
    return None if v is None else str(v.quantize(CENT))


def _num(v: Any) -> Decimal:
    return v if isinstance(v, Decimal) else ZERO


class _Book:
    """一次求值的取值、文字，以及沿公式往上找底稿格子。"""

    def __init__(self, wb: TaxWorkbook, ev: tws.Evaluation) -> None:
        self.wb = wb
        self.ev = ev
        self.code_of: dict[str, str] = {}
        self.workpaper_sheets: set[str] = set()
        params_sheet = wb.model["params_sheet"]
        for code, sheets in wb.codes.items():
            is_wp = tws.code_domain(wb, code) == tws.WORKPAPER_DOMAIN and code not in RESERVED_SHEET_CODES
            for s in sheets:
                self.code_of[s] = code
                if is_wp and s != params_sheet:
                    self.workpaper_sheets.add(s)

    def raw(self, key: Key) -> Any:
        ev = self.ev
        if key in self.wb.formulas:
            if key in ev.inputs and key not in ev.computed:
                return ev.inputs[key]
            return ev.computed.get(key)
        if key in ev.inputs:
            return ev.inputs[key]
        if key in ev.rule_values:
            return ev.rule_values[key]
        return self.wb.consts.get(key)

    def num(self, key: Key) -> Decimal:
        return _num(self.raw(key))

    def text(self, key: Key) -> str:
        v = self.raw(key)
        return "" if v is None or isinstance(v, (Decimal, bool)) else _squash(v)

    def trace(self, key: Key) -> Key | None:
        """沿公式往上找底稿上的格子（按公式从左到右深度优先，不穿过底稿）；有数的优先，否则取第一个。
        深度优先：A105000「资产折旧、摊销」先到 A105080 第一节固定资产（3-03-01），不会因层数浅先落到油气投资表。"""
        seen = {key}
        stack = [key]
        hits: list[Key] = []
        while stack and len(seen) < 400:
            ast = self.wb.formulas.get(stack.pop())
            if ast is None:
                continue
            nxt: list[Key] = []
            for _, sheet, r1, c1, r2, c2 in iter_refs(ast):
                for r in range(r1, r2 + 1):
                    for c in range(c1, c2 + 1):
                        ref = (sheet, r, c)
                        if ref in seen:
                            continue
                        seen.add(ref)
                        if sheet in self.workpaper_sheets:
                            hits.append(ref)
                        else:
                            nxt.append(ref)
            stack.extend(reversed(nxt))
        for ref in hits:
            if abs(self.num(ref)) >= EPS:
                return ref
        return hits[0] if hits else None

    def loc(self, key: Key | None) -> dict | None:
        if key is None or key[0] not in self.code_of:
            return None
        domain = "workpaper" if key[0] in self.workpaper_sheets else "tax_return"
        return {"domain": domain, "code": self.code_of[key[0]], "sheet": key[0], "ref": to_a1(key[1], key[2])}


def main_rows(wb: TaxWorkbook) -> dict[str, int]:
    """A100000 各关键行的行号（按 C 列文字定位）；模板变了找不到就报错，不猜。"""
    texts = {}
    for ref, raw in wb.model["sheets"][MAIN]["cells"].items():
        m = re.fullmatch(r"C(\d+)", ref)
        if m and isinstance(raw, str):
            texts[int(m.group(1))] = _squash(raw)
    out: dict[str, int] = {}
    for name, pattern in _MAIN_LABELS.items():
        rows = [r for r, t in texts.items() if re.search(pattern, t)]
        if len(rows) != 1:
            raise RuntimeError(f"申报表 {MAIN} 找不到唯一的「{pattern}」行：{rows}")
        out[name] = rows[0]
    return out


def _linear_same_column(ast: tuple, sheet: str, col: int) -> dict[int, Decimal] | None:
    """公式只是本表本列若干格的加减（SUM / + / - / 一元负号）时返回 {行: 系数}，否则 None。"""
    kind = ast[0]
    if kind == "ref":
        _, s, r1, c1, r2, c2 = ast
        if s != sheet or c1 != col or c2 != col:
            return None
        return {r: Decimal(1) for r in range(r1, r2 + 1)}
    if kind == "neg":
        inner = _linear_same_column(ast[1], sheet, col)
        return None if inner is None else {r: -k for r, k in inner.items()}
    if kind == "call" and ast[1] == "SUM":
        out: dict[int, Decimal] = {}
        for arg in ast[2]:
            if arg[0] == "empty":
                continue
            part = _linear_same_column(arg, sheet, col)
            if part is None:
                return None
            for r, k in part.items():
                out[r] = out.get(r, ZERO) + k
        return out
    if kind == "bin" and ast[1] in ("+", "-"):
        left = _linear_same_column(ast[2], sheet, col)
        right = _linear_same_column(ast[3], sheet, col)
        if left is None or right is None:
            return None
        out = dict(left)
        sign = Decimal(1) if ast[1] == "+" else Decimal(-1)
        for r, k in right.items():
            out[r] = out.get(r, ZERO) + sign * k
        return out
    return None


def leaf_rows(wb: TaxWorkbook, sheet: str, col: int, total_row: int) -> dict[int, Decimal]:
    """把合计格按「本列加减」逐层展开到明细行：{明细行: 系数}。「其中」行加了又减，系数为 0 不列。"""
    leaves: dict[int, Decimal] = {}
    stack: list[tuple[int, Decimal]] = [(total_row, Decimal(1))]
    steps = 0
    while stack and steps < 2000:
        steps += 1
        row, k = stack.pop()
        ast = wb.formulas.get((sheet, row, col))
        parts = _linear_same_column(ast, sheet, col) if ast is not None else None
        if not parts or row in parts:
            leaves[row] = leaves.get(row, ZERO) + k
            continue
        stack.extend((r, k * c) for r, c in parts.items())
    return {r: k for r, k in leaves.items() if k != 0}


# ── 三类：A105000 明细行（职工薪酬 / 折旧摊销 / 权责发生制收入按附表明细） ──
_SECTION = re.compile(r"^[一二三四五六七八九十]+、")
_SUBITEM = re.compile(r"^[（(][一二三四五六七八九十]+[）)]")
_NUMBERED = re.compile(r"^\d+\.(?!\d)")
#: 资产折旧摊销附表的节名 → 汇总表里的叫法（样表示例「固定资产折旧-生产设备」）
_DEPRECIATION = {"固定资产": "固定资产折旧", "生产性生物资产": "生产性生物资产折旧", "无形资产": "无形资产摊销", "长期待摊费用": "长期待摊费用摊销"}


def _line_no(book: _Book, sheet: str, row: int) -> str:
    v = book.raw((sheet, row, 1))
    if isinstance(v, Decimal):
        return number_text(v)
    return _squash(v) or str(row)


def _row_text(book: _Book, sheet: str, row: int) -> str:
    """行标签（C 列有字取 C：A105080「所有固定资产 /（一）房屋、建筑物」）。"""
    for col in (3, 2):
        t = book.text((sheet, row, col))
        if t and t != "*":
            return t
    return ""


def _above(book: _Book, sheet: str, row: int, pattern: re.Pattern) -> str:
    for r in range(row - 1, 0, -1):
        t = book.text((sheet, r, 2))
        if pattern.match(t):
            return clean_label(t)
    return ""


def _detail_name(book: _Book, row: int) -> str:
    own = book.text((DETAIL, row, 2))
    label = clean_label(own)
    if _NUMBERED.match(own):
        parent = _above(book, DETAIL, row, _SUBITEM)
        return f"{parent}-{label}" if parent else label
    if label == "其他":
        parent = "纳税调整项目" if _SECTION.match(own) else _above(book, DETAIL, row, _SECTION)
        return f"{parent}-其他"
    return label


def _sub_name(book: _Book, sheet: str, row: int, line_name: str) -> str:
    own = _row_text(book, sheet, row)
    label = clean_label(own)
    if _SECTION.match(own):
        return f"{line_name}-其他" if label == "其他" else label
    section = _above(book, sheet, row, _SECTION)
    section = _DEPRECIATION.get(section, section)
    if not section:
        return label
    return f"{section}-{label}"


def _expand_ref(wb: TaxWorkbook, book: _Book, row: int) -> tuple[str, int, int, int, int] | None:
    """A105000 本行 C / D 是同一张附表同一行的两格、E = MAX(0,C-D) 或 ABS(MIN(0,C-D)) 时，返回
    (附表, 合计行, C 引用列, D 引用列, 符号)；符号 +1 = 账载 − 税收为调增，−1 = 税收 − 账载为调增。"""
    refs = []
    for col in (3, 4):
        ast = wb.formulas.get((DETAIL, row, col))
        if ast is None or ast[0] != "ref":
            return None
        _, sheet, r1, c1, r2, c2 = ast
        if (r1, c1) != (r2, c2) or sheet in book.workpaper_sheets or sheet == DETAIL:
            return None
        refs.append((sheet, r1, c1))
    (s1, r1, c1), (s2, r2, c2) = refs
    if s1 != s2 or r1 != r2:
        return None
    text = wb.formula_text.get((DETAIL, row, 5), "").replace(" ", "").upper()
    if text == f"=MAX(0,C{row}-D{row})":
        return s1, r1, c1, c2, 1
    if text == f"=ABS(MIN(0,C{row}-D{row}))":
        return s1, r1, c1, c2, -1
    return None


def _item(name: str, account: str, direction: str, amount: Decimal, location: dict | None, source: str) -> dict:
    return {"name": name, "account": account, "direction": direction, "amount": amount, "location": location, "source": source}


def _signed(name: str, amount: Decimal, direction: str, location: dict | None, source: str, account: str = NOT_APPLICABLE) -> dict:
    """金额为负时方向反过来（调增 −100 = 调减 100）。"""
    if amount < 0:
        direction, amount = FLIP.get(direction, direction), -amount
    return _item(name, account, direction, amount, location, source)


def single_ref(wb: TaxWorkbook, key: Key) -> Key | None:
    ast = wb.formulas.get(key)
    if ast is None or ast[0] != "ref":
        return None
    _, sheet, r1, c1, r2, c2 = ast
    return (sheet, r1, c1) if (r1, c1) == (r2, c2) else None


def _expand(wb: TaxWorkbook, book: _Book, spec: tuple, line_net: Decimal, line_name: str) -> list[dict] | None:
    """按附表明细逐项列；明细合计与 A105000 本行（调增 − 调减）对不上时返回 None，退回整行。"""
    sheet, total, col_p, col_m, sign = spec
    plus, minus = leaf_rows(wb, sheet, col_p, total), leaf_rows(wb, sheet, col_m, total)
    out: list[dict] = []
    acc = ZERO
    for r in sorted(set(plus) | set(minus)):
        net = sign * (plus.get(r, ZERO) * book.num((sheet, r, col_p)) - minus.get(r, ZERO) * book.num((sheet, r, col_m)))
        acc += net
        if abs(net) < EPS:
            continue
        key = (sheet, r, col_p)
        loc = book.loc(book.trace(key) or book.trace((sheet, r, col_m))) or book.loc(key)
        out.append(_signed(_sub_name(book, sheet, r, line_name), net, INCREASE, loc, f"{sheet} 第 {_line_no(book, sheet, r)} 行"))
    return out if abs(acc - line_net) < CENT else None


def detail_items(wb: TaxWorkbook, book: _Book, rows: dict[str, int]) -> tuple[list[dict], Decimal]:
    """三类：A105000 明细行 → 汇总项；返回（汇总项，境外所得相关行的调增 − 调减）。"""
    inc_ref, dec_ref = single_ref(wb, (MAIN, rows["inc"], 4)), single_ref(wb, (MAIN, rows["dec"], 4))
    if not inc_ref or not dec_ref or inc_ref[0] != DETAIL or dec_ref[0] != DETAIL:
        raise RuntimeError(f"申报表 {MAIN} 纳税调整增加额 / 减少额不是取自 {DETAIL} 合计")
    coef_e = leaf_rows(wb, DETAIL, inc_ref[2], inc_ref[1])
    coef_f = leaf_rows(wb, DETAIL, dec_ref[2], dec_ref[1])
    items: list[dict] = []
    foreign = ZERO
    for r in sorted(set(coef_e) | set(coef_f)):
        ekey, fkey = (DETAIL, r, inc_ref[2]), (DETAIL, r, dec_ref[2])
        e, f = coef_e.get(r, ZERO) * book.num(ekey), coef_f.get(r, ZERO) * book.num(fkey)
        if abs(e) < EPS and abs(f) < EPS:
            # 无调整的明细行也列（用户 2026-11-05：没有金额的项也显示），金额 0、方向空
            hit = book.trace(ekey) or book.trace(fkey)
            if not (hit and book.code_of.get(hit[0], "").startswith("4-")):
                loc = book.loc(hit) or book.loc(ekey if r in coef_e else fkey)
                items.append(_item(_detail_name(book, r), NOT_APPLICABLE, "", ZERO, loc,
                                   f"{DETAIL} 第 {_line_no(book, DETAIL, r)} 行"))
            continue
        hit = book.trace(ekey if abs(e) >= EPS else fkey)
        if hit and book.code_of.get(hit[0], "").startswith("4-"):
            foreign += e - f  # 境外所得分摊的共同支出：现阶段不计入
            continue
        name = _detail_name(book, r)
        spec = _expand_ref(wb, book, r)
        sub = _expand(wb, book, spec, e - f, name) if spec else None
        if sub is not None:
            items.extend(sub)
            continue
        source = f"{DETAIL} 第 {_line_no(book, DETAIL, r)} 行"
        if abs(e) >= EPS:
            items.append(_signed(name, e, INCREASE, book.loc(book.trace(ekey)) or book.loc(ekey), source))
        if abs(f) >= EPS:
            items.append(_signed(name, f, DECREASE, book.loc(book.trace(fkey)) or book.loc(fkey), source))
    return items, foreign


# ── 五类：A100000「免税、减计收入及加计扣除」各行 → 5-01-01 审核确认额 ──
PREFERENCE_NAME = "免税、减计收入及加计扣除"


def preference_items(wb: TaxWorkbook, book: _Book, rows: dict[str, int]) -> list[dict]:
    """按 5-01-01 G 列类别汇总成免税 / 减计 / 加计三行，名称统一「免税、减计收入及加计扣除」（样表写法，用户 2026-11-05），
    无金额也列。位置取该类别第一个有数的格子，都没数取第一个格子。"""
    sums = {EXEMPT: ZERO, REDUCE: ZERO, PLUS: ZERO}
    first: dict[str, Key] = {}
    first_hit: dict[str, Key] = {}
    for r in sorted(leaf_rows(wb, MAIN, 4, rows["free"])):
        key = (MAIN, r, 4)
        target = single_ref(wb, key) or key
        if target[0] in book.workpaper_sheets:
            probe = " ".join(book.text((target[0], target[1], c)) for c in range(2, 10))
        else:
            probe = book.text((MAIN, r, 3))
        direction = REDUCE if "减计" in probe else PLUS if "加计" in probe else EXEMPT
        amount = book.num(target)
        sums[direction] += amount
        first.setdefault(direction, target)
        if abs(amount) >= EPS:
            first_hit.setdefault(direction, target)
    source = f"{WP_PREFERENCE}「审核确认额」中备注为{{}}的行（{MAIN}「{PREFERENCE_NAME}」）"
    label = {EXEMPT: "免税收入", REDUCE: "减计收入", PLUS: "加计扣除"}
    return [
        _item(PREFERENCE_NAME, NOT_APPLICABLE, d, sums[d], book.loc(first_hit.get(d) or first.get(d)), source.format(label[d]))
        for d in (EXEMPT, REDUCE, PLUS)
    ]


# ── 四类：境外所得（现阶段不计入验算，只列出） ──
FOREIGN_CODE = "4-01"


def foreign_item(wb: TaxWorkbook, book: _Book) -> dict | None:
    """样表第 8 行「境外所得税纳税调整 / 抵免」：4-01「境外所得可抵免的所得税额」小计的合计行。
    按表头文字找格子；模板变了找不到就不列（境外部分现阶段不计入，不因此报错）。"""
    sheets = wb.codes.get(FOREIGN_CODE) or []
    if not sheets:
        return None
    sheet = sheets[0]
    head = sub = total = None
    texts = []
    for ref, raw in wb.model["sheets"][sheet]["cells"].items():
        if isinstance(raw, str):
            r, c = parse_a1(ref)
            texts.append((r, c, _squash(raw)))
    heads = [c for r, c, t in texts if r <= 9 and "可抵免的所得税额" in t]
    head = min(heads) if heads else None
    if head is not None:
        subs = [c for r, c, t in texts if r <= 9 and c >= head and t == "小计"]
        sub = min(subs) if subs else None
    totals = [r for r, c, t in texts if c <= 2 and r > 9 and t == "合计"]
    total = totals[0] if totals else None
    if sub is None or total is None:
        return None
    key = (sheet, total, sub)
    item = _item("境外所得税纳税调整", NOT_APPLICABLE, "抵免", book.num(key), book.loc(key),
                 f"{FOREIGN_CODE}「境外所得可抵免的所得税额」合计")
    item["excluded"] = True
    return item


# ── 二类：综合利润类底稿的审核调整额 ──
def _title(wb: TaxWorkbook, sheet: str) -> str:
    cells = wb.model["sheets"][sheet]["cells"]
    for r in (1, 2, 3):
        for c in range(1, 15):
            raw = cells.get(to_a1(r, c))
            if isinstance(raw, str) and "表" in raw:
                return raw
    return ""


def _layout(wb: TaxWorkbook, sheet: str) -> tuple[set[int], int, set[int], int | None]:
    """审核调整额所在列（列式表，返回列集合与表头行）或所在行（2-01 这类按列分项的表）；账载金额列。"""
    cols: set[int] = set()
    rows: set[int] = set()
    header_row, book_col = 0, None
    cells = wb.model["sheets"][sheet]["cells"]
    for ref, raw in cells.items():
        if not isinstance(raw, str):
            continue
        r, c = parse_a1(ref)
        t = _squash(raw)
        if 4 <= r <= 9 and "审核调整" in t and "确认" not in t:
            cols.add(c)
            header_row = max(header_row, r)
        elif 4 <= r <= 9 and "账载" in t and book_col is None:
            book_col = c
    if cols:
        return cols, header_row, rows, book_col
    for ref, raw in cells.items():
        r, c = parse_a1(ref)
        if c == 1 and r > 9 and isinstance(raw, str) and "审核调整" in _squash(raw) and "确认" not in _squash(raw):
            rows.add(r)
            below = cells.get(f"B{r + 1}")
            if isinstance(below, str) and _squash(below) in ("借方", "贷方"):
                rows.add(r + 1)
    return cols, 0, rows, None


def _row_label(book: _Book, sheet: str, row: int) -> str:
    for col in (1, 2, 3):
        t = book.text((sheet, row, col))
        if not t or t == "*" or re.fullmatch(r"[\d.]+", t):
            continue
        label = clean_label(t)
        if label:
            return label
    return ""


def _col_label(book: _Book, sheet: str, col: int) -> str:
    """按列分项的表（2-01 等）：第 6~8 行表头，合并格往左找。"""
    parts: list[str] = []
    for r in (6, 7, 8):
        for c in range(col, 1, -1):
            t = book.text((sheet, r, c))
            if t:
                if t not in parts:
                    parts.append(t)
                break
    return "-".join(parts)


def _accounts(book: _Book, key: Key, fallback: str) -> str:
    """账载金额格取数用到的客户科目（上级-明细）；没取数（手填 / 无规则）用底稿科目名。"""
    meta = book.ev.results_meta.get(key)
    tree = book.ev.book
    if meta is None or not meta.nodes or tree is None:
        return fallback
    names: list[str] = []
    for node in meta.nodes:
        path, cur = [], node
        while cur is not None and len(path) < 4:
            path.append(cur.label if cur.parent else cur.name)
            cur = tree.nodes.get(cur.parent) if cur.parent else None
        text = "-".join(reversed(path))
        if text not in names:
            names.append(text)
    return "、".join(names[:3]) + (f" 等 {len(names)} 个科目" if len(names) > 3 else "")


def _feeding_cells(wb: TaxWorkbook, needed: set[Key], sheets: list[str]) -> dict[str, list[Key]]:
    """每张二类底稿上，利润总额计算链里的公式直接读到的审核调整额格（成本归集表这类不进利润总额的表为空）。"""
    layouts = {s: _layout(wb, s) for s in sheets}
    out: dict[str, set[Key]] = {}
    for key in needed:
        sheet = key[0]
        if sheet not in layouts or key not in wb.formulas:
            continue
        cols, header_row, rows, _ = layouts[sheet]
        for _, s, r1, c1, r2, c2 in iter_refs(wb.formulas[key]):
            if s != sheet:
                continue
            for r in range(r1, r2 + 1):
                for c in range(c1, c2 + 1):
                    if (cols and c in cols and r > header_row) or (rows and r in rows and c >= 2):
                        out.setdefault(sheet, set()).add((sheet, r, c))
    return {s: sorted(ks, key=lambda k: (k[2], k[1])) for s, ks in out.items()}


def _has_amount(book: _Book, sheet: str) -> bool:
    """本表有没有取到或填过数（账上没有这类业务的表不列 0 行，如金融业、事业单位专用表）。"""
    ev = book.ev
    for values in (ev.rule_values, ev.inputs):
        for key, v in values.items():
            if key[0] == sheet and isinstance(v, Decimal) and abs(v) >= EPS:
                return True
    return False


def profit_items(wb: TaxWorkbook, book: _Book, profit_key: Key, sheets: list[str]) -> tuple[list[dict], Decimal, list[str]]:
    """二类：逐组去掉审核调整额重算利润总额。返回（汇总项，审核调整前利润总额，提示）。"""
    ev = book.ev
    groups: dict[tuple[str, int], list[Key]] = {}
    meta: dict[tuple[str, int], tuple[str, Key | None]] = {}  # 组 → (行 / 列, 账载金额格)
    for sheet in sheets:
        cols, header_row, rows, book_col = _layout(wb, sheet)
        if not cols and not rows:
            continue
        for key, v in ev.inputs.items():
            if key[0] != sheet or not isinstance(v, Decimal):
                continue
            if v == 0 and key not in wb.formulas:
                continue
            _, r, c = key
            if cols and c in cols and r > header_row:
                gid = (sheet, r)
                meta[gid] = ("row", (sheet, r, book_col) if book_col else None)
            elif rows and r in rows and c >= 2:
                gid = (sheet, -c)
                meta[gid] = ("col", None)
            else:
                continue
            groups.setdefault(gid, []).append(key)
    needed = wb.closure([profit_key])
    base = _num(wb.evaluate(needed, ev.inputs, ev.rule_values).get(profit_key))

    def profit_without(keys: set[Key]) -> Decimal:
        inputs = {k: v for k, v in ev.inputs.items() if k not in keys}
        return _num(wb.evaluate(needed, inputs, ev.rule_values).get(profit_key))

    all_keys = {k for ks in groups.values() for k in ks}
    before = profit_without(all_keys) if all_keys else base
    feeds = _feeding_cells(wb, needed, sheets)
    items: list[dict] = []
    silent: list[str] = []
    total = ZERO
    for sheet in sheets:
        code = book.code_of.get(sheet, sheet)
        subject = subject_of(_title(wb, sheet)) or code
        emitted = False
        for gid in sorted((g for g in groups if g[0] == sheet), key=lambda g: abs(g[1])):
            keys = groups[gid]
            effect = base - profit_without(set(keys))
            kind, book_key = meta[gid]
            label = _row_label(book, sheet, gid[1]) if kind == "row" else _col_label(book, sheet, -gid[1])
            name = subject if not label or label == subject else f"{subject}-{label}"
            if abs(effect) < EPS:
                if len(silent) < 5:
                    silent.append(f"{code} {name}")
                continue
            total += effect
            account = _accounts(book, book_key, subject) if book_key else subject
            first = sorted(keys, key=lambda k: (k[2], k[1]))[0]
            items.append(_signed(name, effect, INCREASE, book.loc(first), "审核调整额", account))
            emitted = True
        # 本表审核调整额会影响利润总额、账上有数、但没有调整：列一行 0（用户 2026-11-05：没有金额的项也显示）
        if not emitted and feeds.get(sheet) and _has_amount(book, sheet):
            items.append(_item(subject, subject, "", ZERO, book.loc(feeds[sheet][0]), "审核调整额"))
    notices = []
    if silent:
        notices.append(f"以下综合利润类底稿的审核调整额不影响利润总额（成本归集等），未列入：{'、'.join(silent)}")
    if abs(total - (base - before)) >= CENT:
        notices.append(f"综合利润类审核调整额逐项影响合计 {money(total)} 与整体影响 {money(base - before)} 不一致（调整项之间相互关联）")
    return items, base - total, notices


def _sum(items: list[dict], direction: str) -> Decimal:
    return sum((i["amount"] for i in items if i["direction"] == direction and not i.get("excluded")), ZERO)


async def build(db: AsyncSession, project_id: UUID, year: int) -> dict:
    wb = tws.load_workbook()
    ev = await tws.evaluate_keys(db, project_id, year, seeds(wb))
    return summarize(wb, ev, year)


def _profit_sheets(wb: TaxWorkbook) -> list[str]:
    return [s for code, ss in wb.codes.items() if code.startswith("2-")
            and tws.code_domain(wb, code) == tws.WORKPAPER_DOMAIN for s in ss]


def seeds(wb: TaxWorkbook) -> list[Key]:
    """求值起点：A100000 / A105000 全部公式（闭包含附表与三~五类底稿）+ 二类底稿打印区（行标签取数格）+ 4-01（境外行）。"""
    out = [k for k in wb.formulas if k[0] in (MAIN, DETAIL)]
    sheets = _profit_sheets(wb) + list(wb.codes.get(FOREIGN_CODE) or [])
    return out + [k for s in sheets for k in wb.print_keys(s)]


def summarize(wb: TaxWorkbook, ev: tws.Evaluation, year: int) -> dict:
    rows = main_rows(wb)
    profit_sheets = _profit_sheets(wb)
    book = _Book(wb, ev)

    profit_key = (MAIN, rows["profit"], 4)
    profit_list, profit_before, notices = profit_items(wb, book, profit_key, profit_sheets)
    detail_list, foreign_common = detail_items(wb, book, rows)
    pref_list = preference_items(wb, book, rows)
    foreign_row = foreign_item(wb, book)
    items = profit_list + detail_list + pref_list + ([foreign_row] if foreign_row else [])

    inc, dec = _sum(items, INCREASE), _sum(items, DECREASE)
    exempt, reduce_, plus = _sum(items, EXEMPT), _sum(items, REDUCE), _sum(items, PLUS)
    result = profit_before + inc - dec - exempt - reduce_ - plus
    foreign = book.num((MAIN, rows["foreign"], 4))
    offset = book.num((MAIN, rows["offset"], 4))
    declared = book.num((MAIN, rows["result"], 4))
    # 申报表纳税调整后所得 = 利润总额 − 境外所得 + 调增 − 调减 − 免税减计加计 + 境外抵减；去掉境外部分再比
    declared_domestic = declared + foreign - offset - foreign_common
    diff = result - declared_domestic

    notices = list(ev.notices) + notices
    if abs(foreign) >= EPS or abs(offset) >= EPS or abs(foreign_common) >= EPS:
        notices.append(
            f"申报表有境外所得相关金额（境外所得 {money(foreign)}、境外应税所得抵减境内亏损 {money(offset)}、"
            f"境外所得分摊的共同支出 {money(foreign_common)}），现阶段未计入本表")
    if abs(diff) >= CENT:
        notices.append(f"按本表算出的纳税调整后所得与申报表 {MAIN}（剔除境外部分）差 {money(diff)}，请核对相关底稿与申报表")

    def line(name: str) -> str:
        return _line_no(book, MAIN, rows[name])

    return {
        "year": year,
        "items": [{**i, "index": n, "amount": money(i["amount"])} for n, i in enumerate(items, 1)],
        "check": {
            "profit": money(profit_before),
            "profit_declared": money(book.num(profit_key)),
            "foreign": money(foreign),
            "increase": money(inc),
            "decrease": money(dec),
            "exempt": money(exempt),
            "reduce": money(reduce_),
            "plus": money(plus),
            "offset": money(offset),
            "result": money(result),
            "declared": money(declared),
            "declared_domestic": money(declared_domestic),
            "diff": money(diff),
            "lines": {k: line(k) for k in rows},
        },
        "notices": notices,
    }
