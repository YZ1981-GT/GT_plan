/**
 * H 循环（固定资产）受管 sheet 的**单一来源清单** —— 前端受管判定的唯一真源。
 *
 * spec: `h-cycle-sync-foundation-and-first-canary` · Requirements 4.x（HC-1 现算口径）
 *
 * ═══ 为什么是一份跨 9 entry 的清单，而不是每个宿主内联一张 map ═══════════════
 *
 * F 循环 5 条 lane 各在宿主里内联 `F*_SHEET_KEY_BY_CODE`，注释写「从 provider 受管清单
 * 派生」而代码是宿主硬编码 —— 注释与实现对不上，没有任何判据能报红。D3/G2 把这件事做实
 * （集中声明 + 后端 parity 契约测试），本模块照 D3/G2 范式。
 *
 * H 比 D3/G2 更需要集中：**9 条独立 entry + 5 条子入口**，若照 F 的内联做法就是 9~14 份
 * 拷贝。集中一份后，`useHSyncMode` 只认本清单，新增 entry 只改这里一行。
 *
 * ═══ 🔴 诚实边界：受管面 ≠ 已接桥面 ═══════════════════════════════════════════
 *
 * D3 实证过「契约受管 ≠ 已接 OO 直写宿主」（D3-4/5/6/7 受管但未接桥）。H 当前的真实状态：
 *   · 后端 provider **只有 H9**（`phase5_h9_lease_liabilities` / `h9.lease_liability_detail`）
 *     —— H2/H3/H4/H5/H6/H7/H8/H10 八条 lane 的 provider 尚未落地；
 *   · H1 是**同循环既有 pilot**（`pilot_h1_grouped_dynamic`），走 `pilot_*` 范式、
 *     adapter 已注册，**不属本轮受管面**，故不进本清单（避免把两套范式并进同一个布尔，
 *     D4-35/D4-13 踩过「切错桥 + 工具条叠加」）。
 * ⇒ 本清单当前 1 条。**不得**因「H 循环有 9 条 entry」就预先声明 9 条：那会让
 *   `isHOoWiredRowsSheet` 对未接桥的 sheet 返 true，宿主据此渲染
 *   `WorkpaperSyncEditorHost` 而后端没有 adapter，用户点「在线编辑」直接失败。
 *
 * ═══ 后端守护 ═══════════════════════════════════════════════════════════════
 *
 * `backend/tests/workpaper_sync/test_h_frontend_managed_sheet_parity.py` 逐字守护：
 *   · 本清单 `excelName` 集合 == 各 provider `all_managed_sheet_names()` 之并
 *   · 本清单 `sheetKey` 集合 == 各 provider 行表 spec 的 `sheet_key` 集合
 *   · 本清单 `storeItemId` 集合 == `store_item_registry` 里对应 plan 的 item_id 集合
 * 往这里加一张假 sheet、或后端增删受管面而这里没跟上，那条守护立即报红。
 *
 * 🔴 登记的停下报告点（同 D3/G2，不在本任务范围）：理想形态是生成器
 *    `generate_workpaper_sync_manifest.py` 把「Excel 名 → 前端短码」映射下发进
 *    `workpaperSyncManifest.generated.ts`，前端彻底去掉手写清单。该映射目前只存在于
 *    前端各 `extractH*SheetCode`，属跨前后端下发通路建设，超出单个接线任务。
 */

/** 受管 sheet 的桥类型：行表（store-projection rows）vs 审定表（逐格 mask）。 */
export type HManagedSheetKind = 'rows' | 'adjudication'

export interface HManagedSheet {
  /** 所属 entry id（manifest 冻结值）。 */
  readonly entryId: string
  /** 前端 sheet 短码（各宿主 `currentSheet` 归一后的形态）。 */
  readonly code: string
  /** 后端受管 sheet 的 `sheet_key`（store-projection / 契约条目主键）。 */
  readonly sheetKey: string
  /** 桥类型 —— 决定分派到 rows 桥还是 adjudication 桥，**不得**因合并集合而抹掉。 */
  readonly kind: HManagedSheetKind
  /** 后端 Excel sheet 原名（供后端 parity 契约测试逐字比对）。 */
  readonly excelName: string
  /** store item id（checklist 键）—— 供 parity 守护比对 registry。 */
  readonly storeItemId: string
}

/**
 * H 循环受管 sheet 单一来源清单。
 *
 * **逐字对齐**后端：
 *   · `phase5_h9_lease_liabilities.ENTRY_ID` / `all_managed_sheet_names()`
 *   · `phase5_h9_02_detail.SHEET_KEY_H902` / `STORE_ITEM_ID_H902`
 */
