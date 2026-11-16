# -*- coding: utf-8 -*-
"""D1-1「应收票据审定表」—— `AdjudicationSheetSpec` 实例声明。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 31 · Requirements 5.1

═══ 几何（openpyxl 直读实测，2026-09-26）═══

三区（原值 R7-R10 / 坏账准备 R11-R14 / 净值 R15-R18）+ footer（合计 R18 / 试算平衡表数 R19 /
差异 R20）。两级表头 R5-R6（项目/期初/期末/变动/原因分析）。15 列 A-O。

绝大多数格是**跨 sheet 公式**（引用 D1-2/D1-4），真正可编辑的很少：
- D12/D13 重分类调整（坏账区，手工录入）
- H12/H13 期末重分类调整（坏账区，手工录入）
- E19（试算平衡表数，手工录入对照 TB）
- I19（试算平衡表数，同上期末）
- R24+ 审计说明/结论文字区（HTML-only，不映射 Excel 格）

🔴 净值三区（R15-R18）全部是**公式**（原值−坏账），零可编辑格 ⇒ 不需要 section，只需
   cell_mask 覆盖。

🔴 `row_mode = fixed_rows`：银行承兑/商业承兑是固定行（不增删），前端 `useD1Adjudication.ts`
   的行由模板固定。

🔴 前端 store 键是 per-cell 锚点模式 `D1-adj-{section}-{slug}-{field}`。

🔴 本声明只交付**几何 + 逐格 mask**（Task 31 范围）。存量迁移（Task 32）和四态状态机
   接入（Task 33）是后续依赖任务。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_adjudication_sheet import (
    AdjudicationRowMode,
    AdjudicationSection,
    AdjudicationSheetSpec,
    AdjudicationValueSource,
)

__all__ = [
    "SPEC_D101",
    "MANAGED_SHEET_D101",
    "SHEET_KEY_D101",
    "GT_MANAGED_REGION_D11",
    "static_sheet_payload_d11",
]

MANAGED_SHEET_D101: Final[str] = "审定表D1-1"
TEMPLATE_ID_D101: Final[str] = "D11"
SHEET_KEY_D101: Final[str] = f"{TEMPLATE_ID_D101.lower()}-managed"

#: 静态受管区的 workbook-scope defined name（照 D2-1 / D4-8 / D4-13 / D1-4 范式）。
#: instrumentation 注入只写这一个 definedName（`region_kind=static`），不注入 Excel Table /
#: UUID 列 / 隐藏 identity_row —— D1-1 是三区 `fixed_rows` 审定表，没有任何动态行载体。
GT_MANAGED_REGION_D11: Final[str] = f"GT_MANAGED_REGION_{TEMPLATE_ID_D101}"

#: D1-1 的受管矩形（A5:O20）：表头 R5-R6 + 三区数据/小计 R7-R18 + footer R19-R20。
#: 🔴 起点取**表头行**而非数据行：`_sheet_extent` 只校验「字段坐标不超出物理外延」，
#:    但表头行在矩形内能让 definedName 锚点覆盖整块受管面（含 footer 的 TB 数格 E19/I19，
#:    它们是 `manual` 可编辑格）。
_STATIC_REGION_RANGE_D11: Final[str] = "$A$5:$O$20"

#: per-cell 锚点键的前缀（前端 `D1_ADJ_PREFIX = 'D1-adj-'`）。
D1_ADJ_PREFIX: Final[str] = "D1-adj-"

#: ─── 三个 section（原值/坏账/净值）───────────────────────────────────────
#: 🔴 净值区（R15-R18）全格公式（原值−坏账），不设独立 section 的 uuid_col——它没有独立
#:    store 行身份，只是两区的差。
SECTION_GROSS: Final[AdjudicationSection] = AdjudicationSection(
    section_key="gross",
    table_key="adj_gross_rows",
    title_row=7,
    first_data_row=8,
    last_data_row=9,
    subtotal_row=10,
    uuid_col="",  # 固定行不需 UUID
    table_name="",
    template_id=f"{TEMPLATE_ID_D101}GROSS",
)

SECTION_BAD_DEBT: Final[AdjudicationSection] = AdjudicationSection(
    section_key="bd",
    table_key="adj_bad_debt_rows",
    title_row=11,
    first_data_row=12,
    last_data_row=13,
    subtotal_row=14,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_D101}BD",
)

SECTION_NET: Final[AdjudicationSection] = AdjudicationSection(
    section_key="net",
    table_key="adj_net_rows",
    title_row=15,
    first_data_row=16,
    last_data_row=17,
    subtotal_row=18,
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_D101}NET",
)

#: ─── 受管字段（审定表列 A-K + L 原因分析）────────────────────────────────
#: 🔴 D1-1 的 B-I 绝大多数数据格是**跨 sheet 公式**（引用 D1-2/D1-4）或**计算公式**
#:    （E=B+C+D / I=F+G+H / J=I-E / K=IF）。真正可编辑的数据格**极少**：
#:    只有 D12/D13（坏账区期初重分类）、H12/H13（坏账区期末重分类）、L 列（原因分析）。
#:    field_specs 的 mode 声明的是**列级默认**：B/C/D/E/F/G/H/I/J/K 全部声明为 formula
#:    （它们在每个数据行都是公式），只有 A（项目名）和 L（原因分析）是 editable。
#:    D12/D13/H12/H13 四格是少数例外——它们**不进 cell_mask**（不被保护），从而在逐格判定时
#:    被视为可写（cell_mask 覆盖 = 保护；不覆盖 = 列级默认模式，formula 列但该格未 mask
#:    ⇒ materialize 仍不写该格，extract 读出公式值不覆盖 store 值——这是正确行为，
#:    因为 D12/D13 的值来源是手工录入，不经 extract 回写）。
_FIELD_SPECS_D101: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_name", "A", "editable", "text", "itemName", "项目", ""),
    ("prior_unadjusted", "B", "formula", "amount", "priorUnadjusted", "未审数", f"B{5}"),
    ("prior_aje", "C", "formula", "amount", "priorAje", "账项调整", f"B{5}"),
    ("prior_rje", "D", "formula", "amount", "priorRje", "重分类调整", f"B{5}"),
    ("prior_audited", "E", "formula", "amount", "priorAudited", "审定数", f"B{5}"),
    ("current_unadjusted", "F", "formula", "amount", "currentUnadjusted", "未审数", f"F{5}"),
    ("current_aje", "G", "formula", "amount", "currentAje", "账项调整", f"F{5}"),
    ("current_rje", "H", "formula", "amount", "currentRje", "重分类调整", f"F{5}"),
    ("current_audited", "I", "formula", "amount", "currentAudited", "审定数", f"F{5}"),
    ("change_amount", "J", "formula", "amount", "changeAmount", "变动额", f"J{5}"),
    ("change_rate", "K", "formula", "ratio", "changeRate", "变动率", f"J{5}"),
    ("reason_analysis", "L", "editable", "text", "reasonAnalysis", "原因分析", ""),
)

#: ─── 逐格 mask（小计行 10/14/18 全列 + 审定列 E/I 数据行 + 变动列 J/K 全行 + 净值区全格）──
#: 🔴 这是**实测**所有公式格的完整清单，不是推演。
def _build_cell_mask() -> tuple[str, ...]:
    """构建逐格 formula mask（大写 A1 形态）。"""
    cells: list[str] = []
    # 审定列 E/I（= B+C+D / F+G+H）—— 全部数据行 + 小计行 + footer 行
    for col in ("E", "I"):
        for row in (8, 9, 10, 12, 13, 14, 16, 17, 18, 20):
            cells.append(f"{col}{row}")
    # 变动列 J/K —— 全部有数据的行
    for col in ("J", "K"):
        for row in (8, 9, 10, 12, 13, 14, 16, 17, 18):
            cells.append(f"{col}{row}")
    # 小计行 10/14/18 的 B-I（SUM 公式）
    for row in (10, 14, 18):
        for col in ("B", "C", "D", "F", "G", "H"):
            cells.append(f"{col}{row}")
    # 净值区全格（R16-R18 B-K 全为公式 = 原值−坏账）
    for row in (16, 17):
        for col in ("B", "C", "D", "F", "G", "H"):
            cells.append(f"{col}{row}")
    # 跨 sheet 公式（B8/C8/D8 引用 D1-2；B9/C9/D9 同；B12/C12 引用 D1-4；B13/C13 同）
    for col in ("B", "C", "D"):
        for row in (8, 9):
            cells.append(f"{col}{row}")
    for col in ("B", "C"):
        for row in (12, 13):
            cells.append(f"{col}{row}")
    # 期末跨 sheet：F8/G8/H8 引用 D1-2；F9/G9/H9 同；F12/G12 引用 D1-4；F13/G13 同
    for col in ("F", "G", "H"):
        for row in (8, 9):
            cells.append(f"{col}{row}")
    for col in ("F", "G"):
        for row in (12, 13):
            cells.append(f"{col}{row}")
    return tuple(sorted(set(cells)))


_CELL_MASK_D101: Final[tuple[str, ...]] = _build_cell_mask()

#: 字段值来源声明（供四态覆盖状态机用）。
_VALUE_SOURCES: Final[dict[str, AdjudicationValueSource]] = {
    "prior_unadjusted": AdjudicationValueSource.cross_sheet,
    "prior_aje": AdjudicationValueSource.cross_sheet,
    "prior_rje": AdjudicationValueSource.manual,  # 🔴 坏账区 D 列是手工录入
    "prior_audited": AdjudicationValueSource.computed,
    "current_unadjusted": AdjudicationValueSource.cross_sheet,
    "current_aje": AdjudicationValueSource.cross_sheet,
    "current_rje": AdjudicationValueSource.manual,  # 🔴 坏账区 H 列是手工录入
    "current_audited": AdjudicationValueSource.computed,
    "change_amount": AdjudicationValueSource.computed,
    "change_rate": AdjudicationValueSource.computed,
    "reason_analysis": AdjudicationValueSource.manual,
}


SPEC_D101: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_D101,
    sheet_key=SHEET_KEY_D101,
    template_id=TEMPLATE_ID_D101,
    header_rows=(5, 6),
    sections=(SECTION_GROSS, SECTION_BAD_DEBT, SECTION_NET),
    row_mode=AdjudicationRowMode.fixed_rows,
    total_row=18,  # 合计行 = 净值小计行（同一行）
    tb_row=19,     # 试算平衡表数
    diff_row=20,   # 差异数
    footer_marker="合计",
    store_item_id="",  # per-cell 锚点，无单一 store item
    row_identity_key="",  # 固定行无行身份
    per_cell_key_template=f"{D1_ADJ_PREFIX}{{section}}-{{slug}}-{{field}}",
    field_specs=_FIELD_SPECS_D101,
    cell_mask=_CELL_MASK_D101,
    value_sources=_VALUE_SOURCES,
    html_only_item_ids=(),
)


def static_sheet_payload_d11() -> dict:
    """D1-1 静态区寄生声明（挂到 D1-3 主 spec 的 `static_sheets`）。

    ═══ 为什么必须有它（2026-11-16 实测的整册首版发布阻塞）═══

    契约 `d1.notes_receivable_detail.json` 的 `sheets[]` 声明 **13** 张受管 sheet，其中
    `d11-managed` 由 :func:`phase5_adjudication_sheet.static_sheet_payload_for_adjudication`
    生成（`_adjudication_sheet_payload_d11()`）。但 instrumentation 侧只有 **12** 张 ——
    本审定表从来没有进过 `static_sheets` ⇒ 注入后的 workbook 里没有
    `GT_MANAGED_REGION_D11` 这个 definedName ⇒ 观测器
    (`published_identity_observer._sheet_anchors`) 拿不到 `d11-managed` 的
    `physical_sheet_by_key` 条目 ⇒ `observe_structure_inventory` 对整张 sheet 的三张表
    **一个字段都不产出** ⇒ `assert_no_structure_drift` 报
    `sync_contract_structure_drift`，首个点名位置
    `sheet='d11-managed' table='adj_bad_debt_rows' field='d11_adj_bd/change_amount'
    locator='J:static:12'`，整册首版发布 500。

    🔴 与 D5 / D6 / D7 三处 `static_sheet_declarations()` 同病：那三处写的是**契约形态**
       （`locator` + `tables[]` + `footer`），而 `ExcelInstrumentationSpec.static_sheets`
       要的是 **instrumentation 形态**（`region_boundary_locator` + `tables[0].table_key`
       + `excel_name`），且那三处的函数**没有任何调用方**（现算 grep 命中 0）⇒ 它们的
       审定表同样从未进入 instrumentation。本条按 D2-1 / D4-13 / D1-4 的**已验证形态**写，
       不复用那三个死函数。

    三张表（`adj_gross_rows` anchor=A7 / `adj_bad_debt_rows` anchor=A11 /
    `adj_net_rows` anchor=A15）在契约里 `row_identity=None` ⇒ 都是静态表
    （`TableSpec.has_dynamic_rows == False`）。`managed_tables_of` 的静态分支返回本 sheet
    **全部**静态表，故一个 binding（`tables[0].table_key`）即可覆盖三张。
    """
    return {
        "sheet_key": SHEET_KEY_D101,
        "excel_name": MANAGED_SHEET_D101,
        "template_id": TEMPLATE_ID_D101,
        "region_boundary_locator": {
            "anchor": "defined_name_ref",
            "defined_name": GT_MANAGED_REGION_D11,
            "range": _STATIC_REGION_RANGE_D11,
            "region_kind": "static",
        },
        "tables": [
            {"table_key": section.table_key}
            for section in SPEC_D101.sections
        ],
    }
