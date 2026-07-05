/**
 * useG5BalanceDetail — G5-2 余额明细表逻辑 (22列→2区段Tab)
 *
 * Tab1: 债务人基础信息(10列)
 * Tab2: 余额分析+账龄(12列)
 * 公式：期末余额=合同总额-已收回 / 净额=余额-未实现 / 账龄合计
 */
import { ref, computed } from 'vue'
import { parseNum, calcAgingTotal } from '@/composables/useG5FormulaEngine'
import { ElMessageBox } from 'element-plus'

export interface BalanceDetailRow {
  id: string
  seq: number
  debtorName: string
  businessType: 'lease' | 'installment' | 'factoring' | 'other'
  contractNo: string
  startDate: string
  maturityDate: string
  contractAmount: number
  recoveredAmount: number
  closingBalance: number
  isRelatedParty: boolean
  unrealizedIncome: number
  netAmount: number
  aging1Year: number
  aging1to2: number
  aging2to3: number
  aging3to4: number
  aging4to5: number
  aging5Plus: number
  agingTotal: number
  remark: string
}

export function useG5BalanceDetail() {
  const rows = ref<BalanceDetailRow[]>([])
  const activeTab = ref<'basic' | 'aging'>('basic')
  const activeRowIndex = ref(0)

  function recalcRow(row: BalanceDetailRow) {
    row.closingBalance = parseNum(row.contractAmount) - parseNum(row.recoveredAmount)
    row.netAmount = row.closingBalance - parseNum(row.unrealizedIncome)
    row.agingTotal = calcAgingTotal(
      row.aging1Year, row.aging1to2, row.aging2to3,
      row.aging3to4, row.aging4to5, row.aging5Plus,
    )
  }

  const agingMismatchRows = computed(() =>
    rows.value.filter(r => Math.abs(r.agingTotal - r.netAmount) > 0.01)
  )

  const totals = computed(() => ({
    contractAmount: rows.value.reduce((s, r) => s + parseNum(r.contractAmount), 0),
    recoveredAmount: rows.value.reduce((s, r) => s + parseNum(r.recoveredAmount), 0),
    closingBalance: rows.value.reduce((s, r) => s + parseNum(r.closingBalance), 0),
    netAmount: rows.value.reduce((s, r) => s + parseNum(r.netAmount), 0),
    aging1Year: rows.value.reduce((s, r) => s + parseNum(r.aging1Year), 0),
    aging1to2: rows.value.reduce((s, r) => s + parseNum(r.aging1to2), 0),
    aging2to3: rows.value.reduce((s, r) => s + parseNum(r.aging2to3), 0),
    aging3to4: rows.value.reduce((s, r) => s + parseNum(r.aging3to4), 0),
    aging4to5: rows.value.reduce((s, r) => s + parseNum(r.aging4to5), 0),
    aging5Plus: rows.value.reduce((s, r) => s + parseNum(r.aging5Plus), 0),
  }))

  async function addRow() {
    const { value } = await ElMessageBox.prompt('请输入债务人名称', '新增行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    if (!value?.trim()) return
    const newRow: BalanceDetailRow = {
      id: crypto.randomUUID(),
      seq: rows.value.length + 1,
      debtorName: value.trim(),
      businessType: 'other',
      contractNo: '',
      startDate: '',
      maturityDate: '',
      contractAmount: 0,
      recoveredAmount: 0,
      closingBalance: 0,
      isRelatedParty: false,
      unrealizedIncome: 0,
      netAmount: 0,
      aging1Year: 0, aging1to2: 0, aging2to3: 0,
      aging3to4: 0, aging4to5: 0, aging5Plus: 0,
      agingTotal: 0,
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
    recalcRow, agingMismatchRows, totals,
    addRow, removeRow,
  }
}
