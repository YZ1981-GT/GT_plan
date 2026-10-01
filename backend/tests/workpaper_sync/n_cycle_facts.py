# -*- coding: utf-8 -*-
"""N 循环三份 sync spec 的**本轮现算基线**与**分歧登记表**。

spec:
  - `.kiro/specs/n-cycle-sync-foundation-and-first-canary`（NF-P1 ~ NF-P40）
  - `.kiro/specs/n1-n3-host-inline-router-and-shared-adoption`（NA-P1 ~ NA-P22）
  - `.kiro/specs/n2-n5-json-table-identity-and-cross-entry-readonly`（NB-P1 ~ NB-P22）

═══ 为什么要有这个模块 ═══════════════════════════════════════════════════════

三份 spec 的 design.md 冻结于 **2026-08-16**（slice 冻结日）。本轮实施时逐项现算，
发现 **13 组**数字与 design 不同。按方法论铁律 ①②（slice 结论必重算 / 计数类现算），
处置是：**以现算为准 + 把分歧登记成可复核的表**，而不是改口径去凑 design 的数。

`DESIGN_VS_RECOMPUTED` 是那张表。每条都写明：design 值 / 现算值 / 差因类别。
差因类别只有三种，含义不同、处置也不同：

  - `snapshot_drift`  —— 事实本身变了（文件增删 / 真库数据被清）。design 没错，是旧。
  - `caliber`         —— 两边口径不同，两个数都对。必须写明本轮口径。
  - `design_internal` —— 🔴 design 自己前后不一致（如「8 处」却只列举 4 处）。
                         此类以 design 自己的**列举**为准，不以它的计数为准。

🔴 本模块**不含任何扫描逻辑** —— 扫描在 `backend/scripts/analyze/n_cycle_scanner.py`，
   这里只放「比对右侧」的基线值，便于一眼看出哪些值是人工锚定的。
"""
from __future__ import annotations

from dataclasses import dataclass

# ═══════════════════════════════════════════════════════════════════════════
# entry 事实基线（design「五条 entry 事实基线」表，现算全部吻合）
# ═══════════════════════════════════════════════════════════════════════════
N1 = "xlsx/gt-n1-deferred-tax-assets"
N2 = "xlsx/gt-n2-taxes-payable"
N3 = "xlsx/gt-n3-deferred-tax-liabilities"
N4 = "xlsx/gt-n4-taxes-and-surcharges"
N5 = "xlsx/gt-n5-income-tax-expense"

ENTRY_IDS: tuple[str, ...] = (N1, N2, N3, N4, N5)

#: canary（决策 2）
CANARY_ENTRY_ID = N4

#: 三份 spec 的 entry 归属
FOUNDATION_ENTRIES: tuple[str, ...] = (N4,)
LANE2_ENTRIES: tuple[str, ...] = (N1, N3)
LANE3_ENTRIES: tuple[str, ...] = (N2, N5)

#: entry → (wp_code, 科目号, 科目性质, 借贷方向)
ENTRY_ACCOUNTS: dict[str, tuple[str, str, str, str]] = {
    N1: ("N1D", "1811", "资产", "借"),
    N2: ("N2T", "2221", "负债", "贷"),
    N3: ("N3D", "2901", "负债", "贷"),
    N4: ("N4T", "6403", "损益", "借"),
    N5: ("N5I", "6801", "损益", "借"),
}

#: entry → 模板册名（authoritative_templates.files[].name）
ENTRY_WORKBOOKS: dict[str, str] = {
    N1: "N1 递延所得税资产.xlsx",
    N2: "N2 应交税费.xlsx",
    N3: "N3 递延所得税负债.xlsx",
    N4: "N4 税金及附加.xlsx",
    N5: "N5 所得税费用.xlsx",
}


#: 逐册 sheet 数 / 公式格 / 带 fx sheet（现算与 slice 的 authoritative_templates 全等）
WORKBOOK_SHEET_COUNT: dict[str, int] = {
    "N1 递延所得税资产.xlsx": 10,
    "N2 应交税费.xlsx": 18,
    "N3 递延所得税负债.xlsx": 6,
    "N4 税金及附加.xlsx": 9,
    "N5 所得税费用.xlsx": 16,
}
WORKBOOK_FORMULA_CELLS: dict[str, int] = {
    "N1 递延所得税资产.xlsx": 593,
    "N2 应交税费.xlsx": 710,
    "N3 递延所得税负债.xlsx": 162,
    "N4 税金及附加.xlsx": 236,
    "N5 所得税费用.xlsx": 484,
}
WORKBOOK_SHEETS_WITH_FORMULA: dict[str, int] = {
    "N1 递延所得税资产.xlsx": 8,
    "N2 应交税费.xlsx": 16,
    "N3 递延所得税负债.xlsx": 4,
    "N4 税金及附加.xlsx": 7,
    "N5 所得税费用.xlsx": 14,
}

