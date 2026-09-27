/**
 * G2 应收利息受管 sheet 的**单一来源清单** —— 前端受管判定的唯一真源。
 *
 * spec: `g-cycle-sync-foundation-and-first-canary` · Task 15 · Requirements 4.7
 *
 * ═══ 为什么不在宿主里内联写死 ═══
 *
 * Task 15 原文要求 `isG2SyncManagedSheet` **从 provider 派生**。已落地的 5 条 F 循环 lane
 * （F1/F3/F4/F5）都在宿主里内联一张 `F*_SHEET_KEY_BY_CODE` map，注释写着「从 provider
 * 受管清单派生」而代码是宿主硬编码 —— 注释与实现对不上，没有任何判据能报红。
 * D3 是仓库里唯一把这件事做实的样本（`d3ManagedSheets.ts` + 后端 parity 契约测试），
 * 本模块照 D3 范式，不照 F 循环的内联 map。
 *
 * ═══ 为什么是「前端集中声明 + 后端契约测试守护」而不是运行时下发 ═══
 *
 * 后端 `phase5_g2_interest_receivable.all_managed_sheet_names()` 是权威真源，但它返回
 * **Excel sheet 原名**（`明细表G2-2`），而前端全程用**短码**（`G2-2`，经
 * `extractG2SheetCode` 归一）。平台当前没有把受管清单以短码形态下发前端的通路：
 *   · `workpaperSyncManifest.generated.ts` 只带 AST 抽出的 `sheetLiterals`/`sheetExpressions`
 *     （G2 的是 `:sheet-name="ooSheetName"` 表达式，无字面量），**不枚举受管 sheet**；
 *   · render-config / store-projection 端点均不下发「本 entry 受管哪些 sheet」的短码集合。
 *
 * ⇒ 取 D3 已确立的可接受形态：前端集中声明一次（不散落宿主），由后端契约测试
 *   `backend/tests/workpaper_sync/test_g2_frontend_managed_sheet_parity.py` 逐字守护本清单的
 *   `excelName` 集合 == `all_managed_sheet_names()`、`sheetKey` 集合 == 行表 spec 的
 *   `sheet_key` 集合。往这里加一张假 sheet、或后端增删受管面而这里没跟上，那条守护立即报红。
 *
 * 🔴 **登记的停下报告点**（改进项，不在本任务范围）：理想形态是生成器
 *    `generate_workpaper_sync_manifest.py` 增「Excel 名 → 短码」映射入口，把
 *    `managedSheetCodes` 下发进 manifest 生成物，前端彻底去掉手写清单。该映射目前只存在于
 *    前端各 `extractG*SheetCode`，属跨前后端下发通路建设，超出单个接线任务，与 D3 同款登记。
 *
 * ═══ 🔴 审定表 G2-1 当前**不在**受管面（裁决 GF-H5）═══
 *
 * G 循环 13 张审定表的逐格 mask 形态另立第五份 spec `g-cycle-adjudication-sheets-coverage`
 * 承载，本 spec 的 provider `adjudication_spec()` 恒 `None`。故本清单当前**只有一条**
 * `kind='rows'`，`kind` 字段保留是为了将来接入审定表时分派到**另一套**桥 —— 两套桥不合并
 * （D4-35/D4-13 踩过「并进同一个布尔切错桥 + 工具条叠加」）。
 */

/** 受管 sheet 的桥类型：行表（store-projection rows）vs 审定表（逐格 mask）。 */
export type G2ManagedSheetKind = 'rows' | 'adjudication'

export interface G2ManagedSheet {
  /** 前端 sheet 短码（`extractG2SheetCode` 归一后的形态）。 */
  readonly code: string
  /** 后端受管 sheet 的 `sheet_key`（store-projection / 契约条目主键）。 */
  readonly sheetKey: string
  /** 桥类型 —— 决定分派到 rows 桥还是 adjudication 桥，**不得**因合并集合而抹掉。 */
  readonly kind: G2ManagedSheetKind
  /** 后端 Excel sheet 原名（供后端 parity 契约测试逐字比对 `all_managed_sheet_names()`）。 */
  readonly excelName: string
}

/**
 * G2 受管 sheet 单一来源清单。**逐字对齐**后端
 * `phase5_g2_interest_receivable.all_managed_sheet_names()`（当前 1 张）
 * + `phase5_g2_02_detail.SHEET_KEY_G202`。
 */
export const G2_MANAGED_SHEETS: readonly G2ManagedSheet[] = Object.freeze([
  { code: 'G2-2', sheetKey: 'g202-managed', kind: 'rows', excelName: '明细表G2-2' },
] as const)

const BY_CODE: ReadonlyMap<string, G2ManagedSheet> = new Map(
  G2_MANAGED_SHEETS.map((s) => [s.code, s]),
)

/**
 * 🔴 当前**真正接了统一双向宿主（`WorkpaperSyncEditorHost` + `useWorkpaperSyncBridge`）**的
 * 受管行表短码。
 *
 * 诚实边界：G2 受管面 1 张、接桥 1 张 ⇒ 当前两集合相等。保留这层区分是因为 D3 实证过
 * 「契约受管 ≠ 已接 OO 直写宿主」（D3-4/5/6/7 受管但未接桥），G4/G6 lane 一册三 entry
 * 也会出现受管面先于接桥面增长的中间态 —— 届时**不得**因「它是受管 sheet」就假称可切 OO。
 */
export const G2_OO_WIRED_ROWS_CODES: readonly string[] = Object.freeze(['G2-2'])

/** 该短码是否属受管 sheet（任意 kind）。派生判定，替代宿主内联字面量。 */
export function isG2ManagedSheet(code: string | null | undefined): boolean {
  return code != null && BY_CODE.has(code)
}

/** 该短码是否是受管**行表**（rows kind）—— 分派到 rows 桥的前置。 */
export function isG2ManagedRowsSheet(code: string | null | undefined): boolean {
  const s = code == null ? undefined : BY_CODE.get(code)
  return s?.kind === 'rows'
}

/** 该短码是否是受管**审定表**（adjudication kind）—— 当前恒 false（GF-H5 后置）。 */
export function isG2ManagedAdjudicationSheet(code: string | null | undefined): boolean {
  const s = code == null ? undefined : BY_CODE.get(code)
  return s?.kind === 'adjudication'
}

/** 该短码是否**真正接了 OO 直写桥**（`WorkpaperSyncEditorHost`）。 */
export function isG2OoWiredRowsSheet(code: string | null | undefined): boolean {
  return isG2ManagedRowsSheet(code) && code != null && G2_OO_WIRED_ROWS_CODES.includes(code)
}

/** 取受管 sheet 声明（未受管返回 `null`）。 */
export function g2ManagedSheetOf(code: string | null | undefined): G2ManagedSheet | null {
  return code == null ? null : (BY_CODE.get(code) ?? null)
}

/** 受管短码 → `sheet_key`（宿主 `syncSheetKey` 派生用；未受管返回 `null`）。 */
export function g2SheetKeyOf(code: string | null | undefined): string | null {
  return g2ManagedSheetOf(code)?.sheetKey ?? null
}
