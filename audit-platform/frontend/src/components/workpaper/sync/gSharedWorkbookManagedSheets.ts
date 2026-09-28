/**
 * G4 / G6 共享工作簿 lane 的受管 sheet 清单 —— 前端受管判定的单一来源。
 *
 * spec: `g4-g6-shared-workbook-three-entry-lanes`
 *
 * ═══ 为什么不能并进 `gSingleRegionManagedSheets` ═══════════════════════════
 *
 * 那个模块按**前端短码**（`G1-2` / `G13-2` …）建单键 map。G4/G6 的宿主 `currentSheet`
 * 返回的**不是短码而是语义名**（`SHEET_CODE_MAP` 映射后的 `securitiesInventory` /
 * `fairValueTest` / `detail` …），而且两个 SPPI 宿主的语义名集合**有交集**：
 *
 *   · `GtG4BondInvestmentSppi` → businessModel / sppiTest / **securitiesInventory** / inventoryReconciliation
 *   · `GtG6OtherBondSppi`      → fairValueTest / interestCalculation / businessModel / sppiTest / **securitiesInventory** / inventoryRollForward
 *
 * ⇒ 按语义名做全局单键 map 会让 G4 的 `securitiesInventory` 和 G6 的同名 sheet 串台，
 *   桥会拿错 entry 的 sheet_key 去 materialize。故本模块按 **(entryId, 语义名) 二元组**
 *   判定，与「两套桥不合并」（D4-35/D4-13 踩过切错桥）同一条原则。
 *
 * ═══ 🔴 一册三 entry：受管 sheet 在 SPPI 宿主，entry 身份归 main ═════════════
 *
 * 后端 `phase5_g4_bond_investment.py` 的 `ENTRY_ID` 是 `xlsx/gt-g4-bond-investment-main`
 * （文件头：「一册三 entry（G4-main / G4-sppi / G4-ecl），共用同一个 `TEMPLATE_SHA256`，
 * pointer 靠 `entry_id` 区分，matcher 用 `sheet_keys` 互斥（裁决 G46-H2）」），而它
 * 唯一的受管行表 spec 是 `phase5_g4_07_sppi_inventory.SPEC_G407`
 * （`有价证券盘点表G4-7`，`sheet_key='g407-managed'`）——**那张表由 SPPI 宿主渲染**
 * （G4-SPPI 的 `currentSheet` 正则是 `G4-([5-8])`，G4-7 落在它身上）。
 *
 * ⇒ SPPI 宿主接桥时 `entryId` 必须用 **main 的 entry_id**，不是它自己那个
 *   `xlsx/gt-g4-bond-investment-sppi`。用自己的 entry 会让桥去查一个没有受管 sheet、
 *   没有契约、`adapter_id=null` 的 entry。G6 同理。
 *
 * ⇒ 另外三个宿主（G4-main / G4-ecl / G6-main）当前**没有受管 sheet**：
 *   main 册的受管面只有 G4-7 / G6-5 这一张，ECL 那条 entry 连契约都还没交付
 *   （`delivered_contracts_ledger` 里 G4 只有 `g4.bond_main`、G6 只有 `g6.other_bond_main`）。
 *   它们接同一个切换器但受管判定恒 `false` ⇒ 切「在线编辑」走 legacy 只读视图，
 *   **不会**出现「挂了同步编辑器却永远停在『正在打开…』」那种空壳。
 */

export interface GSharedWorkbookManagedSheet {
  /** 宿主 `currentSheet` 返回的**语义名**（不是短码）。 */
  readonly semanticName: string
  /** 后端 `sheet_key`（逐字对齐 sheet spec）。 */
  readonly sheetKey: string
  /** 后端 Excel sheet 原名（供后端 parity 判据逐字比对）。 */
  readonly excelName: string
  /**
   * 桥要用的 entry_id —— **共享册的 main entry**，不是渲染它的宿主自己那个 entry。
   * 与后端 `phase5_g{4,6}_*.ENTRY_ID` 逐字一致。
   */
  readonly bridgeEntryId: string
  /** 渲染这张表的宿主自己的 entry_id（仅作对照，**不**拿去建桥）。 */
  readonly hostEntryId: string
}

/**
 * G4/G6 共享册当前受管的 sheet。逐字对齐
 * `phase5_g4_07_sppi_inventory.SPEC_G407` / `phase5_g6_05_sppi_fair_value.SPEC_G605`。
 */
export const G_SHARED_WORKBOOK_MANAGED_SHEETS: readonly GSharedWorkbookManagedSheet[] =
  Object.freeze([
    {
      semanticName: 'securitiesInventory',
      sheetKey: 'g407-managed',
      excelName: '有价证券盘点表G4-7',
      bridgeEntryId: 'xlsx/gt-g4-bond-investment-main',
      hostEntryId: 'xlsx/gt-g4-bond-investment-sppi',
    },
    {
      semanticName: 'fairValueTest',
      sheetKey: 'g605-managed',
      excelName: '公允价值测试表G6-5',
      bridgeEntryId: 'xlsx/gt-g6-other-bond-main',
      hostEntryId: 'xlsx/gt-g6-other-bond-sppi',
    },
  ] as const)

/** `${hostEntryId}\u0000${semanticName}` → 声明。 */
const BY_HOST_AND_SHEET: ReadonlyMap<string, GSharedWorkbookManagedSheet> = new Map(
  G_SHARED_WORKBOOK_MANAGED_SHEETS.map((s) => [`${s.hostEntryId}\u0000${s.semanticName}`, s]),
)

/**
 * 取该宿主在该语义 sheet 上的受管声明（未受管返回 `null`）。
 *
 * 🔴 必须同时给 `hostEntryId` 与 `semanticName` —— 只给语义名会让两个 SPPI 宿主的
 * `securitiesInventory` 串台（见文件头）。
 */
export function gSharedWorkbookSheetOf(
  hostEntryId: string,
  semanticName: string | null | undefined,
): GSharedWorkbookManagedSheet | null {
  if (semanticName == null) return null
  return BY_HOST_AND_SHEET.get(`${hostEntryId}\u0000${semanticName}`) ?? null
}

/** 该宿主的该语义 sheet 是否受管。 */
export function isGSharedWorkbookManagedSheet(
  hostEntryId: string,
  semanticName: string | null | undefined,
): boolean {
  return gSharedWorkbookSheetOf(hostEntryId, semanticName) !== null
}
