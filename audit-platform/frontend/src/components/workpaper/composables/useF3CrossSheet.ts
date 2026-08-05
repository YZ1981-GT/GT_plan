/**
 * useF3CrossSheet — F3 跨 Sheet 联动（比照 useD4CrossSheet）
 *
 * F3-2 明细 → F3-1 审定表交叉验证
 * Spec: .kiro/specs/f3-notes-payable/ Task 4.x
 *
 * 现代字段：currentIssued / currentAccepted / closingAdjusted（内存或导出）
 * 旧字段 fallback：increase / decrease / adjustedBalance / closingBalance
 *
 * 2026-07-22 复盘改进 P0-1：按票据类别动态聚合（银行/商业/供应链/其他），
 *   供应链票据不再被审定表/附注丢弃；审定表↔明细表口径一致。
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { calcSubtotal, calcCreditBalance, calcAuditedAmount, parseNum } from './useF3FormulaEngine'
import type { ChecklistResponse, ProjectContext } from './useF3FormData'

export interface UseF3CrossSheetOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  projectContext: Ref<ProjectContext>
}

/** F3-2 行（现代 + 遗留字段均可） */
export interface F3DetailRowRaw {
  noteType?: string
  openingBalance?: number
  currentIssued?: number
  currentAccepted?: number
  aje?: number
  rje?: number
  /** 若导出/旧数据已带审定数 */
  closingAdjusted?: number
  closingUnadjusted?: number
  /** 遗留 */
  adjustedBalance?: number
  closingBalance?: number
  increase?: number
  decrease?: number
  currentIncrease?: number
  currentDecrease?: number
  endBalance?: number
  depositAmount?: number
}

/** 票据类别 → 审定/附注分类键（单一真源，供 F3-1 审定表与附注共用） */
export type F3CategoryKey = 'bank' | 'commercial' | 'letter_of_credit' | 'supplychain' | 'other'

export const F3_CATEGORY_META: ReadonlyArray<{ rowKey: F3CategoryKey; label: string; keyword: string }> = [
  { rowKey: 'bank', label: '银行承兑汇票', keyword: '银行' },
  { rowKey: 'commercial', label: '商业承兑汇票', keyword: '商业' },
  { rowKey: 'letter_of_credit', label: '信用证', keyword: '信用证' },
  { rowKey: 'supplychain', label: '供应链票据', keyword: '供应链' },
  { rowKey: 'other', label: '其他', keyword: '' },
]

/** 按票据类别归类：银行/商业/信用证/供应链关键字匹配，其余归"其他"。 */
export function rowCategoryKey(r: F3DetailRowRaw): F3CategoryKey {
  const t = String(r.noteType || '')
  if (t.includes('银行')) return 'bank'
  if (t.includes('商业')) return 'commercial'
  if (t.includes('信用证')) return 'letter_of_credit'
  if (t.includes('供应链')) return 'supplychain'
  return 'other'
}

function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/** 本期开票（贷方发生） */
export function rowPeriodCredit(r: F3DetailRowRaw): number {
  return parseNum(r.currentIssued ?? r.increase ?? r.currentIncrease)
}

/** 本期承兑/兑付（借方发生） */
export function rowPeriodDebit(r: F3DetailRowRaw): number {
  return parseNum(r.currentAccepted ?? r.decrease ?? r.currentDecrease)
}

/** 期末审定数：优先显式字段，否则按公式重算 */
export function rowClosingAdjusted(r: F3DetailRowRaw): number {
  if (r.closingAdjusted != null) return parseNum(r.closingAdjusted)
  if (r.adjustedBalance != null) return parseNum(r.adjustedBalance)
  if (r.endBalance != null && r.aje == null && r.rje == null) {
    return parseNum(r.endBalance)
  }
  const opening = parseNum(r.openingBalance)
  const issued = rowPeriodCredit(r)
  const accepted = rowPeriodDebit(r)
  const closingUnaud = r.closingUnadjusted != null
    ? parseNum(r.closingUnadjusted)
    : (r.closingBalance != null
      ? parseNum(r.closingBalance)
      : calcCreditBalance(opening, issued, accepted))
  return calcAuditedAmount(closingUnaud, parseNum(r.aje), parseNum(r.rje))
}

export interface F3CategoryAgg {
  periodCredit: number
  periodDebit: number
  closingAdjusted: number
  count: number
}

function emptyAgg(): F3CategoryAgg {
  return { periodCredit: 0, periodDebit: 0, closingAdjusted: 0, count: 0 }
}

/** 按票据类别聚合明细行（纯函数，供审定表 cross-sheet 与附注共用）。 */
export function aggregateDetailByCategory(
  rows: F3DetailRowRaw[],
): Record<F3CategoryKey, F3CategoryAgg> {
  const acc: Record<F3CategoryKey, F3CategoryAgg> = {
    bank: emptyAgg(),
    commercial: emptyAgg(),
    supplychain: emptyAgg(),
    other: emptyAgg(),
  }
  for (const r of rows) {
    const k = rowCategoryKey(r)
    acc[k].periodCredit += rowPeriodCredit(r)
    acc[k].periodDebit += rowPeriodDebit(r)
    acc[k].closingAdjusted += rowClosingAdjusted(r)
    acc[k].count += 1
  }
  return acc
}

/** 附注/审定表分类行（供上市/国企附注共用） */
export interface F3ClassRow {
  rowKey: F3CategoryKey
  label: string
  endAmount: number
  priorAmount: number
}