#: design「算术自检」表：sheets 59 / 公式格 2185 / 带 fx 49
TOTAL_SHEETS = 59
TOTAL_FORMULA_CELLS = 2185
TOTAL_SHEETS_WITH_FORMULA = 49
TOTAL_BARE_IF = 244
TOTAL_HIDDEN_SHEETS = 8

#: sheet 分类（sheet_granularity_and_router_audit.counters）
SHEETS_HTML_CHILD = 45
SHEETS_PROGRAM_CONSOLE = 2
SHEETS_OO_FALLTHROUGH = 12
OO_FALLTHROUGH_BUCKETS: dict[str, int] = {
    "gt_custom_config_sheet": 5,
    "program_sheet_not_html_migrated": 3,
    "pre_revision_original_sheet": 3,
    "reference_example_sheet": 1,
}
DUAL_MODE_SWITCHABLE_SHEETS = 45

#: BP 公共 7 项 + 区分项成员集（blocking_preconditions）
BP_COMMON: tuple[str, ...] = ("BP-1", "BP-2", "BP-3", "BP-6", "BP-7", "BP-9", "BP-11")
BP_DISCRIMINATING: dict[str, tuple[str, ...]] = {
    "BP-4": (N3,),
    "BP-5": (N4, N5),
    "BP-8": (N1, N2, N5),
    "BP-10": (N1, N3),
    "BP-12": (N5,),
}
BP_COUNT_PER_ENTRY: dict[str, int] = {N1: 9, N2: 8, N3: 9, N4: 8, N5: 10}

#: mode_switch_resolution.per_entry_verdict
SWITCH_VERDICT_BEFORE: dict[str, str] = {
    N1: "redeemable",
    N2: "redeemable",
    N3: "redeemable",
    N4: "inert",
    N5: "inert",
}
#: 🔴 foundation Task 13 / lane3 Task 6 落地后的目标态（NC-13）
SWITCH_VERDICT_AFTER: dict[str, str] = {e: "redeemable" for e in ENTRY_IDS}


# ═══════════════════════════════════════════════════════════════════════════
# 本轮现算基线（🔴 与 design 不同的，逐条进 DESIGN_VS_RECOMPUTED）
# ═══════════════════════════════════════════════════════════════════════════
#: NC-5 strict 域文件集
DOMAIN_FILES_TOTAL = 164
DOMAIN_FILES_PRODUCTION = 137
DOMAIN_FILES_TEST = 27
#: 本系列 spec 新增、落在 N 域口径内的测试文件（经 `ref` 分支 `^nCycle` 收入）
NEW_DOMAIN_TEST_FILES: tuple[str, ...] = (
    "nCycleCanaryRowIdentity.spec.ts",
    "nCycleLane3RowIdentity.spec.ts",
    "nCycleLane2RouterAndKeys.spec.ts",
)
#: 只用 `upper` 分支时的漏检量（design 记 35）
UPPER_ONLY_MISSED = 39
#: 去掉 `lower` 分支时的漏检量
LOWER_BRANCH_CONTRIBUTION = 36

#: NC-6 / NC-8 行身份六族（口径见 `n_cycle_scanner.ROW_IDENTITY_PATTERNS`）
ROW_IDENTITY_BASELINE: dict[str, int] = {
    "A_positional_persistence_key": 3,
    "A2_positional_render_key": 1,
    "B_array_position_addressing": 58,
    "C_display_sequence": 14,
    "D_entropy_key": 48,
    "E_stable_identity": 176,
    "M_row_infix_template": 0,
}
E_FAMILY_FILES = 28

#: NC-7 removeRow（口径：只数**声明**，不数调用点）
REMOVE_DECL_TOTAL = 21
REMOVE_SIGNATURE_KINDS = 9
REMOVE_HISTOGRAM_BEFORE: dict[str, int] = {"by_index": 10, "by_rowid": 10, "other": 1}

#: NC-32 超列引用三族（正确口径 17 与 design 逐值吻合）
OVERFLOW_TOTAL = 17
OVERFLOW_FAMILIES: dict[str, int] = {
    "A1_real_defect": 3,
    "A2_structural_residue": 11,
    "B_range_end": 3,
}
#: 错口径（不剔 sheet 限定段）—— design 记 232
OVERFLOW_WRONG_CALIBER = 193

