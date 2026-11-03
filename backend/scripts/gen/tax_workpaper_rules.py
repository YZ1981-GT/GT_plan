"""税审底稿「取数规则」中文原文 → 结构化取数项（生成脚本内部模块）。

样表部分 sheet 打印区下方有「取数规则」区：A 列目标格、B 列标记（@直取 / @说明）、C 列原文。
这里逐条按固定句式解析，展开到单个单元格；解析不了的规则抛 ``RuleParseError`` 点名，
不静默跳过。原文笔误按目标格纠正，纠正内容写进 ``corrections``，随模型一起提交以便核对。

输出（写入计算模型）：
- items：每个目标格一项 ``{sheet, ref, rule, status, op, ...}``，op 见 design §3
- lists：列表类规则（逐行列出明细科目）的定义 ``{id: {sheet, path, mode, exclude, refs}}``
- formulas：转成公式写进模型的规则 ``[(sheet, ref, formula)]``
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from openpyxl.utils.cell import column_index_from_string, coordinate_from_string, get_column_letter

ROOT = Path(__file__).resolve().parents[3]
STANDARD_CHART = ROOT / "backend" / "data" / "standard_account_chart.json"

MEASURES = {
    "本期借方发生额": "debit", "借方发生额": "debit",
    "本期贷方发生额": "credit", "贷方发生额": "credit",
    "期初余额": "opening", "期末余额": "closing",
    "期末借方余额": "closing_debit", "借方期末余额": "closing_debit",
    "期末贷方余额": "closing_credit", "贷方期末余额": "closing_credit",
}
_MEASURE_ALT = "|".join(sorted(MEASURES, key=len, reverse=True))

# 一级科目名的别名：规则里写的名称 → 标准科目表 / 客户科目表里的名称
PATH_ALIASES = {
    ("累计折旧", "生物性资产"): ["生产性生物资产累计折旧"],
    ("生物性资产",): ["生产性生物资产"],
}

# 原文笔误纠正：(sheet, 目标区域) → 改写；每条都登记原因
CORRECTIONS: dict[tuple[str, str], dict] = {
    ("3-07-04", "A7:A28"): {
        "text": "底稿取数余额表-长期应付款末级科目",
        "reason": "长期应付款审核表的名称列写成了「长期应收款末级科目」，金额列取的是长期应付款，按表名改为长期应付款",
    },
    ("3-03-01", "I36:I39"): {
        "text": "底稿取数余额表-累计折旧二级科目不能归类与上述分类的归集于此，取期末贷方余额",
        "reason": "原文「取期末借方余额期末贷方余额」两个口径并列，累计折旧取贷方余额，与 I11:I34 同口径",
    },
}
TEXT_FIXES = [
    ("底稿取数余额表表-", "底稿取数余额表-", "多写了一个「表」"),
    ("特殊权适用法", "特许权使用费", "「特殊权适用法」为「特许权使用费」笔误（同表 D14 行名）"),
]


class RuleParseError(ValueError):
    pass


@dataclass
class ParsedRules:
    items: list[dict] = field(default_factory=list)
    lists: dict[str, dict] = field(default_factory=dict)
    formulas: list[tuple[str, str, str]] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)


def expand_range(target: str) -> list[str]:
    parts = target.replace("$", "").split(":")
    (c1, r1), (c2, r2) = (coordinate_from_string(parts[0]), coordinate_from_string(parts[-1]))
    i1, i2 = column_index_from_string(c1), column_index_from_string(c2)
    return [f"{get_column_letter(c)}{r}" for c in range(i1, i2 + 1) for r in range(r1, r2 + 1)]


def _col(ref: str) -> str:
    return coordinate_from_string(ref)[0]


def _row(ref: str) -> int:
    return coordinate_from_string(ref)[1]


def _split_path(text: str) -> list[str]:
    parts = [p.strip() for p in text.split("-") if p.strip()]
    for key, alias in PATH_ALIASES.items():
        if tuple(parts[: len(key)]) == key:
            return alias + parts[len(key):]
    return parts


def _debit_names() -> set[str]:
    """借方的损益类科目（5xxx / 6xxx）：期末把借方发生额从贷方结转到本年利润。"""
    chart = json.loads(STANDARD_CHART.read_text(encoding="utf-8"))
    return {a["name"] for a in chart["accounts"] if a["direction"] == "debit" and a["code"][:1] in ("5", "6")}


class RuleParser:
    """逐条解析；``cell_text(sheet, ref)`` 取样表常量文本，``column_texts(sheet, col)`` 取打印区内某列全部文字。"""

    def __init__(
        self,
        cell_text: Callable[[str, str], str | None],
        column_texts: Callable[[str, str], list[str]],
        resolve_sheet: Callable[[str], str | None],
    ) -> None:
        self.cell_text = cell_text
        self.column_texts = column_texts
        self.resolve_sheet = resolve_sheet
        self.debit_names = _debit_names()
        self.out = ParsedRules()

    # ── 公共 ──
    def _status(self, mark: str) -> str:
        return "auto" if mark == "@直取" else "confirm"

    def _item(self, raw: dict, ref: str, status: str, op: str, **extra) -> None:
        self.out.items.append({
            "sheet": raw["sheet"], "ref": ref, "rule": str(raw.get("original") or raw["text"]),
            "status": status, "op": op, **extra,
        })

    def _side(self, path: list[str], side: str, raw: dict) -> str:
        """成本 / 费用类损益科目规则写「贷方发生额」的，实际取借方（贷方是期末结转）。"""
        measure = "credit" if side == "贷" else "debit"
        if measure == "credit" and path and path[0] in self.debit_names:
            note = f"{raw['sheet']} {raw['target']}：{path[0]}为借方科目，「贷方发生额」是期末结转，改取借方发生额"
            if note not in self.out.corrections:
                self.out.corrections.append(note)
            return "debit"
        return measure

    def _label_ref(self, sheet: str, row: int, col: str, target_col: str) -> str:
        """本行标签格：指定列是文字就用它；是序号（数字）或空则取目标列左侧最近的文字格。"""
        text = self.cell_text(sheet, f"{col}{row}")
        if text and not re.fullmatch(r"[\d.\s]+", text):
            return f"{col}{row}"
        for c in range(column_index_from_string(target_col) - 1, 0, -1):
            ref = f"{get_column_letter(c)}{row}"
            t = self.cell_text(sheet, ref)
            if t and not re.fullmatch(r"[\d.\s]+", t):
                return ref
        return f"{col}{row}"

    def _list_for(self, sheet: str, col: str, row: int) -> tuple[str, int] | None:
        for list_id, spec in self.out.lists.items():
            if spec["sheet"] != sheet:
                continue
            for i, ref in enumerate(spec["refs"]):
                if _col(ref) == col and _row(ref) == row:
                    return list_id, i
        return None

    def _list_by_rows(self, sheet: str, rows: list[int]) -> str | None:
        for list_id, spec in self.out.lists.items():
            if spec["sheet"] == sheet and [_row(r) for r in spec["refs"]] == rows:
                return list_id
        return None

    def _add_list(self, raw: dict, refs: list[str], path: list[str], mode: str, exclude: list[str], status: str) -> None:
        list_id = f"{raw['sheet']}!{raw['target']}"
        self.out.lists[list_id] = {"sheet": raw["sheet"], "path": path, "mode": mode, "exclude": exclude, "refs": refs}
        for i, ref in enumerate(refs):
            self._item(raw, ref, status, "list_name", list=list_id, index=i)

    # ── 解析 ──
    def parse_all(self, raw_rules: list[dict]) -> ParsedRules:
        fixed: list[dict] = []
        for raw in raw_rules:
            text = str(raw["text"] or "")
            fix = CORRECTIONS.get((raw["sheet"], raw["target"]))
            if fix:
                self.out.corrections.append(f"{raw['sheet']} {raw['target']}：{fix['reason']}")
                text = fix["text"]
            for wrong, right, reason in TEXT_FIXES:
                if wrong in text:
                    text = text.replace(wrong, right)
                    self.out.corrections.append(f"{raw['sheet']} {raw['target']}：{reason}")
            # rule 保留样表原文（悬停显示），解析用纠正后的文字
            fixed.append({**raw, "original": raw["text"], "text": text})
        # 列表（名称）规则先建，金额规则再按标签列找列表；sort 稳定，同类保持原顺序
        fixed.sort(key=lambda r: 0 if self._is_name_rule(self._clean(r["text"])) else 1)
        for raw in fixed:
            self._parse_one(raw)
        return self.out

    @staticmethod
    def _clean(text: str) -> str:
        text = text.strip().replace("“其中”明细行：", "")
        return re.sub(r"^(底稿取数余额表|试算表)-", "", text)

    @staticmethod
    def _is_name_rule(body: str) -> bool:
        return bool(re.search(r"(科目名称|末级科目|三级科目内容|填写三级科目内容)$", body))

    def _parse_one(self, raw: dict) -> None:
        body = self._clean(raw["text"])
        sheet, mark = raw["sheet"], raw["mark"]
        refs = expand_range(raw["target"])
        status = self._status(mark)

        # 公式：G列=E列+F列
        m = re.fullmatch(r"([A-Z])列=([A-Z])列\+([A-Z])列", body)
        if m:
            for ref in refs:
                r = _row(ref)
                self.out.formulas.append((sheet, ref, f"={m.group(2)}{r}+{m.group(3)}{r}"))
            return
        # 引用：3-2-1-01!D52
        m = re.fullmatch(r"([\d-]+)!([A-Z]+\d+)", body)
        if m:
            target_sheet = self.resolve_sheet(m.group(1))
            if not target_sheet:
                raise RuleParseError(f"{sheet} {raw['target']}：引用的表 {m.group(1)} 不存在")
            for ref in refs:
                self.out.formulas.append((sheet, ref, f"='{target_sheet}'!{m.group(2)}"))
            return

        # 按月 + 非货币性资产交换特征
        m = re.fullmatch(
            r"([^-，]+)-([^，]+)，提取上述明细科目在序时账中(不)?含有非货币性资产交换特征的记录，"
            r"按会计期间（1-12月）分组，计算各月(借|贷)方发生额，按1-12月顺序填入[A-Z]+\d+:[A-Z]+\d+。", body)
        if m:
            path = [m.group(1), m.group(2)]
            measure = self._side(path, m.group(4), raw)
            st = status if m.group(3) else "manual"
            self._months(raw, refs, st, path=path, measure=measure)
            return
        # 按月：对应科目(本列第6行)
        m = re.fullmatch(r"([^-]+)-对应科目\(本列第(\d+)行\)-本期(借|贷)方发生额（1-12月）", body)
        if m:
            path = [m.group(1)]
            measure = self._side(path, m.group(3), raw)
            label = f"{_col(refs[0])}{m.group(2)}"
            self._months(raw, refs, status, path=path, measure=measure, label=label)
            return
        # 单个明细科目（可带非货币性资产交换特征）
        m = re.fullmatch(
            r"([^-，]+)-([^，]+)，(?:(不)?含有非货币性资产交换特征，)?提取该明细科目(借|贷)方发生额，填入[A-Z]+\d+。?", body)
        if m:
            path = [m.group(1), m.group(2)]
            nonmonetary = "含有非货币性资产交换特征" in body
            st = "manual" if nonmonetary and not m.group(3) else status
            measure = self._side(path, m.group(4), raw)
            for ref in refs:
                self._item(raw, ref, st, "amount", path=path, measure=measure)
            return
        # 「其中」明细行：已列示科目外的其他科目
        m = re.fullmatch(r"([^-]+)-B列已列示科目外的其他科目-科目名称", body)
        if m:
            exclude = [t for t in self.column_texts(sheet, "B") if t]
            self._add_list(raw, refs, [m.group(1)], "children", exclude, status)
            return
        m = re.fullmatch(r"([^-]+)-对应科目（本行([A-Z])列科目）-本期(借|贷)方发生额", body)
        if m:
            path = [m.group(1)]
            self._list_amounts(raw, refs, m.group(2), path, self._side(path, m.group(3), raw), status)
            return
        # 明细科目名称 / 末级科目
        m = re.fullmatch(r"([^-]+)-明细科目-科目名称", body)
        if m:
            self._add_list(raw, refs, [m.group(1)], "children", [], status)
            return
        m = re.fullmatch(r"([^-]+)末级科目", body)
        if m:
            self._add_list(raw, refs, [m.group(1)], "leaves", [], status)
            return
        # 对应科目（本行 X 列）
        m = re.fullmatch(rf"([^-]+)-对应科目\(本行([A-Z])列\)-({_MEASURE_ALT})", body)
        if m:
            path = [m.group(1)]
            measure = MEASURES[m.group(3)]
            if measure == "credit":
                measure = self._side(path, "贷", raw)
            self._list_amounts(raw, refs, m.group(2), path, measure, status)
            return
        # 二级科目不能归类（其他）
        m = re.fullmatch(r"([^-]+?)二级科目不能归类与上述分类的归集于此，填写三级科目内容", body)
        if m:
            exclude = self._category_names(sheet, m.group(1))
            self._add_list(raw, refs, [m.group(1)], "others", exclude, status)
            return
        m = re.fullmatch(rf"([^-]+?)二级科目不能归类与上述分类的归集于此，取({_MEASURE_ALT})", body)
        if m:
            list_id = self._list_by_rows(sheet, [_row(r) for r in refs])
            if not list_id:
                raise RuleParseError(f"{sheet} {raw['target']}：找不到同行的名称列表")
            for i, ref in enumerate(refs):
                self._item(raw, ref, status, "list_amount", list=list_id, index=i,
                           path=[m.group(1)], measure=MEASURES[m.group(2)])
            return
        m = re.fullmatch(rf"([^-]+?)二级科目不能归类(.+?)的项目({_MEASURE_ALT})(?:合计)?", body)
        if m:
            exclude = [s.strip() for s in m.group(2).split("、") if s.strip()]
            for ref in refs:
                self._item(raw, ref, status, "others_sum", path=[m.group(1)], exclude=exclude, measure=MEASURES[m.group(3)])
            return
        # 三级科目内容（名称 / 金额）
        m = re.fullmatch(r"(.+)-三级科目内容", body)
        if m:
            self._add_list(raw, refs, _split_path(m.group(1)), "children", [], status)
            return
        m = re.fullmatch(rf"(.+)-三级科目内容的({_MEASURE_ALT})", body)
        if m:
            list_id = self._list_by_rows(sheet, [_row(r) for r in refs])
            if not list_id:
                raise RuleParseError(f"{sheet} {raw['target']}：找不到同行的三级科目名称列表")
            for i, ref in enumerate(refs):
                self._item(raw, ref, status, "list_amount", list=list_id, index=i,
                           path=_split_path(m.group(1)), measure=MEASURES[m.group(2)])
            return
        # 两级科目 + 口径
        m = re.fullmatch(rf"([^-]+)-([^-]+?)(?:-|的)({_MEASURE_ALT})", body)
        if m:
            path = _split_path(f"{m.group(1)}-{m.group(2)}")
            for ref in refs:
                self._item(raw, ref, status, "amount", path=path, measure=MEASURES[m.group(3)])
            return
        raise RuleParseError(f"{sheet} {raw['target']}：无法解析的取数规则「{raw['text']}」")

    def _months(self, raw: dict, refs: list[str], status: str, **spec) -> None:
        if len(refs) != 12:
            raise RuleParseError(f"{raw['sheet']} {raw['target']}：按月取数应为 12 格，实为 {len(refs)}")
        for month, ref in enumerate(refs, start=1):
            self._item(raw, ref, status, "month", month=month, **spec)

    def _list_amounts(self, raw: dict, refs: list[str], label_col: str, path: list[str], measure: str, status: str) -> None:
        sheet = raw["sheet"]
        for ref in refs:
            hit = self._list_for(sheet, label_col, _row(ref))
            if hit:
                self._item(raw, ref, status, "list_amount", list=hit[0], index=hit[1], path=path, measure=measure)
            else:
                label = self._label_ref(sheet, _row(ref), label_col, _col(ref))
                self._item(raw, ref, status, "amount", path=path, label=label, measure=measure)

    def _category_names(self, sheet: str, top: str) -> list[str]:
        """同表里已按二级分类列示的名称（「其他」要排除它们）。"""
        names: list[str] = []
        for spec in self.out.lists.values():
            if spec["sheet"] == sheet and len(spec["path"]) >= 2 and spec["path"][0] == top:
                if spec["path"][1] not in names:
                    names.append(spec["path"][1])
        return names
