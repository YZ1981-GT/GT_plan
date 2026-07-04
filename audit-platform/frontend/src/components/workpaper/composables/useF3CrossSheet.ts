/**
 * useF3CrossSheet — F3 跨 Sheet 联动（比照 useD4CrossSheet）
 *
 * F3-2 明细 → F3-1 审定表交叉验证
 * Spec: .kiro/specs/f3-notes-payable/ Task 4.x
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { calcSubtotal, parseNum } from './useF3FormulaEngine'
import type { ChecklistResponse, ProjectContext } from './useF3FormData'

export interface UseF3CrossSheetOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  projectContext: Ref<ProjectContext>
}

interface F3DetailRowRaw {
  noteType?: string
  adjustedBalance?: number
  closingBalance?: number
  increase?: number
  decrease?: number
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

function sumByNoteType(rows: F3DetailRowRaw[], typeKeyword: string, field: keyof F3DetailRowRaw): number {
  return calcSubtotal(filterByNoteType(rows, typeKeyword).map((r) => parseNum(r[field] as number)))
}

export function useF3CrossSheet(options: UseF3CrossSheetOptions) {
  const { allResponses } = options

  const detailRows: ComputedRef<F3DetailRowRaw[]> = computed(() => {
    const resp = allResponses.value.get('F3-2-rows')
    return safeParseRows<F3DetailRowRaw>(resp?.remark)
  })

  const hasDetailData = computed(() => detailRows.value.length > 0)

  const detailBankTotal: ComputedRef<number> = computed(() =>
    sumByNoteType(detailRows.value, '银行', 'adjustedBalance'),
  )

  const detailCommercialTotal: ComputedRef<number> = computed(() =>
    sumByNoteType(detailRows.value, '商业', 'adjustedBalance'),
  )

  const detailGrandTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(detailRows.value.map((r) => parseNum(r.adjustedBalance ?? r.closingBalance))),
  )

  const bankPeriodCredit = computed(() => sumByNoteType(detailRows.value, '银行', 'increase'))
  const bankPeriodDebit = computed(() => sumByNoteType(detailRows.value, '银行', 'decrease'))
  const commercialPeriodCredit = computed(() => sumByNoteType(detailRows.value, '商业', 'increase'))
  const commercialPeriodDebit = computed(() => sumByNoteType(detailRows.value, '商业', 'decrease'))

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
