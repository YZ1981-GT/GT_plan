/**
 * useG5Adjustment — G5-4 调整分录汇总逻辑
 * 24行×10列，借贷平衡校验，AJE/RJE回写G5-1
 */
import { ref, computed } from 'vue'
import { parseNum, isDebitCreditBalanced } from '@/composables/useG5FormulaEngine'
import { ElMessageBox } from 'element-plus'

export interface AdjustmentEntry {
  id: string
  seq: number
  entryType: 'AJE' | 'RJE'
  date: string
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  preparedBy: string
  remark: string
}

export function useG5Adjustment() {
  const entries = ref<AdjustmentEntry[]>([])

  const debitTotal = computed(() => entries.value.reduce((s, e) => s + parseNum(e.debitAmount), 0))
  const creditTotal = computed(() => entries.value.reduce((s, e) => s + parseNum(e.creditAmount), 0))
  const isBalanced = computed(() => isDebitCreditBalanced(
    entries.value.map(e => e.debitAmount),
    entries.value.map(e => e.creditAmount),
  ))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)

  const ajeTotal = computed(() => ({
    debit: entries.value.filter(e => e.entryType === 'AJE').reduce((s, e) => s + parseNum(e.debitAmount), 0),
    credit: entries.value.filter(e => e.entryType === 'AJE').reduce((s, e) => s + parseNum(e.creditAmount), 0),
  }))
  const rjeTotal = computed(() => ({
    debit: entries.value.filter(e => e.entryType === 'RJE').reduce((s, e) => s + parseNum(e.debitAmount), 0),
    credit: entries.value.filter(e => e.entryType === 'RJE').reduce((s, e) => s + parseNum(e.creditAmount), 0),
  }))

  async function addEntry() {
    const { value } = await ElMessageBox.prompt('请输入摘要', '新增调整分录', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    if (!value?.trim()) return
    entries.value.push({
      id: crypto.randomUUID(),
      seq: entries.value.length + 1,
      entryType: 'AJE',
      date: new Date().toISOString().slice(0, 10),
      summary: value.trim(),
      accountCode: '1531',
      accountName: '长期应收款',
      debitAmount: 0,
      creditAmount: 0,
      preparedBy: '',
      remark: '',
    })
  }

  function removeEntry(id: string) {
    entries.value = entries.value.filter(e => e.id !== id)
    entries.value.forEach((e, i) => { e.seq = i + 1 })
  }

  return {
    entries, debitTotal, creditTotal, isBalanced, balanceDiff,
    ajeTotal, rjeTotal, addEntry, removeEntry,
  }
}
