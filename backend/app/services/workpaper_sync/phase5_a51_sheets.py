# -*- coding: utf-8 -*-
"""A5-1 现金流量表审计 —— 受管 sheet 层声明。

spec: a-cycle-sync-foundation-and-first-canary · Task 12/13

═══ A5-1 册几何（openpyxl 逐格实测）═══

册 `A/A5-1 现金流量表审计.xlsx`（60,894 B）· 9 sheets：
  1. 表头（请先填写）          — 填写基本信息（客户名称/期间/编制人/日期）
  2. A5-1现金流量审计程序       — 程序表（21 步骤 Y/N/NA + 执行人 + 说明 + 索引号）
  3. A5-1-1…现金及现金等价物   — 审定表（8 行：货币资金/受限/等价物/合计/其他/净增减/现金流量表数/差异）
  4. A5-1-3…勾稽关系核对       — 4 组报表勾稽（经营/投资/筹资/净增减额，各含明细+合计+差异）
  5. A5-1-4现金流量核查         — 核查-子公司（两卡片：取得/处置子公司 + 本年变动）
  6. A5-1-5现金流量核查         — 核查-明细（10 行差异分析 + 2 个合计行）
  7. A5-1-6其他现金流量         — 3 类收支（经营/投资/筹资，各含收到+支付）
  8. 会计提示                   — 静态指引文本（不受管）
  9. GT_Custom                  — 隐藏（不受管）

═══ store 模型 ═══

A5-1 的 HTML 侧持久化走 `checklist_responses`，每个字段是独立 `item_id`：
  - `a51-program-step-1.conclusion` / `.executor` / `.description` / `.index_ref`
  - `a51-audit-1.unadjusted` / `.adjustment` / `.explanation` / `.remark`
  - `a51-reconcile-1-{item}.amount` / `.remark` / `.index_ref`
  - ...

这是**扁平键值对型**（非行表型），每个 cell 在 Excel 中有固定位置。
"""
from __future__ import annotations

from typing import Any, Final, Sequence

from app.services.workpaper_sync.sheet_geometry import col_index

# ═══════════════════════════════════════════════════════════════════════════
# 冻结常量
# ═══════════════════════════════════════════════════════════════════════════

ENTRY_ID: Final[str] = "xlsx/gt-a51-cashflow-audit"
ADAPTER_ID: Final[str] = "a51.cashflow_audit"
#: 🔴 **只有 `A5-1`**；`A51C` 是幻影码，已收窄。三条实测依据：
#:
#: 1. 真库现查 `wp_index`：`A5-1` **3 行**、`A51C` **0 行** ⇒ `A51C` 当 matcher 域用时
#:    恒空命中（它是 manifest `wp_code_patterns` 从宿主 Vue 文件名
#:    `GtA51CashflowAudit.vue` CamelCase 反推的产物）。
#: 2. `backend/data/workpaper_sync_entry_wp_code_adjudication.json` 的 `basis_rule`：
#:    wp_code 的真源是契约里**冻结**的 `template.relative_path` 的文件名前缀 ——
#:    `A/A5-1 现金流量表审计.xlsx` ⇒ `A5-1`（该字段进了 contract sha256，改不了）。
#: 3. 现扫确认无任何测试/守卫依赖 `A51C`（其余出现处只有 manifest / slice 两份数据文件
#:    与 A spec 的说明文字，全是「第二 pattern」这一事实陈述，不是判据）。
#:
#: 🔴 **注意**：该裁决表**尚无**本 entry 的条目（现有 36 条覆盖 B60/D/F/G/H/L，A 与 C
#: 循环整类未裁决）⇒ 这里不是「照抄裁决值」，而是按表自己声明的 `basis_rule` 现算。
#: Task 76 的宿主解析走裁决表且 fail-closed（不回落启发式），故本 entry 在裁决条目补上
#: 之前仍报 `unresolved` —— 那是独立的待裁决欠账，不在本模块可修范围内。
WP_CODES: Final[frozenset[str]] = frozenset({"A5-1"})

TEMPLATE_RELATIVE_PATH: Final[str] = "A/A5-1 现金流量表审计.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "2a331368dad3aaf3ac922c8f46a0052e9ba1ec8c0a3ae0504edddc8153dab462"
)
TEMPLATE_SIZE: Final[int] = 60894

# ─── 受管 sheet 声明 ───────────────────────────────────────────────────

#: Sheet 3: A5-1-1 审定表（8 行固定，列 D=年初/E=调整/F=说明/G=审定数/H=备注）
MANAGED_SHEET_AUDIT: Final[str] = "A5-1-1列示于现金流量表的现金及现金等价物"
SHEET_KEY_AUDIT: Final[str] = "a511-audit"

