/**
 * useG5BadDebtDetail — G5-3 坏账准备明细表逻辑 (20列→2区段Tab)
 *
 * Tab1: 未审数+审计调整(11列)
 * Tab2: 审定数(9列)
 * ECL公式链：③=①×② / ⑥=⑤×②A+①×(②A-②) / ⑦=①+⑤ / ⑧=③+⑥ / ⑨=⑦-⑧
 */
import { ref, computed } from 'vue'
import {
  parseNum,
  calcImpairmentProvision,
  calcImpairmentAdjustment,
  calcAdjustedBalance,
  calcAdjustedImpairment,
  calcAdjustedBookValue,
  calcCurrentYearProvision,
} from '@/composables/useG5FormulaEngine'
import { ElMessageBox } from 'element-plus'

export interface BadDebtDetailRow {
  id: string
  seq: number
  debtorOrGroup: string
  provisionMethod: 'group' | 'individual'
  // Tab1
  closingBalance: number       // ①
  creditLossRate: number       // ②
  unadjustedProvision: number  // ③=①×②
  balanceAdjustment: number    // ⑤
  adjustedLossRate: number     // ②A
  provisionAdjustment: number  // ⑥=⑤×②A+①×(②A-②)
  adjustmentDesc: string
  indexRef: string
  // Tab2
  adjustedBalance: number      // ⑦=①+⑤
  adjustedProvision: number    // ⑧=③+⑥
  adjustedNetValue: number     // ⑨=⑦-⑧
  priorYearProvision: number
  currentYearProvision: number // =⑧-上年+转回
  currentYearReversal: number
  remark: string
}

export function useG5BadDebtDetail() {
  const rows = ref<BadDebtDetailRow[]>([])
  const activeTab = ref<'unadjusted' | 'adjusted'>('unadjusted')
  const activeRowIndex = ref(0)

  function recalcRow(row: BadDebtDetailRow) {
    row.unadjustedProvision = calcImpairmentProvision(row.closingBalance, row.creditLossRate)
    row.provisionAdjustment = calcImpairmentAdjustment(
      row.balanceAdjustment, row.adjustedLossRate,
      row.closingBalance, row.creditLossRate,
    )
    row.adjustedBalance = calcAdjustedBalance(row.closingBalance, row.balanceAdjustment)
    row.adjustedProvision = calcAdjustedImpairment(row.unadjustedProvision, row.provisionAdjustment)
    row.adjustedNetValue = calcAdjustedBookValue(row.adjustedBalance, row.adjustedProvision)
    row.currentYearProvision = calcCurrentYearProvision(
      row.adjustedProvision, row.priorYearProvision, row.currentYearReversal,
    )
  }

  const groupRows = computed(() => rows.value.filter(r => r.provisionMethod === 'group'))
  const individualRows = computed(() => rows.value.filter(r => r.provisionMethod === 'individual'))

  const totals = computed(() => ({
    closingBalance: rows.value.reduce((s, r) => s + parseNum(r.closingBalance), 0),
    unadjustedProvision: rows.value.reduce((s, r) => s + parseNum(r.unadjustedProvision), 0),
    adjustedBalance: rows.value.reduce((s, r) => s + parseNum(r.adjustedBalance), 0),
    adjustedProvision: rows.value.reduce((s, r) => s + parseNum(r.adjustedProvision), 0),
    adjustedNetValue: rows.value.reduce((s, r) => s + parseNum(r.adjustedNetValue), 0),
    currentYearProvision: rows.value.reduce((s, r) => s + parseNum(r.currentYearProvision), 0),
  }))

  async function addRow() {
    const { value } = await ElMessageBox.prompt('请输入债务人/组合名称', '新增行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    if (!value?.trim()) return
    const newRow: BadDebtDetailRow = {
      id: crypto.randomUUID(),
      seq: rows.value.length + 1,
      debtorOrGroup: value.trim(),
      provisionMethod: 'group',
      closingBalance: 0, creditLossRate: 0, unadjustedProvision: 0,
      balanceAdjustment: 0, adjustedLossRate: 0, provisionAdjustment: 0,
      adjustmentDesc: '', indexRef: '',
      adjustedBalance: 0, adjustedProvision: 0, adjustedNetValue: 0,
      priorYearProvision: 0, currentYearProvision: 0, currentYearReversal: 0,
      remark: '',
    }
    rows.value.push(newRow)
  }

  function removeRow(id: string) {
    rows.value = rows.value.filter(r => r.id !== id)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
  }

  return {
    rows, activeTab, activeRowIndex,
    recalcRow, groupRows, individualRows, totals,
    addRow, removeRow,
  }
}
