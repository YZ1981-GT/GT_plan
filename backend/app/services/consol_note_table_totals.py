"""合并附注表格行组装与合计重算 —— 明细映射拉数与节点子树汇总共用。

spec: consol-note-header-library-and-node-reaggregate（Task 9，从 ``consol_note_detail_apply_service`` 抽出）

骨架行（行名, 行类型）+ 每行逐列金额 → 写入用的二维行：
- 数据行写金额（两位小数，ROUND_HALF_UP）；
- 合计 / 小计按合计构成（``note_total_terms``，与单体附注 / 前端同一判定）用本表已组装的行重算：小计 = 本组
  明细、合计 = 各小计 ± 减项 / 加项、「其中：」明细不重复加；整列都没有数据保持空白；判不准的合计行（「其中：X」
  行内写法、嵌套小计…）写来源同一行之和（汇总按线性相加），没有来源金额留空；
- 手工 / 锁定单元格保留原值并回报；已保存行按行名对到新行（``row_correspondence``），模板插删行、不写「……」占位行
  （``build_note_rows`` 的 ``placeholders``，spec note-pull-followup-closure R15）后不错位。

变动表逐行勾稽（期初 + Σ增加 − Σ减少 = 期末，``rollforward_balance``）：「审核」与勾稽规则列平衡共用同一个函数（R7.5）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable, Sequence

__all__ = [
    "TOTAL_ROW_TYPES", "BuiltRows", "build_note_rows", "build_table_rows", "existing_cell", "fmt_amount",
    "remap_cells", "rollforward_balance", "row_correspondence", "to_decimal",
]

TOTAL_ROW_TYPES = ("total", "subtotal")
#: 空格与占位符（「—」「-」）：没有金额
_BLANK_CELLS = ("", "-", "—", "－")


def to_decimal(value: Any) -> Decimal | None:
    """单元格 → Decimal；空、占位符、非数值 → None（不参与加总）。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float) and value != value:  # NaN
        return None
    if isinstance(value, dict):  # 带元数据的单元格
        return to_decimal(value.get("value", value.get("manual_value")))
    s = str(value).strip().replace(",", "").replace("，", "")
    if s in _BLANK_CELLS:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def rollforward_balance(flow: Any, row: Sequence[Any]) -> tuple[Decimal, Decimal] | None:
    """变动表一行：(期初 + Σ增加 − Σ减少, 期末)；这一行没法勾稽 ⇒ None。「审核」的勾稽校验与勾稽规则列平衡共用。

    ``flow`` 是标题行库 ``rollforward_columns`` 按表头认出的列（期初 / 期末 / 增加 / 减少 / 方向不定）。没法勾稽：期初或期末格
    有字但不是金额；期初、期末都是零；方向不定的变动列有数；增加、减少合计都是零（只填了余额）。空格、越界、占位符按零。
    """
    def amount(ci: int) -> Decimal | None:
        raw = row[ci] if 0 <= ci < len(row) else None
        if raw is None or (not isinstance(raw, dict) and str(raw).strip() in _BLANK_CELLS):
            return Decimal(0)
        return to_decimal(raw)

    opening, closing = amount(flow.opening), amount(flow.closing)
    if opening is None or closing is None or not (opening or closing):
        return None
    if any(amount(ci) for ci in flow.unknown):
        return None
    increase = sum((amount(ci) or Decimal(0) for ci in flow.increase), Decimal(0))
    decrease = sum((amount(ci) or Decimal(0) for ci in flow.decrease), Decimal(0))
    if not (increase or decrease):
        return None
    return opening + increase - decrease, closing


