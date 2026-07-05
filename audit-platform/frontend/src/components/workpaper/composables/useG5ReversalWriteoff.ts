/** useG5ReversalWriteoff — G5-11 转回核销检查 */
import { ref, computed } from 'vue'
import { parseNum, isReversalValid } from '@/composables/useG5FormulaEngine'
import { ElMessageBox } from 'element-plus'

export interface ReversalRow {
  id: string
  seq: number
  debtor: string
  accumulatedProvision: number
  reversalAmount: number
  isValid: boolean
  isRelatedParty: boolean
  reason: string
  indexRef: string
}

export interface WriteoffRow {
  id: string
  seq: number
  debtor: string
  writeoffAmount: number
  approvalStatus: string
  isRelatedParty: boolean
  reason: string
  indexRef: string
}

export function useG5ReversalWriteoff() {
  const reversalRows = ref<ReversalRow[]>([])
  const writeoffRows = ref<WriteoffRow[]>([])
  const activeTab = ref<'reversal' | 'writeoff'>('reversal')
  const activeRowIndex = ref(0)

  function recalcReversal(row: ReversalRow) {
    row.isValid = isReversalValid(row.reversalAmount, row.accumulatedProvision)
  }

  async function addReversalRow() {
    const { value } = await ElMessageBox.prompt('请输入债务人名称', '新增转回行', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (!value?.trim()) return
    const row: ReversalRow = {
      id: crypto.randomUUID(), seq: reversalRows.value.length + 1, debtor: value.trim(),
      accumulatedProvision: 0, reversalAmount: 0, isValid: true, isRelatedParty: false, reason: '', indexRef: '',
    }
    recalcReversal(row)
    reversalRows.value.push(row)
  }

  async function addWriteoffRow() {
    const { value } = await ElMessageBox.prompt('请输入债务人名称', '新增核销行', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (!value?.trim()) return
    writeoffRows.value.push({
      id: crypto.randomUUID(), seq: writeoffRows.value.length + 1, debtor: value.trim(),
      writeoffAmount: 0, approvalStatus: '', isRelatedParty: false, reason: '', indexRef: '',
    })
  }

  const invalidReversals = computed(() => reversalRows.value.filter(r => !r.isValid))

  function loadReversalRows(data: ReversalRow[]) {
    reversalRows.value = data.map((r, i) => {
      const row = { ...r, id: r.id || crypto.randomUUID(), seq: i + 1 }
      recalcReversal(row)
      return row
    })
  }

  function loadWriteoffRows(data: WriteoffRow[]) {
    writeoffRows.value = data.map((r, i) => ({ ...r, id: r.id || crypto.randomUUID(), seq: i + 1 }))
  }

  return {
    reversalRows, writeoffRows, activeTab, activeRowIndex,
    recalcReversal, addReversalRow, addWriteoffRow, invalidReversals,
    loadReversalRows, loadWriteoffRows,
  }
}
