/**
 * usePeriodAdjudication — 通用期初/期末审定表（借方/贷方科目）
 */
import { ref, computed, type Ref } from 'vue'
import { parseNum, calcAuditedAmount, calcSubtotal } from '../composables/useG1TraFinFormulaEngine'
import type { ChecklistResponse } from '../composables/useF1FormData'
import type { CycleAdjudicationConfig } from './cycleAdjudicationConfigs'

export interface PeriodAdjudicationRow {
  rowKey: string
  label: string
  priorAudited: number
  periodDebit: number
  periodCredit: number
  closingUnadjusted: number
  closingAje: number
  closingRje: number
  closingAudited: number
}

function cellId(sheetCode: string, rowKey: string, field: string): string {
  return `${sheetCode}-${rowKey}-${field}`
}

function loadNum(map: Map<string, ChecklistResponse>, id: string): number {
  return parseNum(map.get(id)?.conclusion)
}

function calcClosingUnadjusted(
  priorAudited: number,
  debit: number,
  credit: number,
  direction: 'debit' | 'credit',
): number {
  return direction === 'debit' ? priorAudited + debit - credit : priorAudited + credit - debit
}

function buildRows(
  config: CycleAdjudicationConfig,
  map: Map<string, ChecklistResponse>,
): PeriodAdjudicationRow[] {
  return config.rows.map((r) => {
    const priorAudited = loadNum(map, cellId(config.sheetCode, r.rowKey, 'prior-audited'))
    const periodDebit = loadNum(map, cellId(config.sheetCode, r.rowKey, 'debit'))
    const periodCredit = loadNum(map, cellId(config.sheetCode, r.rowKey, 'credit'))
    const closingAje = loadNum(map, cellId(config.sheetCode, r.rowKey, 'aje'))
    const closingRje = loadNum(map, cellId(config.sheetCode, r.rowKey, 'rje'))
    const closingUnadjusted = calcClosingUnadjusted(
      priorAudited,
      periodDebit,
      periodCredit,
      config.direction,
    )
    const closingAudited = calcAuditedAmount(closingUnadjusted, closingAje, closingRje)
    return {
      rowKey: r.rowKey,
      label: r.label,
      priorAudited,
      periodDebit,
      periodCredit,
      closingUnadjusted,
      closingAje,
      closingRje,
      closingAudited,
    }
  })
}

function subtotal(rows: PeriodAdjudicationRow[]): PeriodAdjudicationRow {
  return {
    rowKey: 'subtotal',
    label: '合计',
    priorAudited: calcSubtotal(rows.map((r) => r.priorAudited)),
    periodDebit: calcSubtotal(rows.map((r) => r.periodDebit)),
    periodCredit: calcSubtotal(rows.map((r) => r.periodCredit)),
    closingUnadjusted: calcSubtotal(rows.map((r) => r.closingUnadjusted)),
    closingAje: calcSubtotal(rows.map((r) => r.closingAje)),
    closingRje: calcSubtotal(rows.map((r) => r.closingRje)),
    closingAudited: calcSubtotal(rows.map((r) => r.closingAudited)),
  }
}

export function usePeriodAdjudication(opts: {
  config: Ref<CycleAdjudicationConfig>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const auditNote = ref('')
  const conclusion = ref('')
  const trialBalanceAmount = ref(0)

  const rows = computed(() => buildRows(opts.config.value, opts.allResponses.value))
  const totalRow = computed(() => subtotal(rows.value))
  const trialBalanceDiff = computed(() => totalRow.value.closingAudited - trialBalanceAmount.value)

  const debitLabel = computed(() => (opts.config.value.direction === 'debit' ? '借方发生' : '借方发生'))
  const creditLabel = computed(() => (opts.config.value.direction === 'credit' ? '贷方发生' : '贷方发生'))

  function updateField(rowKey: string, field: string, value: number) {
    if (opts.isReadonly.value) return
    opts.debouncedSave(cellId(opts.config.value.sheetCode, rowKey, field), {
      conclusion: String(value),
    })
  }

  return {
    rows,
    totalRow,
    trialBalanceAmount,
    trialBalanceDiff,
    auditNote,
    conclusion,
    debitLabel,
    creditLabel,
    updateField,
  }
}