def fmt_amount(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def existing_cell(rows: Sequence[Any], row_idx: int, col_idx: int) -> str:
    """从已保存行中安全取值（二维行或 ``{values|cells: {列号: 值}}`` 对象行）。"""
    if row_idx >= len(rows):
        return ""
    row = rows[row_idx]
    if isinstance(row, (list, tuple)):
        return str(row[col_idx]) if col_idx < len(row) else ""
    if isinstance(row, dict):
        vals = row.get("values") or row.get("cells") or {}
        if isinstance(vals, dict):
            return str(vals.get(str(col_idx), vals.get(col_idx, "")))
    return ""


def _row_label(row: Any) -> str:
    if isinstance(row, (list, tuple)):
        return str(row[0] or "") if row else ""
    if isinstance(row, dict):
        return str(row.get("label") or "")
    return ""


def row_correspondence(names: Sequence[str], existing_rows: Sequence[Any]) -> dict[int, int]:
    """新行号 → 已保存行号。

    按（行名比较键, 同名序号）对（与节点子树汇总对下级行同一口径）；名字对不上的新行，若同号的已保存行也没被别的新行
    认领，按位置对（行名被改过、前后没有插删行时与旧行为一致）。对不上的新行没有对应（不读已保存值、不带手工保护）。
    """
    from app.services.consol_elimination_sheet_service import row_name_key

    def keyed(labels: Sequence[str]) -> list[tuple[str, int]]:
        seen: dict[str, int] = {}
        out = []
        for label in labels:
            key = row_name_key(label)
            out.append((key, seen.get(key, 0)))
            seen[key] = seen.get(key, 0) + 1
        return out

    old_keys = keyed([_row_label(r) for r in existing_rows])
    old_by_key = {k: j for j, k in enumerate(old_keys)}
    mapping: dict[int, int] = {}
    for i, key in enumerate(keyed(list(names))):
        if key in old_by_key:
            mapping[i] = old_by_key[key]
    claimed = set(mapping.values())
    for i in range(len(names)):
        if i not in mapping and i < len(existing_rows) and i not in claimed:
            mapping[i] = i
            claimed.add(i)
    return mapping


@dataclass
class BuiltRows:
    """``build_note_rows`` 的结果。行号都是新行号（``rows`` 的下标）。"""

    rows: list[list[str]]
    filled: list[dict[str, Any]]
    kept: list[dict[str, Any]]
    #: 已保存行号 → 新行号（手工 / 锁定坐标按它改写，``remap_cells``）
    old_to_new: dict[int, int] = field(default_factory=dict)
    #: 骨架行号 → 新行号（不写的占位行没有）
    kept_index: dict[int, int] = field(default_factory=dict)
    #: 不写的「……」占位行行名（spec note-pull-followup-closure R15）
    dropped_placeholders: list[str] = field(default_factory=list)


def remap_cells(cells: Iterable[tuple[int, int]], old_to_new: dict[int, int]) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """已保存坐标 → 新坐标；所在行在新表里没有对应的坐标单独返回（调用方回报，不静默落到别的行上）。"""
    moved: list[tuple[int, int]] = []
    lost: list[tuple[int, int]] = []
    for r, c in sorted(set(cells)):
        if r in old_to_new:
            moved.append((old_to_new[r], c))
        else:
            lost.append((r, c))
    return moved, lost


def build_note_rows(
    skeleton: Sequence[tuple[str, str | None]],
    amounts: dict[int, dict[int, Decimal]],
    *,
    width: int,
    protected: set[tuple[int, int]],
    existing_rows: Sequence[Any],
    placeholders: Iterable[int] = (),
) -> BuiltRows:
    """骨架 + 金额 → 写入用的行。

    - ``skeleton[i]`` = (行名, 行类型)；``amounts[i][col]`` = 第 i 行第 col 列金额（col ≥ 1）。判得准的合计 / 小计行不写来源
      金额，按合计构成用本表已组装的行重算（先小计、后合计）；判不准的合计行与数据行一样写来源金额。
    - ``placeholders``：骨架里的「……」可扩位占位行（模板的意思是「此处按实际列示」）。没有映射来的金额、也没有手填值的
      不写（修复前建的明细模板把它标成固定行，拉数 / 重新汇总原样写出一行「……」）。
    - ``protected`` / ``existing_rows`` 的行号是已保存数据的行号：按行名对到新行（``row_correspondence``），占位行不写、模板
      插删行后手工 / 锁定格不错位。
    """
    from app.services.note_total_terms import sum_terms, total_order, total_terms

    names = [name for name, _rt in skeleton]
    corr = row_correspondence(names, existing_rows)
    protected_rows = {r for r, _c in protected}

    def has_manual_value(i: int) -> bool:
        old = corr.get(i)
        return old is not None and old in protected_rows and any(
            (old, c) in protected and existing_cell(existing_rows, old, c).strip() for c in range(1, width))

    drop = {i for i in placeholders if 0 <= i < len(skeleton) and not amounts.get(i) and not has_manual_value(i)}
    keep = [i for i in range(len(skeleton)) if i not in drop]
    kept_skeleton = [skeleton[i] for i in keep]
    new_amounts = {n: amounts[i] for n, i in enumerate(keep) if i in amounts}
    old_of = {n: corr[i] for n, i in enumerate(keep) if i in corr}
    old_to_new = {old: n for n, old in old_of.items()}
    guard = {(old_to_new[r], c) for r, c in protected if r in old_to_new}

    def saved(n: int, col: int) -> str:
        old = old_of.get(n)
        return existing_cell(existing_rows, old, col) if old is not None else ""

    shaped = [{"label": name, "row_type": row_type or "data"} for name, row_type in kept_skeleton]
    plans, _reasons = total_terms(shaped)
    new_rows: list[list[str]] = []
    filled: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for i, (name, _row_type) in enumerate(kept_skeleton):
        row = [""] * width
        if width:
            row[0] = name
        if i not in plans:
            row_amounts = new_amounts.get(i) or {}
            for col in range(1, width):
                if (i, col) in guard:
                    # 手工 / 锁定格一律保留（来源这一格没数也不清空）；来源有数时回报「保留了手工值」
                    old = saved(i, col)
                    row[col] = old
                    if col in row_amounts:
                        kept.append({"row": i, "col": col, "kept_value": old})
                elif col in row_amounts:
                    formatted = fmt_amount(row_amounts[col])
                    row[col] = formatted
                    filled.append({"row": i, "col": col, "value": formatted, "target_name": name})
        new_rows.append(row)
    for i in total_order(shaped, plans):
        row = new_rows[i]
        for col in range(1, width):
            if (i, col) in guard:
                row[col] = saved(i, col)
                continue
            total = sum_terms(plans[i], lambda r, col=col: to_decimal(new_rows[r][col]))
            if total is not None:
                row[col] = fmt_amount(total)
    return BuiltRows(new_rows, filled, kept, old_to_new, {i: n for n, i in enumerate(keep)},
                     [skeleton[i][0] for i in sorted(drop)])


def build_table_rows(
    skeleton: Sequence[tuple[str, str | None]],
    amounts: dict[int, dict[int, Decimal]],
    *,
    width: int,
    protected: set[tuple[int, int]],
    existing_rows: Sequence[Any],
) -> tuple[list[list[str]], list[dict[str, Any]], list[dict[str, Any]]]:
    """返回 (新行, 写入的单元格, 保留的手工 / 锁定单元格)；不去占位行的 ``build_note_rows``。"""
    built = build_note_rows(skeleton, amounts, width=width, protected=protected, existing_rows=existing_rows)
    return built.rows, built.filled, built.kept