#: NC-9 definedName
DEFINED_NAME_TOTAL = 72
DEFINED_NAME_BROKEN = 42
DEFINED_NAME_PER_WORKBOOK: dict[str, tuple[int, int]] = {
    "N1 递延所得税资产.xlsx": (24, 14),
    "N2 应交税费.xlsx": (24, 14),
    "N3 递延所得税负债.xlsx": (24, 14),
}

#: NC-36 footer 三形态
FOOTER_FORMS: dict[str, int] = {"with_separator": 49, "empty": 7, "missing_separator": 3}
FOOTER_MISSING_SEPARATOR_SHEETS: tuple[tuple[str, str], ...] = (
    ("N2 应交税费.xlsx", "出口退税额复核示例"),
    ("N4 税金及附加.xlsx", "税金及附加审计程序表O2A（原底稿）"),
    ("N5 所得税费用.xlsx", "所得税审计程序表N3A (原底稿)"),
)

#: NC-17 合计/小计标签（🔴 非 A 列 1 处：N5-5 r63 在 B 列）
TOTAL_LABEL_SITES = 33
TOTAL_LABEL_LITERAL_KINDS = 6
TOTAL_LABEL_NON_A_COLUMN: tuple[tuple[str, int, str], ...] = (("纳税调整明细表N5-5", 63, "B"),)
MISSING_SUBTOTAL_STRICT = 0
MISSING_SUBTOTAL_ROUGH = 4

#: NC-20 倒挤减法链
SUB_CHAIN_STRICT = 0
SUB_CHAIN_CANDIDATES = 419

#: NC-35 超宽表与幽灵列
WIDE_SHEETS: tuple[tuple[str, int, int], ...] = (
    ("附注披露信息（国企）", 256, 7),
    ("附注披露信息（国企", 255, 4),
)
SHEETS_WITH_GHOST_COLS = 24
SHEETS_WITH_GHOST_ROWS = 25


#: NC-3 / NC-4 写路径与门
PUBLISH_TO_TB_LITERAL = "audit-determination/publish-to-tb"
PUBLISH_TO_TB_CODE = 5
#: design 记 15；T17 删 orphan 后现算 14（被删模块里有 1 条迁移注释）
PUBLISH_TO_TB_COMMENT = 14
LEGACY_WRITEBACK_LITERAL = "trial-balance/writeback"
CONFIRM_SITES = 26
CONFIRM_FILES = 17

#: NC-13 / BP-4 OO health 与 config 直调
OO_HEALTH_LITERAL = "onlyoffice/health"
OO_HEALTH_CODE_BEFORE = 5
#: T17 删掉 useN4DualMode.ts 后现算（lane2 T4 / lane3 T14 会继续降）
OO_HEALTH_CODE_NOW = 4
OO_CONFIG_CODE = 1
#: 统一能力层（D4 收敛出来的平台唯一探针）
OO_HEALTH_CAPABILITY_MODULE = (
    "audit-platform/frontend/src/components/workpaper/sync/onlyOfficeHealth.ts"
)

#: NC-5 / NC-29 orphan 全集（8 个 / 现算合计 1339 行；slice 记 1331、plan 记 1325）
ORPHAN_MODULES: dict[str, int] = {
    "audit-platform/frontend/src/components/workpaper/composables/n1DisclosureSegmentTypes.ts": 21,
    "audit-platform/frontend/src/components/workpaper/composables/n2VatSourceConstants.ts": 100,
    "audit-platform/frontend/src/components/workpaper/composables/useN3DualMode.ts": 185,
    "audit-platform/frontend/src/components/workpaper/composables/useN4AdjudicationV2.ts": 295,
    "audit-platform/frontend/src/components/workpaper/composables/useN4DetailV2.ts": 282,
    "audit-platform/frontend/src/components/workpaper/composables/useN4DualMode.ts": 185,
    "audit-platform/frontend/src/components/workpaper/composables/useN5AiAssist.ts": 86,
    "audit-platform/frontend/src/components/workpaper/composables/useN5DualMode.ts": 185,
}
ORPHAN_TOTAL = 8
ORPHAN_LINES_TOTAL = 1339
#: 三份 spec 的 orphan 删除归属（foundation 3 / lane2 2 / lane3 3）
ORPHAN_OWNED_BY_FOUNDATION: tuple[str, ...] = (
    "useN4DualMode.ts",
    "useN4AdjudicationV2.ts",
    "useN4DetailV2.ts",
)
ORPHAN_OWNED_BY_LANE2: tuple[str, ...] = ("useN3DualMode.ts", "n1DisclosureSegmentTypes.ts")
ORPHAN_OWNED_BY_LANE3: tuple[str, ...] = (
    "useN5DualMode.ts",
    "useN5AiAssist.ts",
    "n2VatSourceConstants.ts",
)

