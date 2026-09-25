# -*- coding: utf-8 -*-
"""审定表型受管 sheet 声明 —— 框架层单一数据类（AdjudicationSheetSpec）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 31（D1-1）
consumed by: e1-sync-coverage-and-first-canary（前置 B）· d2/d3/d567 lane specs
Requirements 5.1 / 6.1~6.5

═══ 为什么审定表不进行表引擎（design 裁决 D3）═══

实测三个循环的审定表形态**互不相同**：

| | 区块 | 行模型 | 行来源 | 存储 |
|---|---|---|---|---|
| D1-1 | 3（gross/bd/net） | 动态票据种类 | D1-2 / D1-4 cross-sheet | per-cell 锚点 |
| D2-1 | 1 | **写死 4 行**（信用风险分类） | D2-2 SUMIF | per-cell 锚点 |
| D4-1 | 2（主营/其他） | 动态行 | TB 派生 + 手工 | 行数组 + per-field 双写 |
| E1-1 | 槽位驱动（`E1_SLOT_ORDER`） | per-cell | 本 sheet 人工 / 跨 sheet 聚合 / **跨册** | per-cell 锚点 |

共性只有三件：逐格 mask（含小计/合计/差异行）、cross-sheet 派生 + 人工覆盖冲突、
期初/期末双期审定列。**差异大于共性** ⇒ 强行塞进 `RowTableSheetSpec` 会让它长出一堆
`if is_adjudication`。故行表引擎只管明细类，审定表用本模块的独立 spec 类表达；
共享的是**四态覆盖状态机**（前端 `shared/dynamicAdjudicationRows`）而不是后端投影引擎。

🔴 框架层纪律：本模块零 wp_code 分支（CI 卡点 `check_framework_layer_has_no_wp_code_branch`
   守）。各循环的几何/区块/槽位由 sheet 层实例化时传入。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

from app.services.workpaper_sync.sheet_geometry import col_index

__all__ = [
    "AdjudicationRowMode",
    "AdjudicationValueSource",
    "AdjudicationSection",
    "AdjudicationSheetSpec",
]


class AdjudicationRowMode(str, Enum):
    """审定表的行模型（三循环实测三形态）。

    * `dynamic_identity`（D1-1 / D4-1）：行由 store 的稳定身份驱动，可增删。
    * `fixed_rows`（D2-1）：行写死（如 4 条信用风险分类），不增删。
    * `slot_driven`（E1-1）：per-cell 槽位驱动（`E1_SLOT_ORDER` 常量给顺序），
      既非动态行也非固定行数组 —— 每个槽位是一个独立 store 键。
    """

    dynamic_identity = "dynamic_identity"
    fixed_rows = "fixed_rows"
    slot_driven = "slot_driven"


class AdjudicationValueSource(str, Enum):
    """一格审定值的来源（四态覆盖状态机的输入维度）。

    🔴 **派生格不可由 OO 侧直接写**（E1 spec 需求 4.5 / D1 spec 需求 6.3）：否则 OO 回写会
       覆盖跨 sheet 聚合结果，而聚合源一变又会盖回来 —— 静默丢数据。
    """

    manual = "manual"            # 本 sheet 人工录入
    cross_sheet = "cross_sheet"  # 跨 sheet 聚合（D1-1 ← D1-2/D1-4；E1-1 ← E1-3 分组小计）
    cross_volume = "cross_volume"  # 跨册（E1-1 的 E1-accrued-interest-rows 属第 3 册）
    tb_derived = "tb_derived"    # TB 派生（D4-1）
    computed = "computed"        # 现算不落库（审定/净值/合计列）


@dataclass(frozen=True)
class AdjudicationSection:
    """审定表的一个区块（D1-1 有 3 个 gross/bd/net；D4-1 有 2 个主营/其他；D2-1 有 1 个）。

    :param section_key: 区块标识（进 store 键与契约 table_key，如 `gross` / `main-revenue`）。
    :param table_key: 契约内的 table 键。
    :param title_row: 区块标题行（区块内第一行，非数据行）。
    :param first_data_row / last_data_row: 数据区行范围。
    :param subtotal_row: 小计行（computed，不落库）。
    :param uuid_col: 该区块的隐藏身份列。🔴 同 sheet 多区必须**各用不同列**，避免身份串区
        （D4-1 主营 W / 其他 X 的实测教训）。
    :param table_name: Excel Table displayName。
    :param template_id: `_GT_SYNC` 的 per-区块 template_id（同 sheet 多区各一个）。
    """

    section_key: str
    table_key: str
    title_row: int
    first_data_row: int
    last_data_row: int
    subtotal_row: int
    uuid_col: str = ""
    table_name: str = ""
    template_id: str = ""


@dataclass(frozen=True)
class AdjudicationSheetSpec:
    """一张审定表型受管 sheet 的声明（区块 + 行模型 + 逐格 mask + 值来源）。

    与 `RowTableSheetSpec` 的关键差异：
      * `sections`（1~N 个）取代单一数据区几何；
      * `row_mode` 表达三循环的行模型差异（不用 if 分支）；
      * `cell_mask`（逐格）取代 `formula_mask`（列向区间）—— 审定表的小计/合计/差异行
        与审定列都是公式格，且**不成列向区间**（D4-1 实测 48 格 / E1-1 实测 193 公式）；
      * `value_sources` 声明每个字段的值来源，供四态覆盖状态机与「派生格不可 OO 直写」纪律用。
    """

    # ── 身份与几何 ──────────────────────────────────────────────────────────
    managed_sheet: str
    sheet_key: str
    template_id: str
    header_rows: tuple[int, ...]
    sections: tuple[AdjudicationSection, ...]
    row_mode: AdjudicationRowMode

    # ── footer（合计 / TB 核对 / 差异 三行，各循环有无不同）──────────────────
    total_row: int | None = None
    tb_row: int | None = None
    diff_row: int | None = None
    footer_marker: str = "合计"

    # ── store ──────────────────────────────────────────────────────────────
    store_item_id: str = ""
    row_identity_key: str = "rowId"
    #: per-cell 锚点键的模板（D1-1 的 `D1-adj-{section}-{slug}-{field}`）。
    #: 双读单写迁移期：读侧行对象优先、缺则回落本模板（需求 6.2）。
    per_cell_key_template: str = ""

    # ── 字段与 mask ─────────────────────────────────────────────────────────
    #: (column_key, column, mode, value_type, json_key, header_text, group_header_cell)
    field_specs: tuple[tuple[str, str, str, str, str, str, str], ...] = ()
    #: 🔴 逐格 mask（`"B12"` 形态），**不是**列向区间。审定表的公式格分布在小计/合计/差异行
    #:    与审定列，不成区间；用列向区间会把受管金额字段整列误判只读（D4-1 踩过）。
    cell_mask: tuple[str, ...] = ()
    #: 字段 → 值来源。未声明的字段默认 `manual`。
    value_sources: Mapping[str, AdjudicationValueSource] = field(default_factory=dict)
    #: 槽位顺序（`slot_driven` 才有；取宿主的 `*_SLOT_ORDER` 常量，不另定义）。
    slot_order: tuple[str, ...] = ()
    #: HTML-only item 子集（受管 sheet ≠ 全部 item 受管）。
    html_only_item_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.sections and self.row_mode is not AdjudicationRowMode.slot_driven:
            raise ValueError(
                f"{self.managed_sheet}: 非 slot_driven 的审定表必须至少声明一个 section"
            )
        # 🔴 同 sheet 多区的 uuid_col 必须互不相同（D4-1 主营 W / 其他 X 的实测教训：
        #    同列会让两区的行身份串区，回写落到错的区块）。
        cols = [s.uuid_col for s in self.sections if s.uuid_col]
        if len(cols) != len(set(cols)):
            dupes = sorted({c for c in cols if cols.count(c) > 1})
            raise ValueError(
                f"{self.managed_sheet}: 同 sheet 多区的隐藏身份列重复 {dupes} —— "
                "两区共用同一 UUID 列会让行身份串区，回写落到错的区块"
            )
        # table_key 同理必须唯一
        keys = [s.table_key for s in self.sections]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{self.managed_sheet}: section 的 table_key 重复 {keys}")

    def section(self, section_key: str) -> AdjudicationSection | None:
        for s in self.sections:
            if s.section_key == section_key:
                return s
        return None

    def source_of(self, column_key: str) -> AdjudicationValueSource:
        """取一个字段的值来源（未声明默认 manual）。"""
        return self.value_sources.get(column_key, AdjudicationValueSource.manual)

    def is_oo_writable(self, column_key: str) -> bool:
        """OO 侧是否可直写该字段。

        🔴 派生格（cross_sheet / cross_volume / tb_derived / computed）**不可** OO 直写：
           否则 OO 回写会覆盖聚合结果，而聚合源一变又盖回来 —— 静默丢数据
           （D1 spec 需求 6.3 / E1 spec 需求 4.5 同一条纪律）。
        """
        return self.source_of(column_key) is AdjudicationValueSource.manual

    @property
    def masked_cells(self) -> frozenset[str]:
        """逐格 mask 的规范化集合（大写、去空白）。"""
        return frozenset(c.strip().upper() for c in self.cell_mask if c.strip())

    def is_cell_masked(self, column: str, row: int) -> bool:
        """某格是否在逐格 mask 内（格级判定，**不是**整列）。

        🔴 与 `merge._protection` 的格级判定（`_mask_spans_data_column`）同一口径：
           mask 覆盖小计/合计/差异行的 B–I，**不能**据此否决受管数据行同列的 editable 声明。
        """
        return f"{column.strip().upper()}{row}" in self.masked_cells

    @property
    def data_rows(self) -> tuple[int, ...]:
        """全部区块的数据行（升序，不含标题/小计/footer）。"""
        rows: list[int] = []
        for s in self.sections:
            rows.extend(range(s.first_data_row, s.last_data_row + 1))
        return tuple(sorted(rows))

    @property
    def computed_rows(self) -> tuple[int, ...]:
        """全部 computed 行（各区小计 + footer 三行）—— 它们不落 store。"""
        rows = [s.subtotal_row for s in self.sections]
        rows.extend(r for r in (self.total_row, self.tb_row, self.diff_row) if r)
        return tuple(sorted(set(rows)))

    def assert_data_cells_not_masked(self) -> None:
        """自检：受管数据行的 editable 字段**绝不**入 mask（D4-1 的 fail-closed 纪律）。

        🔴 这条自检存在的理由：mask 若覆盖受管数据格，merge 侧会把它判成只读 ⇒ 审计师在 OO 里
           改了却写不回，且**无任何提示**（四态 UI 重演「已实现但不可达」）。
        """
        bad: list[str] = []
        editable_cols = [
            spec[1] for spec in self.field_specs if spec[2] == "editable"
        ]
        for row in self.data_rows:
            for col in editable_cols:
                if self.is_cell_masked(col, row):
                    bad.append(f"{col}{row}")
        if bad:
            raise ValueError(
                f"{self.managed_sheet}: 受管数据格落进了 formula mask：{sorted(bad, key=lambda c: (col_index(''.join(ch for ch in c if ch.isalpha())), c))} "
                "—— 审计师在 OO 里改了会写不回且无提示（D4-1 踩过的 fail-closed 缺陷）"
            )