#: Sheet 4: A5-1-3 勾稽核对（4 组，含合计公式 SUM + 差异公式）
MANAGED_SHEET_RECONCILE: Final[str] = "A5-1-3相关报表勾稽关系核对"
SHEET_KEY_RECONCILE: Final[str] = "a513-reconcile"

#: Sheet 5: A5-1-4 核查-子公司
MANAGED_SHEET_CHECK4: Final[str] = "A5-1-4现金流量核查"
SHEET_KEY_CHECK4: Final[str] = "a514-check-subsidiary"

#: Sheet 6: A5-1-5 核查-明细
MANAGED_SHEET_CHECK5: Final[str] = "A5-1-5现金流量核查"
SHEET_KEY_CHECK5: Final[str] = "a515-check-detail"

#: Sheet 7: A5-1-6 其他现金流量
MANAGED_SHEET_OTHER: Final[str] = "A5-1-6其他现金流量"
SHEET_KEY_OTHER: Final[str] = "a516-other-cashflow"

#: 不受管的 sheet（会计提示 + GT_Custom + 程序表 + 表头）
UNMANAGED_SHEETS: Final[tuple[str, ...]] = (
    "表头（请先填写）",
    "A5-1现金流量审计程序",
    "会计提示",
    "GT_Custom",
)

# ═══════════════════════════════════════════════════════════════════════════
# 审定表字段映射（A5-1-1 sheet）
# ═══════════════════════════════════════════════════════════════════════════
#
# Excel 几何（逐格实测）：
#   R7: 表头行（项目 / 年初余额 / 本年调整 / 审计说明 / 审定数 / 备注）
#   R8-R15: 数据行（8 行，固定不扩行）
#     Row 8: 年12月31日货币资金（R8D=年初/R8E=调整/R8F=说明/R8G=审定/R8H=备注）
#     Row 13: 小计（公式 =D8-D9-D10+D11+D12）
#     Row 15: 差异（公式 =G13-G14）
#
# 🔴 不写死行号用常量名；公式行（13/15）是 formula 模式不可编辑

AUDIT_FIELD_MAP: Final[tuple[tuple[str, str, int, str, str], ...]] = (
    # (item_id_suffix, excel_col, excel_row, mode, description)
    # Row 8: 货币资金
    ("1.unadjusted", "D", 8, "editable", "货币资金·年初余额"),
    ("1.adjustment", "E", 8, "editable", "货币资金·本年调整"),
    ("1.explanation", "F", 8, "editable", "货币资金·审计说明"),
    ("1.remark", "H", 8, "editable", "货币资金·备注"),
    # Row 9: 受限存款
    ("2.unadjusted", "D", 9, "editable", "受限存款·年初余额"),
    ("2.adjustment", "E", 9, "editable", "受限存款·本年调整"),
    ("2.explanation", "F", 9, "editable", "受限存款·审计说明"),
    ("2.remark", "H", 9, "editable", "受限存款·备注"),
    # Row 10: 现金等价物
    ("3.unadjusted", "D", 10, "editable", "现金等价物·年初余额"),
    ("3.adjustment", "E", 10, "editable", "现金等价物·本年调整"),
    ("3.explanation", "F", 10, "editable", "现金等价物·审计说明"),
    ("3.remark", "H", 10, "editable", "现金等价物·备注"),
    # Row 11: 外币现金
    ("4.unadjusted", "D", 11, "editable", "外币现金·年初余额"),
    ("4.adjustment", "E", 11, "editable", "外币现金·本年调整"),
    ("4.explanation", "F", 11, "editable", "外币现金·审计说明"),
    ("4.remark", "H", 11, "editable", "外币现金·备注"),
    # Row 12: 上年余额
    ("5.unadjusted", "D", 12, "editable", "上年余额·年初余额"),
    ("5.adjustment", "E", 12, "editable", "上年余额·本年调整"),
    ("5.explanation", "F", 12, "editable", "上年余额·审计说明"),
    ("5.remark", "H", 12, "editable", "上年余额·备注"),
    # Row 13: 小计（公式行 — G13 = formula）
    # Row 14: 现金流量表数
    ("7.unadjusted", "D", 14, "editable", "现金流量表数·年初余额"),
    ("7.adjustment", "E", 14, "editable", "现金流量表数·本年调整"),
    ("7.explanation", "F", 14, "editable", "现金流量表数·审计说明"),
    ("7.remark", "H", 14, "editable", "现金流量表数·备注"),
    # Row 15: 差异（公式行 — 自动计算）
)

