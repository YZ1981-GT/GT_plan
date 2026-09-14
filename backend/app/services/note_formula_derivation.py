"""附注表内公式**机械派生**纯函数（Wave 1 / Task 2.1）.

Spec:   .kiro/specs/disclosure-note-formula-data-population/
Design: 决策 2（合计不写公式 binding）/ 决策 3（source='formula' + formula_kind）
        决策 4（人工优先）/ 决策 5（坐标以模板行序为准）
        §「Wave 0 核实结论」V2 / V4 / V5 / V7 / V8 / V14 / V15
Reqs:   1.1 / 1.3 / 1.4 / 2.1 / 2.3 / 2.5 / 5.1 / 5.2 / 8.1 / 8.2

职责
----
从「note_template 表（提供**行序** + headers）」与「note_template_bindings 表
（提供**列语义** + 既有 cell binding）」配对，机械派生两类公式：

1. **Sum_Formula（合计/小计）** —— 仅登记为预设（可见/可核对），**不写 binding**
   （决策 2 硬约束：生成路径第二遍求值不跳过合计行，写了就与 `_backfill_totals`
   双写）。求和范围严格对齐 `_backfill_totals`：上一合计行之后 → 本合计行之前的
   **所有非合计行**（§V8）。
2. **Movement_Identity（变动表恒等式）** —— data 行
   `期末余额 = 期初余额 + 本期增加 − 本期减少`，写 binding + 登记预设。

宁缺勿造
--------
- 列语义四件套不全 → 该表不产出 movement（分列变体按 `_colN` 分组，跨组不混算）
- 目标格已有有效绑定（trial_balance / prior_year_note / 人工标注） → 不覆盖
- 同表重复行标签 → 跳过（`_resolve_cell_binding` 按 label 精确匹配只命中第一个，§V7）
- 比例类 / 文本类语义列 → 不登记求和（避免误导性预设）
- 任何不可判定情形一律进 `skipped` 并带 reason，不猜

纯函数：不做 IO、不读 DB、同输入同输出（供 PBT）。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 语义常量（与 note_template_bindings.json 的 valid_semantics 同名）
# ---------------------------------------------------------------------------

SEM_OPENING = "opening_balance"
SEM_INCREASE = "current_year_increase"
SEM_DECREASE = "current_year_decrease"
SEM_CLOSING = "closing_balance"

#: 变动表恒等式所需的四件套基础语义
MOVEMENT_QUAD: frozenset[str] = frozenset(
    {SEM_OPENING, SEM_INCREASE, SEM_DECREASE, SEM_CLOSING}
)

#: 不参与"合计=分项之和"登记的语义（比例/文本 —— 求和无会计意义）
NON_SUMMABLE_SEMANTICS: frozenset[str] = frozenset({"provision_ratio", "manual_text"})

#: 合计/小计 row_type
TOTAL_ROW_TYPES: frozenset[str] = frozenset({"total", "subtotal"})

#: 分列变体后缀，如 ``closing_balance_col2``
_COL_SUFFIX_RE = re.compile(r"^(?P<base>.+?)(?P<suffix>_col\d+)$")


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FormulaSpec:
    """单个派生公式规格（目标格 + 带符号引用项）。"""

    section_number: str
    variant: str
    table_index: int
    table_name: str
    row_index: int  # 0-based，模板 rows 列表序（含 header_label 与合计行）
    row_label: str
    col_index: int  # 0-based 数值列序（不含 label 列）
    semantic: str | None
    target_cell: str  # 'R{r}C{c}'（1-based）
    signed_cells: tuple[tuple[str, str], ...]  # ((cell, '+'|'-'), ...)
    derived_by: str
    derived_note: str = ""

    def expression(self) -> str:
        """机器可读表达式：``ROW('R2C1') + ROW('R2C2') - ROW('R2C3')``。"""
        parts: list[str] = []
        for i, (cell, sign) in enumerate(self.signed_cells):
            ref = f"ROW('{cell}')"
            if i == 0:
                parts.append(ref if sign == "+" else f"-{ref}")
            else:
                parts.append(f"{sign} {ref}")
        return " ".join(parts)

    def cells_payload(self) -> list[dict[str, str]]:
        """写入 binding 的带符号项载荷。"""
        return [{"cell": cell, "sign": sign} for cell, sign in self.signed_cells]


@dataclass(frozen=True)
class SkippedItem:
    """跳过项（进覆盖率报告，可解释）。

    ``is_candidate=True`` 表示被跳过的对象**本身是候选单元格**（data 行 + 有语义
    + 当前 manual+todo），用于 Property 16 的三分类统计；表级/列级跳过为 False。
    """

    section_number: str
    variant: str
    table_index: int
    row_index: int | None
    row_label: str
    col_index: int | None
    reason: str
    is_candidate: bool = False


@dataclass
class DerivationResult:
    """单章节派生结果。"""

    section_number: str
    variant: str
    sum_specs: list[FormulaSpec] = field(default_factory=list)
    movement_specs: list[FormulaSpec] = field(default_factory=list)
    skipped: list[SkippedItem] = field(default_factory=list)
    #: 候选单元格总数（data 行 × 有语义列 × 当前 manual+todo；独立统计，Property 16 分母）
    candidate_cells: int = 0

    def extend(self, other: DerivationResult) -> None:
        self.sum_specs.extend(other.sum_specs)
        self.movement_specs.extend(other.movement_specs)
        self.skipped.extend(other.skipped)
        self.candidate_cells += other.candidate_cells

    @property
    def skipped_candidate_count(self) -> int:
        """被跳过的候选单元格数（Property 16 三分类之二）。"""
        return sum(1 for s in self.skipped if s.is_candidate)

    @property
    def remaining_manual_todo(self) -> int:
        """仍保持 manual+todo 的候选单元格数（Property 16 三分类之三）。"""
        return (
            self.candidate_cells
            - len(self.movement_specs)
            - self.skipped_candidate_count
        )


# ---------------------------------------------------------------------------
# 坐标 / 语义工具
# ---------------------------------------------------------------------------


def cell_coord(row_index_0based: int, value_col_index_0based: int) -> str:
    """→ ``'R{r+1}C{c+1}'``.

    ``R`` = note_template ``tables[].rows`` 列表序（**含 header_label 行与合计行**，
    与运行时 ``_build_with_binding`` 输出 rows 同序，§V4/V5）；
    ``C`` = 数值列 1-based 序号（**不含** label 列）。
    """
    if row_index_0based < 0 or value_col_index_0based < 0:
        raise ValueError("cell_coord 索引必须非负")
    return f"R{row_index_0based + 1}C{value_col_index_0based + 1}"


def value_col_semantics(table_binding: Any) -> list[str | None]:
    """从 binding ``header_normalize`` 取**数值列**语义（丢弃 index 0 的 label 列）.

    列语义真源在 bindings，不在 note_template（§V2）。结构异常 → 空列表。
    """
    if not isinstance(table_binding, dict):
        return []
    hn = table_binding.get("header_normalize")
    if not isinstance(hn, list) or len(hn) <= 1:
        return []
    out: list[str | None] = []
    for item in hn[1:]:
        if isinstance(item, dict):
            sem = item.get("semantic")
            out.append(sem if isinstance(sem, str) and sem else None)
        else:
            out.append(None)
    return out


def split_semantic(semantic: str) -> tuple[str, str]:
    """拆分语义为 ``(base, suffix)``；``closing_balance_col2`` → ``('closing_balance','_col2')``."""
    m = _COL_SUFFIX_RE.match(semantic)
    if m:
        return m.group("base"), m.group("suffix")
    return semantic, ""


def is_total_row(row: Any) -> bool:
    """合计/小计行判定（与 ``_build_with_binding`` 同口径）."""
    if not isinstance(row, dict):
        return False
    if row.get("is_total"):
        return True
    return row.get("row_type") in TOTAL_ROW_TYPES


def _template_rows(table_template: Any) -> list[dict[str, Any]]:
    if not isinstance(table_template, dict):
        return []
    rows = table_template.get("rows")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _num_value_cols(table_template: Any) -> int:
    if not isinstance(table_template, dict):
        return 0
    headers = table_template.get("headers")
    if not isinstance(headers, list):
        return 0
    return max(0, len(headers) - 1)


def _binding_rows(table_binding: Any) -> dict[str, Any]:
    if not isinstance(table_binding, dict):
        return {}
    rows = table_binding.get("rows")
    return rows if isinstance(rows, dict) else {}


def _cell_binding(binding_rows: dict[str, Any], label: str, semantic: str) -> Any:
    """按 label + semantic 取既有 cell binding（与 ``_resolve_cell_binding`` 同口径）."""
    row = binding_rows.get(label)
    if not isinstance(row, dict):
        return None
    cells = row.get("binding")
    if not isinstance(cells, dict):
        return None
    cell = cells.get(semantic)
    if isinstance(cell, dict):
        return cell
    prefix = semantic + "_col"
    for k, v in cells.items():
        if isinstance(k, str) and k.startswith(prefix) and isinstance(v, dict):
            return v
    return None


def is_manual_todo(cell_binding: Any) -> bool:
    """候选判定：当前为 ``manual`` + 带 ``todo`` 的 placeholder（决策 4 人工优先）."""
    if not isinstance(cell_binding, dict):
        return False
    return cell_binding.get("source") == "manual" and bool(cell_binding.get("todo"))


def _duplicate_labels(rows: list[dict[str, Any]]) -> set[str]:
    counter = Counter((r.get("label") or "") for r in rows)
    return {label for label, n in counter.items() if n > 1}


def count_candidate_cells(table_template: Any, table_binding: Any) -> int:
    """候选单元格数：data 行 × 有语义列 × 当前 ``manual`` + ``todo`` 的格.

    独立统计（不依赖派生结果），作为 Property 16 的分母。
    """
    rows = _template_rows(table_template)
    n_cols = _num_value_cols(table_template)
    sems = value_col_semantics(table_binding)
    binding_rows = _binding_rows(table_binding)
    if not rows or n_cols <= 0 or not sems:
        return 0

    total = 0
    for row in rows:
        if is_total_row(row) or row.get("row_type") != "data":
            continue
        label = row.get("label") or ""
        for c in range(min(n_cols, len(sems))):
            sem = sems[c]
            if not sem:
                continue
            if is_manual_todo(_cell_binding(binding_rows, label, sem)):
                total += 1
    return total


# ---------------------------------------------------------------------------
# 1) 合计 / 小计求和（只登记预设，不写 binding —— 决策 2）
# ---------------------------------------------------------------------------


def derive_sum_formula(
    table_template: Any,
    table_binding: Any,
    *,
    section_number: str = "",
    variant: str = "",
    table_index: int = 0,
) -> tuple[list[FormulaSpec], list[SkippedItem]]:
    """合计/小计行 → 同列求和规格（范围严格对齐 ``_backfill_totals``，§V8）.

    求和范围 = 上一合计行之后 → 本合计行之前的**所有非合计行**（含 header_label
    行 —— 它们 values 恒 None，求值期被 fail-open 跳过，与 backfill 等价）。
    """
    rows = _template_rows(table_template)
    n_cols = _num_value_cols(table_template)
    table_name = (
        table_template.get("name") if isinstance(table_template, dict) else ""
    ) or ""
    sems = value_col_semantics(table_binding)

    specs: list[FormulaSpec] = []
    skipped: list[SkippedItem] = []
    if not rows or n_cols <= 0:
        return specs, skipped

    for i, row in enumerate(rows):
        if not is_total_row(row):
            continue
        label = row.get("label") or ""
        if i == 0:
            skipped.append(
                SkippedItem(
                    section_number, variant, table_index, i, label, None,
                    "total_at_first_row",
                )
            )
            continue

        start = 0
        for j in range(i - 1, -1, -1):
            if is_total_row(rows[j]):
                start = j + 1
                break
        members = [j for j in range(start, i) if not is_total_row(rows[j])]
        if not members:
            skipped.append(
                SkippedItem(
                    section_number, variant, table_index, i, label, None,
                    "empty_sum_range",
                )
            )
            continue

        for c in range(n_cols):
            sem = sems[c] if c < len(sems) else None
            base, _suffix = split_semantic(sem) if sem else (None, "")
            if base in NON_SUMMABLE_SEMANTICS:
                skipped.append(
                    SkippedItem(
                        section_number, variant, table_index, i, label, c,
                        "non_summable_semantic",
                    )
                )
                continue
            specs.append(
                FormulaSpec(
                    section_number=section_number,
                    variant=variant,
                    table_index=table_index,
                    table_name=table_name,
                    row_index=i,
                    row_label=label,
                    col_index=c,
                    semantic=sem,
                    target_cell=cell_coord(i, c),
                    signed_cells=tuple(
                        (cell_coord(j, c), "+") for j in members
                    ),
                    derived_by="sum_total",
                    derived_note=(
                        "合计 = 上一合计行之后至本行之前的非合计行之和"
                        "（与 _backfill_totals 同口径）"
                    ),
                )
            )

    return specs, skipped


# ---------------------------------------------------------------------------
# 2) 变动表恒等式（写 binding + 登记预设）
# ---------------------------------------------------------------------------


def derive_movement_identity(
    table_template: Any,
    table_binding: Any,
    *,
    section_number: str = "",
    variant: str = "",
    table_index: int = 0,
) -> tuple[list[FormulaSpec], list[SkippedItem], int]:
    """列语义四件套齐全 → data 行 ``期末 = 期初 + 增 − 减``（带符号项）.

    Returns:
        ``(specs, skipped, candidate_cells)``；``candidate_cells`` 由
        ``count_candidate_cells`` 独立统计（Property 16 分母，不依赖 specs）。
    """
    rows = _template_rows(table_template)
    n_cols = _num_value_cols(table_template)
    table_name = (
        table_template.get("name") if isinstance(table_template, dict) else ""
    ) or ""
    sems = value_col_semantics(table_binding)
    binding_rows = _binding_rows(table_binding)

    specs: list[FormulaSpec] = []
    skipped: list[SkippedItem] = []
    candidates = count_candidate_cells(table_template, table_binding)
    if not rows or n_cols <= 0 or not sems:
        return specs, skipped, candidates

    # 按分列后缀分组收集四件套列位置
    groups: dict[str, dict[str, int]] = {}
    for c, sem in enumerate(sems):
        if c >= n_cols or not sem:
            continue
        base, suffix = split_semantic(sem)
        if base in MOVEMENT_QUAD:
            groups.setdefault(suffix, {})[base] = c

    full_groups = {
        suffix: cols for suffix, cols in groups.items()
        if MOVEMENT_QUAD <= set(cols)
    }
    if not full_groups:
        # 四件套不全 → 该表不产出（宁缺勿造，Property 5）
        if groups:
            skipped.append(
                SkippedItem(
                    section_number, variant, table_index, None, "", None,
                    "movement_quad_incomplete",
                )
            )
        return specs, skipped, candidates

    dup_labels = _duplicate_labels(rows)

    for suffix, cols in sorted(full_groups.items()):
        c_open = cols[SEM_OPENING]
        c_inc = cols[SEM_INCREASE]
        c_dec = cols[SEM_DECREASE]
        c_close = cols[SEM_CLOSING]
        closing_sem = sems[c_close] or SEM_CLOSING

        for i, row in enumerate(rows):
            label = row.get("label") or ""
            if is_total_row(row):
                continue  # 合计由 _backfill_totals 处理（决策 2）
            if row.get("row_type") != "data":
                continue  # header_label 等非数据行不绑定
            existing = _cell_binding(binding_rows, label, closing_sem)
            target_is_candidate = is_manual_todo(existing)

            if label in dup_labels:
                # 重复 label：binding 定位不可靠（§V7）→ 跳过；若该格本是候选，计入
                # 候选跳过（Property 16 三分类）
                skipped.append(
                    SkippedItem(
                        section_number, variant, table_index, i, label, c_close,
                        "duplicate_label", target_is_candidate,
                    )
                )
                continue

            if not target_is_candidate:
                skipped.append(
                    SkippedItem(
                        section_number, variant, table_index, i, label, c_close,
                        "target_not_manual_todo"
                        if existing is not None
                        else "target_binding_missing",
                        False,
                    )
                )
                continue

            specs.append(
                FormulaSpec(
                    section_number=section_number,
                    variant=variant,
                    table_index=table_index,
                    table_name=table_name,
                    row_index=i,
                    row_label=label,
                    col_index=c_close,
                    semantic=closing_sem,
                    target_cell=cell_coord(i, c_close),
                    signed_cells=(
                        (cell_coord(i, c_open), "+"),
                        (cell_coord(i, c_inc), "+"),
                        (cell_coord(i, c_dec), "-"),
                    ),
                    derived_by="movement_identity",
                    derived_note=(
                        "期末余额 = 期初余额 + 本期增加 − 本期减少"
                        "（由列语义四件套机械派生）"
                    ),
                )
            )

    return specs, skipped, candidates


# ---------------------------------------------------------------------------
# 3) 单章节汇总
# ---------------------------------------------------------------------------


def derive_note_formulas(
    section_number: str,
    template_section: Any,
    binding_section: Any,
    variant: str,
) -> DerivationResult:
    """单章节派生：模板提供行序/headers，binding 提供列语义/既有绑定（§V2/V3）."""
    result = DerivationResult(section_number=section_number, variant=variant)

    t_tables = (
        template_section.get("tables") if isinstance(template_section, dict) else None
    )
    b_tables = (
        binding_section.get("tables") if isinstance(binding_section, dict) else None
    )
    if not isinstance(t_tables, list) or not isinstance(b_tables, list):
        result.skipped.append(
            SkippedItem(section_number, variant, -1, None, "", None, "tables_missing")
        )
        return result
    if len(t_tables) != len(b_tables):
        result.skipped.append(
            SkippedItem(
                section_number, variant, -1, None, "", None, "table_count_mismatch"
            )
        )
        return result

    for ti, (tt, tb) in enumerate(zip(t_tables, b_tables)):
        if not isinstance(tt, dict) or not isinstance(tb, dict):
            result.skipped.append(
                SkippedItem(
                    section_number, variant, ti, None, "", None, "table_not_dict"
                )
            )
            continue
        if not _template_rows(tt):
            result.skipped.append(
                SkippedItem(section_number, variant, ti, None, "", None, "rows_empty")
            )
            continue

        s_specs, s_skipped = derive_sum_formula(
            tt, tb, section_number=section_number, variant=variant, table_index=ti
        )
        m_specs, m_skipped, cands = derive_movement_identity(
            tt, tb, section_number=section_number, variant=variant, table_index=ti
        )
        result.sum_specs.extend(s_specs)
        result.movement_specs.extend(m_specs)
        result.skipped.extend(s_skipped)
        result.skipped.extend(m_skipped)
        result.candidate_cells += cands

    return result


__all__ = [
    "MOVEMENT_QUAD",
    "NON_SUMMABLE_SEMANTICS",
    "TOTAL_ROW_TYPES",
    "DerivationResult",
    "FormulaSpec",
    "SkippedItem",
    "cell_coord",
    "derive_movement_identity",
    "derive_note_formulas",
    "derive_sum_formula",
    "is_manual_todo",
    "is_total_row",
    "split_semantic",
    "value_col_semantics",
]
