/**
 * G 循环九条 single-region lane 的受管 sheet 清单 —— 前端受管判定的单一来源。
 *
 * spec: `g-cycle-single-region-detail-lanes` · Task 15 · Requirements 4.7
 *
 * 九条 lane 各只有一个受管 sheet（明细表），模式完全相同。
 * 后端 parity 契约测试守护本清单与各 provider `all_managed_sheet_names()` 一致。
 */

export interface GSingleRegionManagedSheet {
  /** 前端 sheet 短码 */
  readonly code: string
  /** 后端 `sheet_key` */
  readonly sheetKey: string
  /** 后端 Excel sheet 原名 */
  readonly excelName: string
  /** 对应的 entry_id */
  readonly entryId: string
}

/**
 * 九条 lane 的受管 sheet 清单。逐字对齐各 provider 的 `all_managed_sheet_names()` +
 * sheet spec 的 `sheet_key`。
 */
export const G_SINGLE_REGION_MANAGED_SHEETS: readonly GSingleRegionManagedSheet[] = Object.freeze([
  { code: 'G1-2', sheetKey: 'g102-managed', excelName: '明细表G1-2', entryId: 'xlsx/gt-g1-trading-financial-assets' },
  { code: 'G3-2', sheetKey: 'g302-managed', excelName: '明细表G3-2', entryId: 'xlsx/gt-g3-dividend-receivable' },
  { code: 'G5-2', sheetKey: 'g502-managed', excelName: '余额明细表G5-2', entryId: 'xlsx/gt-g5-long-term-receivable' },
  { code: 'G8-2', sheetKey: 'g802-managed', excelName: '明细表G8-2', entryId: 'xlsx/gt-g8-other-equity-instruments' },
  { code: 'G9-2', sheetKey: 'g902-managed', excelName: '明细表G9-2', entryId: 'xlsx/gt-g9-other-noncurrent-financial' },
  { code: 'G10-2', sheetKey: 'g1002-managed', excelName: '明细表G10-2', entryId: 'xlsx/gt-g10-trading-financial-liabilities' },
  { code: 'G11-2', sheetKey: 'g1102-managed', excelName: '明细分析表G11-2', entryId: 'xlsx/gt-g11-investment-income' },
  { code: 'G12-2', sheetKey: 'g1202-managed', excelName: '明细表G12-2', entryId: 'xlsx/gt-g12-net-hedge-gains' },
  { code: 'G13-2', sheetKey: 'g1302-managed', excelName: '明细表G13-2', entryId: 'xlsx/gt-g13-fair-value-changes' },
  { code: 'G14-2', sheetKey: 'g1402-managed', excelName: '明细表G14-2', entryId: 'xlsx/gt-g14-credit-impairment-loss' },
] as const)

const BY_CODE: ReadonlyMap<string, GSingleRegionManagedSheet> = new Map(
  G_SINGLE_REGION_MANAGED_SHEETS.map((s) => [s.code, s]),
)

const BY_ENTRY: ReadonlyMap<string, GSingleRegionManagedSheet> = new Map(
  G_SINGLE_REGION_MANAGED_SHEETS.map((s) => [s.entryId, s]),
)

/** 该短码是否是九条 lane 之一的受管 sheet。 */
export function isGSingleRegionManagedSheet(code: string | null | undefined): boolean {
  return code != null && BY_CODE.has(code)
}

/** 短码 → sheet_key（未受管返回 null）。 */
export function gSingleRegionSheetKeyOf(code: string | null | undefined): string | null {
  return code == null ? null : (BY_CODE.get(code)?.sheetKey ?? null)
}

/** 短码 → entry_id（未受管返回 null）。 */
export function gSingleRegionEntryIdOf(code: string | null | undefined): string | null {
  return code == null ? null : (BY_CODE.get(code)?.entryId ?? null)
}

/** entry_id → 受管 sheet 声明（未匹配返回 null）。 */
export function gSingleRegionSheetByEntry(entryId: string | null | undefined): GSingleRegionManagedSheet | null {
  return entryId == null ? null : (BY_ENTRY.get(entryId) ?? null)
}