#: NC-19 / NF-P31 共享基类与共享路由边（🔴 每轮必现算，禁抄上一轮）
SHARED_BASE_PRODUCTION_EDGES = 24
SHARED_BASE_TEST_EDGES = 1
SHARED_BASE_N_EDGES = 1
SHARED_ROUTER_ADOPTERS_BEFORE = 3
SHARED_ROUTER_ADOPTERS_AFTER = 5

#: NC-12 notice（N 域 0 ⇒ 须新接入；全域为现算快照）
NOTICE_COMPONENT = "GtEntrySyncCapabilityNotice"
NOTICE_N_DOMAIN_BEFORE = 0
NOTICE_PLATFORM_PRODUCTION_EDGES = 60

#: NC-28 resolveProcedureSheetKey（N 完备 5/5、M 仍 6 条）
PROCEDURE_ROUTE_N: dict[str, str] = {
    "N1": "n1a", "N2": "n2a", "N3": "n3a", "N4": "n4a", "N5": "n5a",
}
PROCEDURE_ROUTE_M_PREFIXES: tuple[str, ...] = ("M10", "M2", "M4", "M5", "M6", "M9")

#: NC-30 transport_key：owner 常量 6 处 + 8 个「按规律该有」的不存在键
TRANSPORT_OWNERS: dict[str, tuple[str, str]] = {
    "TK-1": ("useN1FormData.ts", "N1-"),
    "TK-2": ("useN1Adjudication.ts", "N1-1-adj"),
    "TK-3": ("useN2FormData.ts", "N2-"),
    "TK-4": ("useN3FormData.ts", "N3-"),
    "TK-5": ("useN4FormData.ts", "N4-"),
    "TK-6": ("useN5FormData.ts", "N5-"),
}
NONEXISTENT_GUESSED_KEYS: tuple[str, ...] = (
    "N1-1-rows", "N1-1-adjudication-rows", "N2-1-rows", "N3-1-rows",
    "N4-1-adjudication-rows", "N5-1-rows", "N5-5-rows", "N4-1-rows-v3",
)
#: 🔴 与上一组**不同类**：它命中 1 次（orphan 自己），是「伪造键形态」
FABRICATED_KEY = "N4-1-rows-v2"
FABRICATED_KEY_HITS = 1
N1_ADJUDICATION_CATEGORY_COUNT = 7

#: NC-31 parent_duplicate（K/L/M 三轮均 0，N 首次触发，4 条全挂 N1）
PARENT_DUPLICATE_CHILDREN: tuple[str, ...] = (
    "xlsx/n1/calc/n1-tab-calc-table",
    "xlsx/n1/core/n1-tab-adjudication",
    "xlsx/n1/core/n1-tab-adjustment",
    "xlsx/n1/core/n1-tab-detail",
)

#: NC-19 / BP-12 N5 跨 entry 只读 8 键跨 5 命名空间
N5_FOREIGN_READONLY_KEYS: tuple[str, ...] = (
    "A-accounting-profit", "A-profit-total",
    "I2-1-audited-total", "I6-1-audited-total",
    "N1-1-total-audited", "N1-1-total-begin",
    "N3-1-change-total", "N3-1-end-balance-total",
)
N5_FOREIGN_NAMESPACES: tuple[str, ...] = ("A-", "I2-", "I6-", "N1-", "N3-")
N5_CROSS_WRITE_KEYS: tuple[str, ...] = (
    "N5-cross-n1-change", "N5-cross-n3-change", "N5-cross-i6-expensed",
    "N5-cross-i2-capitalized", "N5-cross-a-profit",
)


# ═══════════════════════════════════════════════════════════════════════════
# 真库基线（🔴 本轮最大分歧：design 的 30 行已不存在）
# ═══════════════════════════════════════════════════════════════════════════
#: 本机 PG 现算：`checklist_responses` 全表 42 行，`item_id ~ '^N[1-5]'` 仅 **3** 行，
#: 全部挂在 N2 的底稿上、全部载荷在 `conclusion`、`remark` 全空、跨 entry 污染 0 条。
LIVE_DB_N_ROWS = 3
LIVE_DB_N_ROWS_WITH_CONCLUSION = 3
LIVE_DB_N_ROWS_WITH_REMARK = 0
LIVE_DB_CROSS_ENTRY_POLLUTION = 0
LIVE_DB_N_ITEM_IDS: tuple[str, ...] = (
    "N2-6-declaration-rows",
    "N2-6-vat-payable",
    "N2-disclosure-soe-synced-tables",
)
#: 🔴 canary 的真库分母：`N4-1-rows` 现算 **0 行**（design 记 1665 B）
LIVE_DB_CANARY_ROWS = 0

