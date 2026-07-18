/**
 * useF3CrossSheet — F3 跨 Sheet 联动（比照 useD4CrossSheet）
 *
 * F3-2 明细 → F3-1 审定表交叉验证
 * Spec: .kiro/specs/f3-notes-payable/ Task 4.x
 *
 * 现代字段：currentIssued / currentAccepted / closingAdjusted（内存或导出）
 * 旧字段 fallback：increase / decrease / adjustedBalance / closingBalance
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

function filterByNoteType(rows: F3DetailRowRaw[], typeKeyword: string): F3DetailRowRaw[] {
  return rows.filter((r) => (r.noteType || '').includes(typeKeyword))
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

function sumByNoteType(
  rows: F3DetailRowRaw[],
  typeKeyword: string,
  picker: (r: F3DetailRowRaw) => number,
): number {
  return calcSubtotal(filterByNoteType(rows, typeKeyword).map(picker))
}

export function useF3CrossSheet(options: UseF3CrossSheetOptions) {
  const { allResponses } = options

  const detailRows: ComputedRef<F3DetailRowRaw[]> = computed(() => {
    const resp = allResponses.value.get('F3-2-rows')
    return safeParseRows<F3DetailRowRaw>(resp?.remark)
  })

  const hasDetailData = computed(() => detailRows.value.length > 0)

  const detailBankTotal: ComputedRef<number> = computed(() =>
    sumByNoteType(detailRows.value, '银行', rowClosingAdjusted),
  )

  const detailCommercialTotal: ComputedRef<number> = computed(() =>
    sumByNoteType(detailRows.value, '商业', rowClosingAdjusted),
  )

  const detailGrandTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(detailRows.value.map(rowClosingAdjusted)),
  )

  const bankPeriodCredit = computed(() => sumByNoteType(detailRows.value, '银行', rowPeriodCredit))
  const bankPeriodDebit = computed(() => sumByNoteType(detailRows.value, '银行', rowPeriodDebit))
  const commercialPeriodCredit = computed(() => sumByNoteType(detailRows.value, '商业', rowPeriodCredit))
  const commercialPeriodDebit = computed(() => sumByNoteType(detailRows.value, '商业', rowPeriodDebit))

  return {
    detailRows,
    hasDetailData,
    detailBankTotal,
    detailCommercialTotal,
    detailGrandTotal,
    bankPeriodCredit,
    bankPeriodDebit,
    commercialPeriodCredit,
    commercialPeriodDebit,
  }
}

export default useF3CrossSheet