export const H_MANAGED_SHEETS: readonly HManagedSheet[] = Object.freeze([
  {
    entryId: 'xlsx/gt-h9-lease-liabilities',
    code: 'H9-2',
    sheetKey: 'h902-managed',
    kind: 'rows',
    excelName: '租赁负债明细表H9-2',
    storeItemId: 'H9-2-rows',
  },
  {
    // H 循环**发布链首例**（审定数经 useH6Adjudication.publishToTb 走显式发布门）。
    // 🔴 excelName 是 `明细表H6-2` —— 不带科目前缀（H9 的是 `租赁负债明细表H9-2`），
    //    逐字取模板 sheet 名，不按 H9 的构词法推演。
    entryId: 'xlsx/gt-h6-asset-disposal-clearing',
    code: 'H6-2',
    sheetKey: 'h602-managed',
    kind: 'rows',
    excelName: '明细表H6-2',
    storeItemId: 'H6-2-rows',
  },
  {
    // 🔴 **受管但尚未接桥** —— 本条刻意只进 `H_MANAGED_SHEETS`，不进
    //    `H_OO_WIRED_ROWS_CODES`。这正是这两个集合分开存在的理由：后端契约已交付
    //    （四级表头 / 49 列 / 三区块），但宿主接桥是独立一步（H4 载体是
    //    `formdata_composable`，flush 钩子要取 composable 的导出而非宿主内联函数）。
    //    在接桥完成前声明「已接桥」会让用户点「在线编辑」时渲染 EditorHost 而桥未就绪。
    entryId: 'xlsx/gt-h4-engineering-materials',
    code: 'H4-2',
    sheetKey: 'h402-managed',
    kind: 'rows',
    excelName: '明细表H4-2',
    storeItemId: 'H4-2-rows',
  },
] as const)

/**
 * 当前**真正接了统一双向宿主（`WorkpaperSyncEditorHost` + `useWorkpaperSyncBridge`）**
 * 的受管行表短码。
 *
 * 当前受管 1 张、接桥 1 张 ⇒ 两集合相等。保留这层区分是因为受管面会先于接桥面增长
 * （8 条 lane provider 落地时先进 `H_MANAGED_SHEETS`，宿主接桥另做）—— 届时**不得**
 * 因「它是受管 sheet」就假称可切 OO。
 */
export const H_OO_WIRED_ROWS_CODES: readonly string[] = Object.freeze(['H9-2', 'H6-2'])

const BY_CODE: ReadonlyMap<string, HManagedSheet> = (() => {
  const m = new Map<string, HManagedSheet>()
  for (const s of H_MANAGED_SHEETS) {
    // H 的 sheet 短码全循环唯一（H2-2 / H9-2 …）。真撞码说明清单写错了，
    // 静默覆盖会让某条 entry 的 sheetKey 被另一条顶掉 —— 当场抛，不留隐患。
    if (m.has(s.code)) {
      throw new Error(`H_MANAGED_SHEETS 短码重复：${s.code}（${m.get(s.code)!.entryId} vs ${s.entryId}）`)
    }
    m.set(s.code, s)
  }
  return m
})()

/** 该短码是否属受管 sheet（任意 kind）。派生判定，替代宿主内联字面量。 */
export function isHManagedSheet(code: string | null | undefined): boolean {
  return code != null && BY_CODE.has(code)
}

/** 该短码是否是受管**行表**（rows kind）—— 分派到 rows 桥的前置。 */
export function isHManagedRowsSheet(code: string | null | undefined): boolean {
  const s = code == null ? undefined : BY_CODE.get(code)
  return s?.kind === 'rows'
}

/** 该短码是否**真正接了 OO 直写桥**（`WorkpaperSyncEditorHost`）。 */
export function isHOoWiredRowsSheet(code: string | null | undefined): boolean {
  return isHManagedRowsSheet(code) && code != null && H_OO_WIRED_ROWS_CODES.includes(code)
}

/** 取受管 sheet 声明（未受管返回 `null`）。 */
export function hManagedSheetOf(code: string | null | undefined): HManagedSheet | null {
  return code == null ? null : (BY_CODE.get(code) ?? null)
}

/** 受管短码 → `sheet_key`（宿主 `syncSheetKey` 派生用；未受管返回 `null`）。 */
export function hSheetKeyOf(code: string | null | undefined): string | null {
  return hManagedSheetOf(code)?.sheetKey ?? null
}

/** 受管短码 → `entryId`（宿主建桥用；未受管返回 `null`）。 */
export function hEntryIdOf(code: string | null | undefined): string | null {
  return hManagedSheetOf(code)?.entryId ?? null
}

/** 某 entry 下的全部受管短码（宿主按 entry 收窄判定用）。 */
export function hManagedCodesOfEntry(entryId: string): readonly string[] {
  return H_MANAGED_SHEETS.filter((s) => s.entryId === entryId).map((s) => s.code)
}
