/**
 * D3 预收账款受管 sheet 的**单一来源清单** —— 前端受管判定的唯一真源。
 *
 * spec: d3-sync-coverage-via-row-table-engine · Task 16 · Requirements 6.6
 * design.md Property 12：前端受管 sheet 集合从 provider 派生、不前端硬编码字面量清单。
 *
 * ═══ 为什么这份清单要与后端逐字对齐、而不是散落在宿主里写死 ═══
 *
 * 现状（本任务要消灭的反模式）：`GtD3PrepaidAccounts.vue` 里
 *     const isD3DetailSheet = computed(() => currentSheet.value === 'D3-2')
 * 把「哪些 sheet 受管」写成了**宿主内联的单张字面量**。D4 更进一步用一张宿主内联的
 * `D4_SHEET_KEY_BY_CODE` map（`isD4DetailSheet = currentSheet in D4_SHEET_KEY_BY_CODE`）——
 * 那正是 Task 16 明文「不得照抄 D4」的写死清单。任何人往这类内联清单里加一张假 sheet，
 * 或后端 provider 增删了受管 sheet 而前端没跟上，都不会有判据报红。
 *
 * ═══ 为什么现在是「前端声明 + 后端契约测试守护一致性」而不是运行时 provider 下发 ═══
 *
 * 后端 `phase5_d3_expansion.all_managed_sheet_names()` / `all_store_item_ids()` 是受管清单的
 * **权威真源**，但它返回的是 **Excel sheet 原名**（如「预收账款明细表D3-2」），而前端全程用
 * **sheet 短码**（`D3-2`，经 `resolveD3SheetCode` 归一）。平台当前**没有**把这份受管清单
 * 以短码形态下发到前端的通路：
 *   · `workpaperSyncManifest.generated.ts` 只带 AST 抽出的 `sheet_literals`/`sheet_expressions`
 *     （D3 的表达式是 `:sheet-name="ooSheetName"`，无字面量），**不枚举受管 sheet**；
 *   · render-config / store-projection 端点均不下发「本 entry 受管哪些 sheet」的短码集合。
 *
 * ⇒ 在后端补下发字段（把受管 sheet 短码集合塞进 manifest 生成物或 render-config）之前，
 *    前端只能声明一份清单。design.md Property 12 明文给出的**可接受形态**正是二选一：
 *    「受管 sheet 集合从 provider 派生」**或**「断言前端受管判定与后端
 *    `all_managed_sheet_names()` 一致」。本模块取后者：前端集中声明一次（不再散落宿主），
 *    并由后端契约测试 `test_d3_frontend_managed_sheet_parity.py` 逐字守护它与
 *    `all_managed_sheet_names()` 一致 —— 往这里加一张假 sheet、或后端增删受管 sheet 而这里
 *    没跟上，那条守护立即报红。
 *
 * 🔴 **登记的停下报告点（改进项，不在本任务范围内实现）**：理想形态是后端把受管 sheet 的
 *    **短码集合**下发进 manifest 生成物（新增字段 `managedSheetCodes`），前端从生成物读取、
 *    彻底去掉本模块的手写清单。这需要生成器脚本 `generate_workpaper_sync_manifest.py` 增加
 *    「Excel 名 → 短码」的映射入口（该映射目前只在前端 `resolveD3SheetCode` 里），属跨前后端
 *    的下发通路建设，超出「前端接线」单任务范围，登记为后续改进。
 *
 * ═══ 🔴 两套桥不合并：rows kind vs adjudication kind ═══
 *
 * D3-2 类行表（`kind='rows'`）走 `useWorkpaperSyncBridge` + store-projection（rows kind）；
 * D3-1 审定表（`kind='adjudication'`）是逐格 mask（`AdjudicationSheetSpec` per-cell），走
 * **另一套**桥。Task 14 已明确警示：把两者并进同一个布尔会切错桥 + 工具条叠加冲突
 * （D4-35/D4-13 踩过）。故本模块派生的是「受管集合」这一个真源，但每张 sheet 带 `kind`，
 * **分派到哪套桥仍按 kind 区分**，绝不为了「消灭硬编码」把两套桥合并成一个。
 */

/** 受管 sheet 的桥类型：行表（store-projection rows）vs 审定表（逐格 mask）。 */
export type D3ManagedSheetKind = 'rows' | 'adjudication'

export interface D3ManagedSheet {
  /** 前端 sheet 短码（`resolveD3SheetCode` 归一后的形态）。 */
  readonly code: string
  /** 后端受管 sheet 的 `sheet_key`（store-projection / 契约条目主键）。 */
  readonly sheetKey: string
  /** 桥类型 —— 决定分派到 rows 桥还是 adjudication 桥，**不得**因合并集合而抹掉。 */
  readonly kind: D3ManagedSheetKind
  /** 后端 Excel sheet 原名（供后端一致性契约测试逐字比对 `all_managed_sheet_names()`）。 */
  readonly excelName: string
}

