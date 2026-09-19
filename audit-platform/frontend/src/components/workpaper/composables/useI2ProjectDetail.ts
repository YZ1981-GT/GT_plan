/**
 * useI2ProjectDetail — I2-7 研发项目构成明细表
 * 滚动勾稽 + 资本化/费用化 + I2-2 交叉验证 + I6 费用化交叉
 */
import { ref, computed, watch, onScopeDispose, type Ref, type ComputedRef } from 'vue'
import {
  type I2ProjectDetailRow,
  type I2ProjectDetailSummary,
  type I2ProjectStageKey,
  type I2ProjectCostKey,
  emptyI2ProjectDetailRow,
  normalizeI2ProjectDetailRow,
  recalcI2ProjectDetailRow,
  serializeI2ProjectDetailRow,
  summarizeI2ProjectDetail,
  costNatureSum,
  costTreatmentSum,
  hasTreatmentMismatch,
  I2_PROJECT_COST_KEYS,
  I2_PROJECT_COST_LABELS,
  I2_PROJECT_STAGE_LABELS,
  I2_PROJECT_EDITABLE_STAGES,
} from './i2ProjectDetailModel'

export {
  type I2ProjectDetailRow,
  type I2ProjectDetailSummary,
  type I2ProjectStageKey,
  type I2ProjectCostKey,
  type I2ProjectCostBlock,
  emptyI2ProjectDetailRow,
  costNatureSum,
  costTreatmentSum,
  hasTreatmentMismatch,
  I2_PROJECT_COST_KEYS,
  I2_PROJECT_COST_LABELS,
  I2_PROJECT_COST_NATURE_KEYS,
  I2_PROJECT_TREATMENT_KEYS,
  I2_PROJECT_STAGE_KEYS,
  I2_PROJECT_STAGE_LABELS,
  I2_PROJECT_EDITABLE_STAGES,
} from './i2ProjectDetailModel'

const STORAGE_ROWS = 'I2-7-rows'
const STORAGE_PROCESS = 'I2-7-audit-process'
const STORAGE_NOTE = 'I2-7-audit-note'
const STORAGE_CONCLUSION = 'I2-7-audit-conclusion'
const I22_ROWS = 'I2-2-rows'

function _safeParseArray(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string' && raw) {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch { return [] }
  }
  if (raw && typeof raw === 'object') {
    const obj = raw as any
    const remark = obj.remark ?? obj.conclusion
    if (remark != null) return _safeParseArray(remark)
  }
  return []
}

function _readText(raw: unknown): string {
  if (raw == null) return ''
  if (typeof raw === 'string') return raw
  if (typeof raw === 'object') return String((raw as any).remark ?? (raw as any).conclusion ?? '')
  return ''
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export function useI2ProjectDetail(
  allResponses: Ref<Map<string, any>>,
  options?: {
    saveResponse?: (sheetCode: string, data: Record<string, any>) => Promise<void>
  },
) {
  const rows = ref<I2ProjectDetailRow[]>([])
  const auditProcess = ref('')
  const auditNote = ref('')
  const auditConclusion = ref('')
  const activeStage = ref<I2ProjectStageKey | 'overview'>('increase')

  /** I6 费用化合计（EventBus）；未收到时 ready=false */
  const i6Expense = ref(0)
  const i6Ready = ref(false)

  function load() {
    const map = allResponses.value
    rows.value = _safeParseArray(map.get(STORAGE_ROWS)).map(normalizeI2ProjectDetailRow)
    auditProcess.value = _readText(map.get(STORAGE_PROCESS))
    auditNote.value = _readText(map.get(STORAGE_NOTE))
    auditConclusion.value = _readText(map.get(STORAGE_CONCLUSION))
  }

  watch(
    () => [
      allResponses.value.get(STORAGE_ROWS),
      allResponses.value.get(STORAGE_PROCESS),
      allResponses.value.get(STORAGE_NOTE),
      allResponses.value.get(STORAGE_CONCLUSION),
      allResponses.value.get(I22_ROWS),
    ],
    () => load(),
    { immediate: true },
  )

  const summary: ComputedRef<I2ProjectDetailSummary> = computed(() =>
    summarizeI2ProjectDetail(rows.value),
  )

  /** 与 I2-2 交叉：优先用本期增加资本化合计 vs I2-2 totalInvestment */
  const crossValidateI22Diff = computed(() => {
    const detailRows = _safeParseArray(allResponses.value.get(I22_ROWS))
    if (!detailRows.length) return null
    const i22Total = detailRows.reduce(
      (s, r) => s + _num(r.totalInvestment ?? r.capitalizedAmount ?? r.endingBalance),
      0,
    )
    const local = summary.value.increaseCapitalized || summary.value.increaseTotal
    return Math.round((local - i22Total) * 100) / 100
  })

  /** I6 费用化 vs 本表本期增加「费用化」合计 */
  const i6ExpenseCross = computed(() => {
    const local = summary.value.increaseExpensed
    if (!i6Ready.value) {
      return { ready: false as const, i6: 0, local, diff: null as number | null }
    }
    const diff = Math.round((local - i6Expense.value) * 100) / 100
    return { ready: true as const, i6: i6Expense.value, local, diff }
  })

  function _onI6ExpenseUpdated(event: Event): void {
    const detail = (event as CustomEvent<{ expense?: number }>).detail
    if (detail && typeof detail === 'object') {
      i6Expense.value = _num(detail.expense)
      i6Ready.value = true
    }
  }
  window.addEventListener('research:expense-updated', _onI6ExpenseUpdated)
  onScopeDispose(() => {
    window.removeEventListener('research:expense-updated', _onI6ExpenseUpdated)
  })

  function addRow(partial?: Partial<I2ProjectDetailRow>) {
    rows.value.push(emptyI2ProjectDetailRow(partial))
  }

  function removeRow(rowId: string) {
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
  }

  function onCostChange(row: I2ProjectDetailRow) {
    recalcI2ProjectDetailRow(row)
  }

  function isStageEditable(stage: I2ProjectStageKey): boolean {
    return I2_PROJECT_EDITABLE_STAGES.includes(stage)
  }

  async function persistAll() {
    const save = options?.saveResponse
    if (!save) return
    await save('I2-7', {
      [STORAGE_ROWS]: JSON.stringify(rows.value.map(serializeI2ProjectDetailRow)),
      [STORAGE_PROCESS]: auditProcess.value,
      [STORAGE_NOTE]: auditNote.value,
      [STORAGE_CONCLUSION]: auditConclusion.value,
    })
  }

  async function saveField(key: string, val: string) {
    if (key === STORAGE_PROCESS) auditProcess.value = val
    if (key === STORAGE_NOTE) auditNote.value = val
    if (key === STORAGE_CONCLUSION) auditConclusion.value = val
    await options?.saveResponse?.('I2-7', { [key]: val })
  }

  return {
    rows,
    auditProcess,
    auditNote,
    auditConclusion,
    activeStage,
    summary,
    crossValidateI22Diff,
    i6ExpenseCross,
    load,
    addRow,
    removeRow,
    onCostChange,
    isStageEditable,
    persistAll,
    saveField,
    STORAGE_PROCESS,
    STORAGE_NOTE,
    STORAGE_CONCLUSION,
  }
}