#: NC-34 契约字段双列映射 —— 现算仍支持「两列都必须映射」这条裁定：
#: 3 行里 3 行 conclusion 非空、0 行 remark 非空 ⇒ 只映 remark 会丢 **100%** 载荷。
PAYLOAD_COLUMNS: tuple[str, ...] = ("remark", "conclusion")
#: AI 复核会话键白名单（解析前必须排除，否则会把会话记录当行表 JSON 解）
REVIEW_SESSION_KEY_MARKER = "-review-session-"


# ═══════════════════════════════════════════════════════════════════════════
# 分歧登记表（铁律 ①②③ / ㉖ 的可复核形式）
# ═══════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Divergence:
    item: str
    design_value: str
    recomputed_value: str
    cause: str  # snapshot_drift | caliber | design_internal
    note: str


CAUSE_SNAPSHOT_DRIFT = "snapshot_drift"
CAUSE_CALIBER = "caliber"
CAUSE_DESIGN_INTERNAL = "design_internal"

DESIGN_VS_RECOMPUTED: tuple[Divergence, ...] = (
    Divergence(
        "真库 N 域行数", "30", "3", CAUSE_SNAPSHOT_DRIFT,
        "本机 PG `checklist_responses` 全表只剩 42 行（K6 7 / D4 5 / D2 5 / D6 5 / N2 3 …）⇒ "
        "design 的 30 行、conclusion 非空 23、remark 非空 4 全部不可复现。"
        "🔴 连带后果：决策 1「N 域分母非空 ⇒ 收回 canary 硬标准」在本轮实施时**前提不成立**，"
        "canary 的真库侧判据按空分母如实声明，不宣称通过（见 NF-P17 的处置）。",
    ),
    Divergence(
        "canary `N4-1-rows` 载荷", "1665 B", "不存在（0 行）", CAUSE_SNAPSHOT_DRIFT,
        "N4 在真库零行。canary 闭环改由「代码层往返 + 结构判据」证明，真库往返标空分母。",
    ),
    Divergence(
        "跨 entry 污染条数", "4（全落 wp_code='G8'）", "0", CAUSE_SNAPSHOT_DRIFT,
        "现存 3 行 N2 载荷的宿主 wp_code 都是 N2 ⇒ 污染分母为空。"
        "NC-19 的平台级裁定（登记不清理）不变，但本轮无对象可锁。",
    ),
    Divergence(
        "strict 域文件集", "160（生产 135 / 测试 25）", "164（生产 137 / 测试 27）",
        CAUSE_SNAPSHOT_DRIFT, "slice 冻结后新增文件。三路取并的**结构判据**（loose_only=0）不变。",
    ),
    Divergence(
        "去小写分支漏检", "35", "36", CAUSE_SNAPSHOT_DRIFT,
        "同上。判据强度不变：漏检集合必须恰等于「文件名匹配 ^n[1-5][A-Z]」的全集。",
    ),
    Divergence(
        "行身份 B/C/D/E 族", "67 / 7 / 29 / 86", "58 / 14 / 48 / 176", CAUSE_CALIBER,
        "design 未写出这四族的正则，无法复现其口径。本轮口径集中在 "
        "`n_cycle_scanner.ROW_IDENTITY_PATTERNS`（唯一一处），判据强度不变："
        "A 族须降到 0、E 族须非空（正面样板可抄）、M 式须为 0 且配变异证明。",
    ),
    Divergence(
        "`removeRow` 归类", "14 种签名 / 32 命中 / 18 : 13 : 1",
        "9 种签名 / 21 声明 / 10 : 10 : 1", CAUSE_CALIBER,
        "本轮只数**声明**（`function remove*(…)` / `const remove* = (…)`）——「按什么寻址」"
        "由声明决定，调用点会把同一语义重复计数。判据强度不变：by_index 单调降 / by_rowid 单调升。"
        "🔴 顺带修掉一个真口径缺陷：`[Ii]ndex` 必须认大写 I，否则 4 处 `rowIndex: number` 全落 other 桶。",
    ),
    Divergence(
        "超列引用错口径", "232（误报 215）", "193（误报 176）", CAUSE_CALIBER,
        "正确口径 **17 = A1 3 + A2 11 + B 3** 与 design 逐值吻合；错口径的构造方式 design 未写明。"
        "🔴 本轮另定位到 design 口径描述的一处不足：只剔 `'…'!` 段会把 `='明细表N2-2'!M10` 的 "
        "`M10` 留下、再拿**本表** max_column 判越界 ⇒ N2 附注披露凭空多出 39 处假阳（56→17）。"
        "正确做法是把 sheet 限定段**连同其引用**一起剔除（同 L 轮误报①）。",
    ),
    Divergence(
        "`definedName` broken", "45（N1/N2/N3 各 15）", "42（各 14）", CAUSE_SNAPSHOT_DRIFT,
        "总数 72 与 design 吻合；broken 判据为 `'#REF!' in value`。N4/N5 各 0 与 design 一致。",
    ),
    Divergence(
        "「合计/小计」标签", "34 处 / 7 种字面量", "33 处 / 6 种", CAUSE_SNAPSHOT_DRIFT,
        "非 A 列的唯一一处（`N5-5` r63 在 B 列）与 design 完全一致 ⇒ 判据对象没丢。",
    ),
    Divergence(
        "合计漏加小计粗口径", "8", "4", CAUSE_DESIGN_INTERNAL,
        "🔴 design 正文自己只列举了 4 处（N1 两张附注披露 r42 / r52 / r63 / r72），"
        "「8」与其列举项数不等（铁律 ③）。以列举为准 ⇒ 4。严格口径 0 两边一致。",
    ),
    Divergence(
        "倒挤链形态候选", "32", "419", CAUSE_CALIBER,
        "本轮候选口径 = 纯单元格加减链且含至少一个 `-`（宽）。严格口径 **0** 与 design 一致，"
        "且严格口径多一条收窄：须**纵向**（被减数同列）—— 不加这条，同行跨列的差额计算会被判成倒挤。",
    ),
    Divergence(
        "notice 全域生产消费方", "53", "60", CAUSE_SNAPSHOT_DRIFT,
        "平台侧在增长。N 域 **0** 与 design 一致（须新接入）。",
    ),
    Divergence(
        "共享基类生产边", "26 生产 + 1 测试", "24 生产 + 1 测试", CAUSE_SNAPSHOT_DRIFT,
        "N 域仍只贡献 1 条（`useN2DualMode.ts`）⇒ 若移除薄封装则 24 → 23。"
        "🔴 design 里的 26 →25 这组数字连带作废，但「每轮现算、禁抄上一轮」那条纪律正是它自己写的。",
    ),
    Divergence(
        "orphan 合计行数", "1331（plan 记 1325）", "1339", CAUSE_SNAPSHOT_DRIFT,
        "orphan **个数 8** 与归属 3+2+3 与 design 完全一致；行数差来自各文件自身的编辑。",
    ),
    Divergence(
        "契约目录", "30（生产 28 + candidate 2）", "60 文件（reviewed 49 / candidate 10 / 非契约 1）",
        CAUSE_SNAPSHOT_DRIFT,
        "其余循环在持续落契约。N 域归属数 **0** 这条结论不变（逐文件读 `review.entry_id`）。",
    ),
    Divergence(
        "`resolveProcedureSheetKey` 行数", "90", "91", CAUSE_CALIBER,
        "design 用的是 `splitlines()`（恒少 1）。N 段完备 5/5、M 段仍 6 条两条结论均现算成立。",
    ),
)