function parseOpeningAdjusted(stored: any): number {
  return calcAuditedAmount(
    parseNum(stored.openingUnadjusted),
    parseNum(stored.openingAje),
    parseNum(stored.openingRje),
  )
}

/**
 * 由 F3-1 审定表（期初审定 + 期末 AJE/RJE）与 F3-2 明细（本期开票/兑付按类别）
 * 组装附注分类行；期末数 = 期初审定 + 本期贷方 − 本期借方 + 期末 AJE + RJE。
 * 银行/商业承兑始终列示；供应链/其他仅在存在金额或明细时列示。
 */
export function buildF3DisclosureClassRows(
  adjRaw: string | null | undefined,
  detailRaw: string | null | undefined,
): F3ClassRow[] {
  const stored = safeParseRows<any>(adjRaw)
  const detailRows = safeParseRows<F3DetailRowRaw>(detailRaw)
  const agg = aggregateDetailByCategory(detailRows)
  const storedByKey = new Map<string, any>()
  for (const s of stored) storedByKey.set(String(s.rowKey), s)

  const out: F3ClassRow[] = []
  for (const meta of F3_CATEGORY_META) {
    const s = storedByKey.get(meta.rowKey)
    const openingAdjusted = s ? parseOpeningAdjusted(s) : 0
    const closingAje = s ? parseNum(s.closingAje) : 0
    const closingRje = s ? parseNum(s.closingRje) : 0
    const catAgg = agg[meta.rowKey]
    // 有明细时以明细本期发生驱动；否则退化为期初审定（与旧行为一致）
    const closingUnadj = catAgg.count > 0
      ? calcCreditBalance(openingAdjusted, catAgg.periodCredit, catAgg.periodDebit)
      : openingAdjusted
    const endAmount = calcAuditedAmount(closingUnadj, closingAje, closingRje)
    const priorAmount = openingAdjusted
    const alwaysShow = meta.rowKey === 'bank' || meta.rowKey === 'commercial'
    if (alwaysShow || endAmount !== 0 || priorAmount !== 0 || catAgg.count > 0) {
      out.push({ rowKey: meta.rowKey, label: meta.label, endAmount, priorAmount })
    }
  }
  return out
}

export function useF3CrossSheet(options: UseF3CrossSheetOptions) {
  const { allResponses } = options

  const detailRows: ComputedRef<F3DetailRowRaw[]> = computed(() => {
    const resp = allResponses.value.get('F3-2-rows')
    return safeParseRows<F3DetailRowRaw>(resp?.remark)
  })

  const hasDetailData = computed(() => detailRows.value.length > 0)

  const categoryAgg = computed(() => aggregateDetailByCategory(detailRows.value))

  const detailGrandTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(detailRows.value.map(rowClosingAdjusted)),
  )

  /** 保证金合计（P1-6：受限货币资金联动 E1） */
  const detailDepositTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(detailRows.value.map((r) => parseNum(r.depositAmount))),
  )

  function periodCreditByKey(key: F3CategoryKey): number {
    return categoryAgg.value[key].periodCredit
  }
  function periodDebitByKey(key: F3CategoryKey): number {
    return categoryAgg.value[key].periodDebit
  }
  function detailTotalByKey(key: F3CategoryKey): number {
    return categoryAgg.value[key].closingAdjusted
  }
  function hasCategory(key: F3CategoryKey): boolean {
    return categoryAgg.value[key].count > 0
  }

  // ── 向后兼容的具名 computed（银行/商业） ──
  const detailBankTotal = computed(() => detailTotalByKey('bank'))
  const detailCommercialTotal = computed(() => detailTotalByKey('commercial'))
  const detailSupplyChainTotal = computed(() => detailTotalByKey('supplychain'))
  const detailOtherTotal = computed(() => detailTotalByKey('other'))
  const bankPeriodCredit = computed(() => periodCreditByKey('bank'))
  const bankPeriodDebit = computed(() => periodDebitByKey('bank'))
  const commercialPeriodCredit = computed(() => periodCreditByKey('commercial'))
  const commercialPeriodDebit = computed(() => periodDebitByKey('commercial'))
  const supplyChainPeriodCredit = computed(() => periodCreditByKey('supplychain'))
  const supplyChainPeriodDebit = computed(() => periodDebitByKey('supplychain'))
  const otherPeriodCredit = computed(() => periodCreditByKey('other'))
  const otherPeriodDebit = computed(() => periodDebitByKey('other'))

  /** 明细中出现的分类键（供审定表动态补行判断） */
  const activeCategoryKeys = computed<F3CategoryKey[]>(() =>
    (['bank', 'commercial', 'supplychain', 'other'] as F3CategoryKey[]).filter((k) => hasCategory(k)),
  )

  return {
    detailRows,
    hasDetailData,
    categoryAgg,
    detailGrandTotal,
    detailDepositTotal,
    periodCreditByKey,
    periodDebitByKey,
    detailTotalByKey,
    hasCategory,
    activeCategoryKeys,
    // 向后兼容
    detailBankTotal,
    detailCommercialTotal,
    detailSupplyChainTotal,
    detailOtherTotal,
    bankPeriodCredit,
    bankPeriodDebit,
    commercialPeriodCredit,
    commercialPeriodDebit,
    supplyChainPeriodCredit,
    supplyChainPeriodDebit,
    otherPeriodCredit,
    otherPeriodDebit,
  }
}

export default useF3CrossSheet
