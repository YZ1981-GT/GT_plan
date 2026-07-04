/**
 * useG1Adjudication — G1-1 审定表（投资品种 × 损益分类）
 */
import { ref, computed, type Ref } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
} from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export const G1_INVEST_TYPES = [
  { rowKey: 'stock', label: '股票' },
  { rowKey: 'fund', label: '基金' },
  { rowKey: 'bond', label: '债券' },
  { rowKey: 'derivative', label: '衍生工具' },
  { rowKey: 'other', label: '其他' },
] as const

export const G1_MEASURE_TYPES = [
  { rowKey: 'cost', label: '成本' },
  { rowKey: 'fv-change', label: '公允价值变动' },
  { rowKey: 'disposal', label: '处置损益' },
] as const

export interface G1AdjudicationRow {
  rowKey: string
  investKey: string
  measureKey: string
  investLabel: string
  measureLabel: string
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  currentAudited: number
  changeAmount: number
  changeRate: number | '' | 'N/A'
}

function cellId(invest: string, measure: string, field: string): string {
  return `G1-1-${invest}-${measure}-${field}`
}

function loadNum(map: Map<string, ChecklistResponse>, id: string): number {
  return parseNum(map.get(id)?.conclusion)
}

function buildRows(map: Map<string, ChecklistResponse>): G1AdjudicationRow[] {
  const rows: G1AdjudicationRow[] = []
  for (const inv of G1_INVEST_TYPES) {
    for (const m of G1_MEASURE_TYPES) {
      const priorU = loadNum(map, cellId(inv.rowKey, m.rowKey, 'prior-unadj'))
      const priorAje = loadNum(map, cellId(inv.rowKey, m.rowKey, 'prior-aje'))
      const priorRje = loadNum(map, cellId(inv.rowKey, m.rowKey, 'prior-rje'))
      const curU = loadNum(map, cellId(inv.rowKey, m.rowKey, 'cur-unadj'))
      const curAje = loadNum(map, cellId(inv.rowKey, m.rowKey, 'cur-aje'))
      const curRje = loadNum(map, cellId(inv.rowKey, m.rowKey, 'cur-rje'))
      const priorAudited = calcAuditedAmount(priorU, priorAje, priorRje)
      const currentAudited = calcAuditedAmount(curU, curAje, curRje)
      rows.push({
        rowKey: `${inv.rowKey}::${m.rowKey}`,
        investKey: inv.rowKey,
        measureKey: m.rowKey,
        investLabel: inv.label,
        measureLabel: m.label,
        priorUnadjusted: priorU,
        priorAje,
        priorRje,
        priorAudited,
        currentUnadjusted: curU,
        currentAje: curAje,
        currentRje: curRje,
        currentAudited,
        changeAmount: calcChangeAmount(currentAudited, priorAudited),
        changeRate: calcChangeRate(priorAudited, currentAudited),
      })
    }
  }
  return rows
}

function subtotal(rows: G1AdjudicationRow[]): G1AdjudicationRow {
  return {
    rowKey: 'subtotal',
    investKey: '',
    measureKey: '',
    investLabel: '合计',
    measureLabel: '',
    priorUnadjusted: calcSubtotal(rows.map((r) => r.priorUnadjusted)),
    priorAje: calcSubtotal(rows.map((r) => r.priorAje)),
    priorRje: calcSubtotal(rows.map((r) => r.priorRje)),
    priorAudited: calcSubtotal(rows.map((r) => r.priorAudited)),
    currentUnadjusted: calcSubtotal(rows.map((r) => r.currentUnadjusted)),
    currentAje: calcSubtotal(rows.map((r) => r.currentAje)),
    currentRje: calcSubtotal(rows.map((r) => r.currentRje)),
    currentAudited: calcSubtotal(rows.map((r) => r.currentAudited)),
    changeAmount: calcSubtotal(rows.map((r) => r.changeAmount)),
    changeRate: '',
  }
}

export function useG1Adjudication(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const auditNote = ref('')
  const conclusion = ref('')
  const trialBalanceAmount = ref(0)

  const rows = computed(() => buildRows(opts.allResponses.value))
  const totalRow = computed(() => subtotal(rows.value))
  const trialBalanceDiff = computed(() => totalRow.value.currentAudited - trialBalanceAmount.value)

  function updateField(
    investKey: string,
    measureKey: string,
    period: 'prior' | 'cur',
    field: 'unadj' | 'aje' | 'rje',
    value: number,
  ) {
    if (opts.isReadonly.value) return
    const mapField = period === 'prior'
      ? (field === 'unadj' ? 'prior-unadj' : field === 'aje' ? 'prior-aje' : 'prior-rje')
      : (field === 'unadj' ? 'cur-unadj' : field === 'aje' ? 'cur-aje' : 'cur-rje')
    opts.debouncedSave(cellId(investKey, measureKey, mapField), { conclusion: String(value) })
  }

  return {
    rows,
    totalRow,
    trialBalanceAmount,
    trialBalanceDiff,
    auditNote,
    conclusion,
    updateField,
  }
}