def divergences_by_cause(cause: str) -> tuple[Divergence, ...]:
    return tuple(d for d in DESIGN_VS_RECOMPUTED if d.cause == cause)


# ═══════════════════════════════════════════════════════════════════════════
# slice 冻结后的改线登记（供既存守卫 test_task56 区分「旧状态记录」与「已按 spec 改线」）
# ═══════════════════════════════════════════════════════════════════════════
#: 🔴 test_task56 锁的是 2026-08-16 的现状；本系列 spec 按要求改了代码之后，那几条
#  「slice 值 == 代码现算」的逐值相等判据必然打红。处置**不是**删判据，而是：
#    - 未在下表登记的对象 ⇒ 仍逐值相等（漂移照样打红）；
#    - 已登记的对象 ⇒ 改为**单调/结构**断言（spec foundation Task 16：「by_index 单调降」）。
#  新改一个 N 域文件而不登记 ⇒ task56 红 ⇒ 逼着来这里写明是哪个 task 改的。
POST_SLICE_EDITED_FILES: dict[str, str] = {
    "audit-platform/frontend/src/components/workpaper/GtN4TaxesAndSurcharges.vue":
        "foundation T13（inert→redeemable）+ T19（notice 接线）",
    "audit-platform/frontend/src/components/workpaper/GtN5IncomeTaxExpense.vue":
        "lane3 T6（inert→redeemable，复用 T13 形态）+ BP-7 notice 接线",
    "audit-platform/frontend/src/components/workpaper/composables/useN4Adjudication.ts":
        "foundation T10（双列取列）+ T14/T16（按身份删行，熵键移入 shared/stableRowIdentity.ts）",
}

