/** useG5ImpairmentCalc — G5-10 坏账准备测算（ECL 公式链 + Stage 分组） */
import { ref, computed } from 'vue'
import {
  parseNum, calcImpairmentProvision, calcImpairmentAdjustment,
  calcAdjustedBalance, calcAdjustedImpairment, calcAdjustedBookValue, calcCurrentYearProvision,
} from '@/composables/useG5FormulaEngine'
import { ElMessageBox } from 'element-plus'

export interface ImpairmentCalcRow {
  id: string
  seq: number
  debtor: string
  eclStage: 'Stage1' | 'Stage2' | 'Stage3'
  closingBalance: number
  creditLossRate: number
  unadjustedProvision: number
  balanceAdjustment: number
  adjustedLossRate: number
  provisionAdjustment: number
  adjustedBalance: number
  adjustedProvision: number
  adjustedNetValue: number
  priorYearProvision: number
  currentYearProvision: number
  currentYearReversal: number
  remark: string
}

export function useG5ImpairmentCalc() {
  const rows = ref<ImpairmentCalcRow[]>([])
  const activeTab = ref<'unadjusted' | 'adjusted'>('unadjusted')
  const activeRowIndex = ref(0)

  function recalcRow(row: ImpairmentCalcRow) {
    row.unadjustedProvision = calcImpairmentProvision(row.closingBalance, row.creditLossRate)
    row.provisionAdjustment = calcImpairmentAdjustment(row.balanceAdjustment, row.adjustedLossRate, row.closingBalance, row.creditLossRate)
    row.adjustedBalance = calcAdjustedBalance(row.closingBalance, row.balanceAdjustment)
    row.adjustedProvision = calcAdjustedImpairment(row.unadjustedProvision, row.provisionAdjustment)
    row.adjustedNetValue = calcAdjustedBookValue(row.adjustedBalance, row.adjustedProvision)
    row.currentYearProvision = calcCurrentYearProvision(row.adjustedProvision, row.priorYearProvision, row.currentYearReversal)
  }

  const stageGroups = computed(() => ({
    s1: rows.value.filter(r => r.eclStage === 'Stage1'),
    s2: rows.value.filter(r => r.eclStage === 'Stage2'),
    s3: rows.value.filter(r => r.eclStage === 'Stage3'),
  }))

  const totals = computed(() => ({
    closingBalance: rows.value.reduce((s, r) => s + parseNum(r.closingBalance), 0),
    adjustedProvision: rows.value.reduce((s, r) => s + parseNum(r.adjustedProvision), 0),
    currentYearProvision: rows.value.reduce((s, r) => s + parseNum(r.currentYearProvision), 0),
  }))

  async function addRow() {
    const { value } = await ElMessageBox.prompt('请输入债务人名称', '新增行', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (!value?.trim()) return
    const row: ImpairmentCalcRow = {
      id: crypto.randomUUID(), seq: rows.value.length + 1, debtor: value.trim(), eclStage: 'Stage1',
      closingBalance: 0, creditLossRate: 0, unadjustedProvision: 0, balanceAdjustment: 0, adjustedLossRate: 0,
      provisionAdjustment: 0, adjustedBalance: 0, adjustedProvision: 0, adjustedNetValue: 0,
      priorYearProvision: 0, currentYearProvision: 0, currentYearReversal: 0, remark: '',
    }
    recalcRow(row)
    rows.value.push(row)
  }

  function removeRow(id: string) {
    rows.value = rows.value.filter(r => r.id !== id)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
  }

  function loadRows(data: ImpairmentCalcRow[]) {
    rows.value = data.map((r, i) => {
      const row = { ...r, id: r.id || crypto.randomUUID(), seq: i + 1 }
      recalcRow(row)
      return row
    })
  }

  return { rows, activeTab, activeRowIndex, recalcRow, stageGroups, totals, addRow, removeRow, loadRows }
}
