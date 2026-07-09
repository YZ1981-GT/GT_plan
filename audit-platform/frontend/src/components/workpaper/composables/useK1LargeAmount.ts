/**
 * useK1LargeAmount — K1-5 大额其他应收款分析
 *
 * Spec: .kiro/specs/k1-other-receivables/
 * Task: 3.4
 * Requirements: 7.1-7.4
 *
 * 职责：
 * - 占比=单项/合计 + 降序排列 + 阈值高亮
 * - GtIndexChip跳转K1-2
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { calcProportion, calcSubtotal } from './useK1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K1LargeAmountRow {
  id: string
  counterparty: string
  endBalance: number
  proportion: number | null  // 占比（公式）
  nature: string             // 性质
  formReason: string         // 形成原因
  expectedRecovery: string   // 预计收回时间
  recoverability: string     // 收回可能性
  followUp: string           // 后续核查
}

export interface UseK1LargeAmountOpts {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK1LargeAmount(opts: UseK1LargeAmountOpts) {
  const { allResponses } = opts

  const rows = ref<K1LargeAmountRow[]>([])
  const highlightThreshold = ref<number>(0.1) // 默认10%高亮阈值

  // ─── 加载 ──────────────────────────────────────────────────────────────────

  function loadRows(): void {
    const raw = allResponses.value.get('K1-5-large-rows')?.remark
    if (!raw) { rows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      rows.value = Array.isArray(parsed) ? parsed : []
      recalcProportions()
      sortByAmount()
    } catch { rows.value = [] }
  }

  // ─── 占比计算 ─────────────────────────────────────────────────────────────

  const totalAmount: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.endBalance))
  )

  function recalcProportions(): void {
    const total = calcSubtotal(rows.value.map(r => r.endBalance))
    for (const row of rows.value) {
      row.proportion = calcProportion(row.endBalance, total)
    }
  }

  // ─── 降序排列 ─────────────────────────────────────────────────────────────

  function sortByAmount(): void {
    rows.value.sort((a, b) => b.endBalance - a.endBalance)
  }

  // ─── 阈值高亮 ─────────────────────────────────────────────────────────────

  function isAboveThreshold(row: K1LargeAmountRow): boolean {
    return (row.proportion ?? 0) >= highlightThreshold.value
  }

  // ─── 行操作 ────────────────────────────────────────────────────────────────

  function addRow(counterparty: string, endBalance: number): K1LargeAmountRow {
    const total = calcSubtotal(rows.value.map(r => r.endBalance)) + endBalance
    const newRow: K1LargeAmountRow = {
      id: `K1-5-r-${Date.now()}`,
      counterparty,
      endBalance,
      proportion: calcProportion(endBalance, total),
      nature: '',
      formReason: '',
      expectedRecovery: '',
      recoverability: '',
      followUp: '',
    }
    rows.value.push(newRow)
    recalcProportions()
    sortByAmount()
    return newRow
  }

  function updateRow(id: string, field: keyof K1LargeAmountRow, value: any): void {
    const row = rows.value.find(r => r.id === id)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'endBalance') {
      recalcProportions()
      sortByAmount()
    }
  }

  function removeRow(id: string): void {
    rows.value = rows.value.filter(r => r.id !== id)
    recalcProportions()
  }

  // ─── GtIndexChip 跳转数据 ──────────────────────────────────────────────────

  function getChipTarget(row: K1LargeAmountRow): { sheetName: string; search: string } {
    return { sheetName: 'K1-2', search: row.counterparty }
  }

  // ─── 序列化 ────────────────────────────────────────────────────────────────

  function serializeRows(): string {
    return JSON.stringify(rows.value)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    totalAmount,
    highlightThreshold,
    loadRows,
    addRow,
    updateRow,
    removeRow,
    isAboveThreshold,
    getChipTarget,
    sortByAmount,
    serializeRows,
  }
}