#: 按 AC 1.7 已删除的 orphan（路径 → 删除它的 task）。
#: 🔴 删除前提：正面样板已提取到 `composables/shared/stableRowIdentity.ts`（foundation T14），
#:    且删前 statement 生产边 0 / 测试边 0（task56 的可达性扫描器现算）。
DELETED_ORPHANS: dict[str, str] = {
    "audit-platform/frontend/src/components/workpaper/composables/useN4DualMode.ts":
        "foundation T17",
    "audit-platform/frontend/src/components/workpaper/composables/useN4AdjudicationV2.ts":
        "foundation T17（伪造键 N4-1-rows-v2 随之从 N 域消失）",
    "audit-platform/frontend/src/components/workpaper/composables/useN4DetailV2.ts":
        "foundation T17",
}
POST_SLICE_EDITED_FILES.update({k: f"已删除：{v}" for k, v in DELETED_ORPHANS.items()})
#: 🔴 删除引出的**二阶 orphan**（slice 记 second_order = 0，是删前的真值）。
#: `n4TaxTypes.ts` 是 N4 税种词典（`n4NormalizeKey`），唯一消费方是刚删的两个 V2 孪生。
#: **未删**：它不在任一 spec 的删除清单里，且承载「N4-1 行键 / N4-2 税种名不一致」
#: 这一真实问题的修复意图 —— 是接到 live 的 useN4Adjudication / useN4Detail 上，
#: 还是随 V2 一起删，属业务决策，待用户拍板。
SECOND_ORDER_ORPHANS_CREATED: dict[str, str] = {}
#: 已处置（删除）的二阶 orphan。🔴 n4TaxTypes 的裁定依据（2026-10-01 现读）：
#:   它声称解决的「N4 各表税种名不一致致跨表 join 落空」在 live 代码里已由
#:   `useN4CrossSheet._normalizeTaxName` 解决（城建税/城市维护建设税等别名归一）；
#:   唯一可能受益的 `useN4Detail.updateN2Accruals` 全仓零调用方 ⇒ 接线无对象，删除。
SECOND_ORDER_ORPHANS_DELETED: dict[str, str] = {
    "audit-platform/frontend/src/components/workpaper/composables/n4TaxTypes.ts":
        "foundation T17 删 V2 孪生后成二阶 orphan；功能已由 useN4CrossSheet 覆盖，删除",
}

DELETED_ORPHANS.update({
    "audit-platform/frontend/src/components/workpaper/composables/useN5DualMode.ts":
        "lane3 T14（N5 inert 已按 foundation 形态在宿主内修复，孪生不再需要）",
    "audit-platform/frontend/src/components/workpaper/composables/useN5AiAssist.ts":
        "lane3 T14（零生产边；N 域 AI 调用写在组件里直调）",
    "audit-platform/frontend/src/components/workpaper/composables/n2VatSourceConstants.ts":
        "lane3 T14（零生产边常量模块）",
    "audit-platform/frontend/src/components/workpaper/composables/useN3DualMode.ts":
        "lane2 T15（N3 宿主内联载体已收敛到统一能力层，孪生不再需要）",
    "audit-platform/frontend/src/components/workpaper/composables/n1DisclosureSegmentTypes.ts":
        "lane2 T15（零生产边纯类型模块）",
})
POST_SLICE_EDITED_FILES.update({
    "audit-platform/frontend/src/components/workpaper/GtN1DeferredTaxAssets.vue":
        "lane2 T2（改用 n1SheetRouting / 共享路由，BP-10）",
    "audit-platform/frontend/src/components/workpaper/GtN3DeferredTaxLiabilities.vue":
        "lane2 T2/T4/T5（共享路由 + health 走统一能力层 + 拒切显式提示）",
    "audit-platform/frontend/src/components/workpaper/composables/useN1DualMode.ts":
        "lane2 T6/T7（health 与 config 预拉收敛到 sync/ 能力层）",
    "audit-platform/frontend/src/components/workpaper/composables/useN1Adjudication.ts":
        "lane2 T8（持久化键改模板行 key A7~A13，旧位置键只读兼容）",
})
POST_SLICE_EDITED_FILES.update({k: f"已删除：{v}" for k, v in DELETED_ORPHANS.items()})