#: 审定表的公式列（G 列审定数 = D + E，row 13 小计是 SUM 公式）
AUDIT_FORMULA_CELLS: Final[tuple[tuple[str, int, str], ...]] = (
    ("G", 8, "=D8+E8"),  # 审定数 = 年初 + 调整
    ("G", 9, "=D9+E9"),
    ("G", 10, "=D10+E10"),
    ("G", 11, "=D11+E11"),
    ("G", 12, "=D12+E12"),
    ("G", 13, "=D8-D9-D10+D11+D12"),  # 小计（公式聚合）
    ("G", 14, "=D14+E14"),
    ("G", 15, "=G13-G14"),  # 差异
)

# ═══════════════════════════════════════════════════════════════════════════
# 勾稽核对字段映射（A5-1-3 sheet）
# ═══════════════════════════════════════════════════════════════════════════

RECONCILE_FORMULA_CELLS: Final[tuple[tuple[str, int, str], ...]] = (
    # 组 1：经营活动 (R8-R17 明细, R18 合计=SUM, R19 报表数, R20 差异)
    ("B", 18, "=SUM(B8:B17)"),
    ("B", 20, "=B18-B19"),
    # 组 2：投资活动 (R24-R33 明细, R34 合计, R35 报表数, R36 差异)
    ("B", 34, "=SUM(B24:B33)"),
    ("B", 36, "=B34-B35"),
    # 组 3：筹资活动 (R40-R49 明细, R50 合计, R51 报表数, R52 差异)
    ("B", 50, "=SUM(B40:B49)"),
    ("B", 52, "=B50-B51"),
    # 组 4：净增减额 (R56 计算值)
    ("B", 56, "=B18+B34+B50"),
)

# ═══════════════════════════════════════════════════════════════════════════
# 汇总：全部受管 sheet 清单
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEETS: Final[tuple[str, ...]] = (
    MANAGED_SHEET_AUDIT,
    MANAGED_SHEET_RECONCILE,
    MANAGED_SHEET_CHECK4,
    MANAGED_SHEET_CHECK5,
    MANAGED_SHEET_OTHER,
)

ALL_SHEET_KEYS: Final[tuple[str, ...]] = (
    SHEET_KEY_AUDIT,
    SHEET_KEY_RECONCILE,
    SHEET_KEY_CHECK4,
    SHEET_KEY_CHECK5,
    SHEET_KEY_OTHER,
)

# store item id 前缀（扁平键值对型，非行表型）
STORE_ITEM_PREFIX: Final[str] = "a51-"

# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════


def all_managed_sheet_names() -> tuple[str, ...]:
    return MANAGED_SHEETS


def all_sheet_keys() -> tuple[str, ...]:
    return ALL_SHEET_KEYS

# ═══════════════════════════════════════════════════════════════════════════
# 静态受管区几何（spec workpaper-sync-static-cell-sheet-writeback）
# ═══════════════════════════════════════════════════════════════════════════
#
# A5-1 是**纯静态 entry**：5 张受管 sheet 全固定行，**0 个动态行表**（实测 60 份契约里
# 唯一如此的 reviewed 契约）。归档 spec `workpaper-sync-static-cell-sheet-writeback`
# 的 **DEC-3 明确否决**「给纯静态 sheet 注入退化动态表当载体」⇒ 这里**不造**行表 /
# UUID 列 / footer 锚点，只声明 workbook-scope definedName 区域锚点
# （`region_kind="static"`，引擎侧路径见 `excel_extract._resolve_static_region` /
#  `excel_materialize._plan_static_writes`）。
#
# 🔴 区域范围一律**由字段映射现算**（`_minimal_managed_ref`），不手写死值：手写值与
#    `AUDIT_FIELD_MAP` / `*_FORMULA_CELLS` 脱钩时没有任何判据能发现（区域只会「大一点/
#    小一点」，不会报错），而区域小了就是静默丢格。
#
# 受管区只覆盖**契约声明了 cell 的那两张 sheet**（A5-1-1 审定表 / A5-1-3 勾稽核对）。
# 另三张（A5-1-4 / A5-1-5 / A5-1-6）在 `MANAGED_SHEETS` 里登记为「册内受管面」，但
# **没有任何字段映射** ⇒ 契约里也没有它们的 sheet ⇒ 现在给不出「覆盖全部受管 cell 的
# 最小矩形」。为它们编一个范围就是伪造声明，故此处如实留空；补齐它们要先补字段映射。


def _minimal_managed_ref(cells: Sequence[tuple[str, int]]) -> str:
    """覆盖 `cells` 全部坐标的最小矩形（`$C$R:$C$R` 形态，照 D4-33 `MANAGED_REF_D433`）。

    列跨度按 A1 列序（`col_index`）取 min/max，而不是按字母序 —— 字母序在跨 `Z` 之后
    与真实列序不一致（`AA` < `B`），本册虽只到 H 列，但判据不能依赖「恰好没跨 Z」。
    """
    if not cells:
        raise ValueError("_minimal_managed_ref: cells 不得为空（纯静态区必须有受管 cell）")
    cols = sorted({c for c, _r in cells}, key=col_index)
    rows = sorted({r for _c, r in cells})
    return f"${cols[0]}${rows[0]}:${cols[-1]}${rows[-1]}"


