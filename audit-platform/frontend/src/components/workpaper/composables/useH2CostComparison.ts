/**
 * useH2CostComparison — H2-7 工程造价比较 composable
 *
 * CostComparisonRow 16列 + 14公式自动计算
 * 从H2-2取数 + 超支/超预算高亮规则
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.9
 * Requirements: 8.1-8.7
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcSubtotal, calcCostDiffRate } from './useH2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H2CostComparisonRow {
  rowId: string
  /** 工程名称 */
  name: string
  /** 合同预算 */
  contractBudget: number
  /** 调整预算 */
  adjustedBudget: number
  /** 预算变更说明 */
  budgetChangeNote: string
  /** 累计实际支出-材料 */
  actualMaterial: number
  /** 累计实际支出-人工 */
  actualLabor: number
  /** 累计实际支出-机械 */
  actualMachinery: number
  /** 累计实际支出-其他 */
  actualOther: number
  /** 累计实际合计 (公式列) */
  actualTotal: number
  /** 超支金额 (公式列: max(实际-调整预算, 0)) */
  overspendAmount: number
  /** 超支率(%) (公式列) */
  overspendRate: number | null
  /** 节余金额 (公式列: max(调整预算-实际, 0)) */
  savingAmount: number
  /** 节余率(%) (公式列) */
  savingRate: number | null
  /** 预算执行率(%) (公式列) */
  executionRate: number | null
  /** 造价偏差原因 */
  deviationReason: string
  /** 备注 */
  remark: string
}

export type CostHighlight = 'red-overspend' | 'red-over-execution' | null

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H2-7-rows'
const NOTE_KEY = 'H2-7-audit-note'
const CONCLUSION_KEY = 'H2-7-audit-conclusion'
const OVERSPEND_THRESHOLD = 10  // 超支率>10%红色高亮

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2CostComparison(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H2CostComparisonRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _recalcRow(row: H2CostComparisonRow): void {
    // 累计实际合计
    row.actualTotal = row.actualMaterial + row.actualLabor + row.actualMachinery + row.actualOther

    // 超支 / 节余
    const diff = row.actualTotal - row.adjustedBudget
    row.overspendAmount = diff > 0 ? diff : 0
    row.savingAmount = diff < 0 ? -diff : 0

    // 超支率 / 节余率
    row.overspendRate = row.adjustedBudget > 0
      ? (row.overspendAmount / row.adjustedBudget) * 100
      : null
    row.savingRate = row.adjustedBudget > 0
      ? (row.savingAmount / row.adjustedBudget) * 100
      : null

    // 预算执行率
    row.executionRate = row.adjustedBudget > 0
      ? (row.actualTotal / row.adjustedBudget) * 100
      : null
  }

  function _normalizeRow(r: any): H2CostComparisonRow {
    const row: H2CostComparisonRow = {
      rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      name: r.name ?? '',
      contractBudget: Number(r.contractBudget) || 0,
      adjustedBudget: Number(r.adjustedBudget) || 0,
      budgetChangeNote: r.budgetChangeNote ?? '',
      actualMaterial: Number(r.actualMaterial) || 0,
      actualLabor: Number(r.actualLabor) || 0,
      actualMachinery: Number(r.actualMachinery) || 0,
      actualOther: Number(r.actualOther) || 0,
      actualTotal: 0,
      overspendAmount: 0,
      overspendRate: null,
      savingAmount: 0,
      savingRate: null,
      executionRate: null,
      deviationReason: r.deviationReason ?? '',
      remark: r.remark ?? '',
    }
    _recalcRow(row)
    return row
  }

  // ─── Init: 优先从持久化加载，否则从H2-2取数 ────────────────────────────────

  function initFromAllResponses(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(_normalizeRow)
    } else {
      // 从H2-2明细表自动取数
      const h2_2_resp = options.allResponses.value.get('H2-2-rows')
      const raw = h2_2_resp?.remark ?? h2_2_resp?.conclusion
      if (raw) {
        try {
          const h2Rows = JSON.parse(raw)
          if (Array.isArray(h2Rows)) {
            rows.value = h2Rows.map((r: any) => _normalizeRow({
              name: r.name,
              contractBudget: r.budget,
              adjustedBudget: r.budget,
              actualMaterial: r.increaseMaterial,
              actualLabor: r.increaseLabor,
              actualMachinery: r.increaseMachinery,
              actualOther: r.increaseOther,
            }))
          }
        } catch { /* empty */ }
      } else {
        rows.value = []
      }
    }
    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  /** 合计行 */
  const totalRow: ComputedRef<Partial<H2CostComparisonRow>> = computed(() => ({
    contractBudget: calcSubtotal(rows.value.map(r => r.contractBudget)),
    adjustedBudget: calcSubtotal(rows.value.map(r => r.adjustedBudget)),
    actualMaterial: calcSubtotal(rows.value.map(r => r.actualMaterial)),
    actualLabor: calcSubtotal(rows.value.map(r => r.actualLabor)),
    actualMachinery: calcSubtotal(rows.value.map(r => r.actualMachinery)),
    actualOther: calcSubtotal(rows.value.map(r => r.actualOther)),
    actualTotal: calcSubtotal(rows.value.map(r => r.actualTotal)),
    overspendAmount: calcSubtotal(rows.value.map(r => r.overspendAmount)),
    savingAmount: calcSubtotal(rows.value.map(r => r.savingAmount)),
  }))

  /** 高亮规则 */
  const rowHighlights: ComputedRef<Map<string, CostHighlight>> = computed(() => {
    const map = new Map<string, CostHighlight>()
    for (const row of rows.value) {
      if (row.overspendRate != null && row.overspendRate > OVERSPEND_THRESHOLD) {
        map.set(row.rowId, 'red-overspend')
      } else if (row.executionRate != null && row.executionRate > 100) {
        map.set(row.rowId, 'red-over-execution')
      } else {
        map.set(row.rowId, null)
      }
    }
    return map
  })

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(name: string): void {
    if (options.isReadonly.value) return
    if (!name?.trim()) return
    rows.value.push(_normalizeRow({ name: name.trim() }))
    _persist()
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      rows.value.splice(idx, 1)
      _persist()
    }
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    const formulaFields = ['actualTotal', 'overspendAmount', 'overspendRate', 'savingAmount', 'savingRate', 'executionRate']
    if (formulaFields.includes(field)) return

    const numFields = ['contractBudget', 'adjustedBudget', 'actualMaterial', 'actualLabor', 'actualMachinery', 'actualOther']
    if (numFields.includes(field)) {
      ;(row as any)[field] = Number(value) || 0
    } else {
      ;(row as any)[field] = String(value ?? '')
    }
    _recalcRow(row)
    _persist()
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options.onSave?.(CONCLUSION_KEY, conclusion)
  }

  function _persist(): void {
    if (!options.onSave) return
    options.onSave(ROWS_KEY, rows.value.map(r => ({
      rowId: r.rowId,
      name: r.name,
      contractBudget: r.contractBudget,
      adjustedBudget: r.adjustedBudget,
      budgetChangeNote: r.budgetChangeNote,
      actualMaterial: r.actualMaterial,
      actualLabor: r.actualLabor,
      actualMachinery: r.actualMachinery,
      actualOther: r.actualOther,
      deviationReason: r.deviationReason,
      remark: r.remark,
    })))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    auditNote,
    auditConclusion,
    totalRow,
    rowHighlights,
    addRow,
    removeRow,
    updateCell,
    saveNote,
    saveConclusion,
    initFromAllResponses,
  }
}

export default useH2CostComparison