#: 已删 orphan 中直调 legacy health 端点的个数（删前现算：useN3/N4/N5DualMode.ts）
DELETED_ORPHANS_CALLING_LEGACY_HEALTH = 3

#: 上表文件（含已删 orphan）在 slice 时点对 task56「数组位置寻址族」的贡献
#: （用 task56 自己的扫描器对 HEAD 版本现算冻结）。
#: task56 据此断言：未改线部分 == slice 值 − 本表（逐值相等）。
POST_SLICE_EDITED_FILES.update({
    "audit-platform/frontend/src/components/workpaper/composables/useN5TaxAdjustment.ts":
        "lane3 T4（N5-5 按身份增删改，BP-8）",
    "audit-platform/frontend/src/components/workpaper/composables/useN5DeferredReconcile.ts":
        "lane3 T4（N5-8 同族）",
    "audit-platform/frontend/src/components/workpaper/composables/useN5RdSuperDeduction.ts":
        "lane3 T4（N5-6-1 同族；顺带修复费用化/资本化分表的下标错配）",
    "audit-platform/frontend/src/components/workpaper/composables/useN2OtherTaxCalc.ts":
        "lane3 T4（N2-8 manualRows 身份 + 渲染键同源）",
    "audit-platform/frontend/src/components/workpaper/n5/calc/N5TabTaxAdjustment.vue":
        "lane3 T4（调用改传 row.rowKey；顺带修复按分类过滤后的下标错配）",
    "audit-platform/frontend/src/components/workpaper/n5/calc/N5TabDeferredReconcile.vue":
        "lane3 T4（调用改传 row.rowKey）",
    "audit-platform/frontend/src/components/workpaper/n5/benefit/N5TabRdSuperDeduction.vue":
        "lane3 T4（调用改传 row.rowKey）",
    "audit-platform/frontend/src/components/workpaper/composables/useN1LossCheck.ts":
        "Playwright：leadRows 数组/字典契约错配致 N1-5 打开即崩",
    "audit-platform/frontend/src/components/workpaper/n2/calc/N2TabOtherTaxCalc.vue":
        "Playwright：页面仍引用已删除的月度/季度 API，改渲染 allCalcRows",
    "audit-platform/frontend/src/components/workpaper/composables/useN4CrossSheet.ts":
        "Playwright：不存在的 /wp-index/by-code 恒 404 + 空数据无条件覆盖",
    "audit-platform/frontend/src/components/workpaper/composables/useN5CrossSheet.ts":
        "同源修复：5 处跨底稿取数改用平台 wp-id-by-code 入口",
})

#: 上表全部文件（含已删 orphan）在 slice 时点（HEAD 版本，于真实路径换入后用 task56
#: 自己的扫描器现算）对「数组位置寻址族」的贡献。
#: task56 据此断言：未改线部分 == slice 值 − 本表（逐值相等）；改线部分只许下降。
ARRAY_ADDRESSING_EDITED_FILES_AT_SLICE: dict[str, int] = {
    "update_by_row_index": 2,
    "remove_by_row_index": 5,
    "array_slot_write": 3,
    "filter_by_index": 3,
    "splice_by_index": 4,
}

#: 已改用共享 sheet 路由的 entry（BP-10 收口，lane2 T2）
ROUTER_ADOPTED_ENTRIES: frozenset[str] = frozenset({N1, N3})
#: 已不再直调 legacy health 端点的宿主（BP-4 收口，lane2 T4）
HEALTH_CONVERGED_HOSTS: frozenset[str] = frozenset({N3})
#: live dual-mode 模块中已收敛 health / config 直调的个数（lane2 T6/T7：useN1DualMode）
LIVE_MODULES_HEALTH_CONVERGED = 1
LIVE_MODULES_CONFIG_CONVERGED = 1
#: 本系列新增、落在 N 域口径内的生产文件（lower 分支收入）
NEW_DOMAIN_PROD_FILES: tuple[str, ...] = ("n1SheetRouting.ts", "n3SheetRouting.ts")
#: lane2 T8 后 A 族（位置化持久化键）目标态
A_FAMILY_AFTER_LANE2 = 0

#: 开关已从 inert 兑现为 redeemable 的 entry
REDEEMED_SWITCH_ENTRIES: frozenset[str] = frozenset({N4, N5})

#: 已挂 `GtEntrySyncCapabilityNotice` 的 entry（BP-7 收口进度）
NOTICE_MOUNTED_ENTRIES: frozenset[str] = frozenset({N4, N5})