/**
 * D3 受管 sheet 单一来源清单。**逐字对齐**后端
 * `phase5_d3_expansion.all_managed_sheet_names()`（6 张）+ 各声明模块的 `SHEET_KEY_*`。
 *
 * 顺序即受管区接入顺序（D3-2 首张已接 → D3-6 → D3-4 双区 → D3-5 → D3-7 双区 → D3-1 审定表）。
 * 后端契约测试 `test_d3_frontend_managed_sheet_parity.py` 守护本清单的 `excelName` 集合 ==
 * `all_managed_sheet_names()`、且 rows 类的 `sheetKey` 集合 ⊆ 行表 spec 的 `sheet_key` 集合。
 */
export const D3_MANAGED_SHEETS: readonly D3ManagedSheet[] = Object.freeze([
  { code: 'D3-2', sheetKey: 'd32-managed', kind: 'rows', excelName: '预收账款明细表D3-2' },
  { code: 'D3-6', sheetKey: 'd36-managed', kind: 'rows', excelName: '关联关系及交易检查表D3-6' },
  { code: 'D3-4', sheetKey: 'd34-managed', kind: 'rows', excelName: '预收账款分析表D3-4' },
  { code: 'D3-5', sheetKey: 'd35-managed', kind: 'rows', excelName: '账龄1年以上的预收账款检查表D3-5' },
  { code: 'D3-7', sheetKey: 'd37-managed', kind: 'rows', excelName: '预收账款检查表D3-7' },
  { code: 'D3-1', sheetKey: 'd31-managed', kind: 'adjudication', excelName: '审定表D3-1' },
] as const)

const BY_CODE: ReadonlyMap<string, D3ManagedSheet> = new Map(
  D3_MANAGED_SHEETS.map((s) => [s.code, s]),
)

/**
 * 🔴 当前**真正接了统一双向宿主（`WorkpaperSyncEditorHost` + `useWorkpaperSyncBridge`）**的
 * 受管行表 sheet 集合。
 *
 * 诚实边界（Task 16 明文「不假装接了」）：D3 六张里受管的有 6 张，但**只有 D3-2** 在宿主
 * 里挂了 `WorkpaperSyncEditorHost`（G5-1 canary）。其余行表 D3-4/5/6/7 虽是**契约受管**
 * （store-projection 出/回两方向），却仍走结构化 `D3Tab*` 视图、**未接** OO 直写宿主；
 * D3-1 审定表走**第二套**桥且 adapter 未注册（裁决 F5）。⇒ 本集合只列真正接了 OO 直写桥的
 * sheet，随后续任务给 D3-4/5/6/7 接宿主而增长，**不**因「它们是受管 sheet」就假称可切 OO。
 */
export const D3_OO_WIRED_ROWS_CODES: readonly string[] = Object.freeze(['D3-2'])

/** 该短码是否属受管 sheet（任意 kind）。派生判定，替代宿主内联的 `=== 'D3-2'` 字面量。 */
export function isD3ManagedSheet(code: string | null | undefined): boolean {
  return code != null && BY_CODE.has(code)
}

/** 该短码是否是受管**行表**（rows kind）——分派到 rows 桥的前置。 */
export function isD3ManagedRowsSheet(code: string | null | undefined): boolean {
  const s = code == null ? undefined : BY_CODE.get(code)
  return s?.kind === 'rows'
}

/** 该短码是否是受管**审定表**（adjudication kind）——分派到第二套桥的前置。 */
export function isD3ManagedAdjudicationSheet(code: string | null | undefined): boolean {
  const s = code == null ? undefined : BY_CODE.get(code)
  return s?.kind === 'adjudication'
}

/**
 * 该短码是否**真正接了 OO 直写桥**（`WorkpaperSyncEditorHost`）。
 * 是「受管行表」且在 `D3_OO_WIRED_ROWS_CODES` 里 —— 诚实边界见该常量说明。
 */
export function isD3OoWiredRowsSheet(code: string | null | undefined): boolean {
  return isD3ManagedRowsSheet(code) && code != null && D3_OO_WIRED_ROWS_CODES.includes(code)
}

/** 取受管 sheet 声明（未受管返回 `null`）。 */
export function d3ManagedSheetOf(code: string | null | undefined): D3ManagedSheet | null {
  return code == null ? null : (BY_CODE.get(code) ?? null)
}