# ─── A5-1-1 审定表 ────────────────────────────────────────────────────

TEMPLATE_ID_AUDIT: Final[str] = "A511"
DEFINED_NAME_AUDIT: Final[str] = f"GT_MANAGED_REGION_{TEMPLATE_ID_AUDIT}"
TABLE_KEY_AUDIT: Final[str] = "a51_audit_table"
#: 表头行（契约 table `anchor` = `A{HEADER_ROW}`，`header_rows=1`）。
HEADER_ROW_AUDIT: Final[int] = 7
FORMULA_MASK_AUDIT: Final[tuple[str, ...]] = tuple(
    f"{col}{row}" for col, row, _f in AUDIT_FORMULA_CELLS
)
#: 受管 cell = 24 个 editable（D/E/F/H × 数据行）+ 8 个 formula（G 列）。
MANAGED_CELLS_AUDIT: Final[tuple[tuple[str, int], ...]] = (
    *((col, row) for _s, col, row, _m, _d in AUDIT_FIELD_MAP),
    *((col, row) for col, row, _f in AUDIT_FORMULA_CELLS),
)
MANAGED_REF_AUDIT: Final[str] = _minimal_managed_ref(MANAGED_CELLS_AUDIT)

# ─── A5-1-3 勾稽核对 ──────────────────────────────────────────────────

TEMPLATE_ID_RECONCILE: Final[str] = "A513"
DEFINED_NAME_RECONCILE: Final[str] = f"GT_MANAGED_REGION_{TEMPLATE_ID_RECONCILE}"
TABLE_KEY_RECONCILE: Final[str] = "a51_reconcile_table"
HEADER_ROW_RECONCILE: Final[int] = 6
FORMULA_MASK_RECONCILE: Final[tuple[str, ...]] = tuple(
    f"{col}{row}" for col, row, _f in RECONCILE_FORMULA_CELLS
)
#: 受管 cell 全是 formula（4 组合计/差异 + 净增减额），无 editable ⇒ 区域首行 18 与表头
#: 行 6 **不相邻**（明细行 8~17 不受管）。审定表那张相邻（受管首行 8 = 表头 7 + 1）。
MANAGED_CELLS_RECONCILE: Final[tuple[tuple[str, int], ...]] = tuple(
    (col, row) for col, row, _f in RECONCILE_FORMULA_CELLS
)
MANAGED_REF_RECONCILE: Final[str] = _minimal_managed_ref(MANAGED_CELLS_RECONCILE)


def static_region_declarations() -> tuple[dict[str, Any], ...]:
    """两张静态受管区的声明（sheet 层单一真源，供契约 / instrumentation / binding 共用）。

    三处消费方（`build_contract_payload` 的 `region_boundary_locator`、instrumentation
    的 `static_sheets`、`ExcelIdentityBinding`）必须读同一份声明 —— 各自手写一份时
    definedName 或 range 漂了没有判据能发现（三者都「自洽」，只是指向不同区域）。
    """
    return (
        {
            "sheet_key": SHEET_KEY_AUDIT,
            "excel_name": MANAGED_SHEET_AUDIT,
            "template_id": TEMPLATE_ID_AUDIT,
            "defined_name": DEFINED_NAME_AUDIT,
            "managed_ref": MANAGED_REF_AUDIT,
            "table_key": TABLE_KEY_AUDIT,
            "header_row": HEADER_ROW_AUDIT,
            "formula_mask": FORMULA_MASK_AUDIT,
        },
        {
            "sheet_key": SHEET_KEY_RECONCILE,
            "excel_name": MANAGED_SHEET_RECONCILE,
            "template_id": TEMPLATE_ID_RECONCILE,
            "defined_name": DEFINED_NAME_RECONCILE,
            "managed_ref": MANAGED_REF_RECONCILE,
            "table_key": TABLE_KEY_RECONCILE,
            "header_row": HEADER_ROW_RECONCILE,
            "formula_mask": FORMULA_MASK_RECONCILE,
        },
    )


#: 顶层 `template_id`（instrumentation / template definition 的 payload 字段）。
#: 取第一张静态区的 id，与平台多 sheet 构建器 `build_instrumentation_payload_for_sheets`
#: 「顶层 template_id 取 specs[0]」同一口径。
TEMPLATE_ID: Final[str] = TEMPLATE_ID_AUDIT
