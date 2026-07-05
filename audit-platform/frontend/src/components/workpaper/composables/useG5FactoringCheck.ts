/** useG5FactoringCheck — G5-7 保理终止确认核查 */
import { ref, computed } from 'vue'
import { parseNum } from '@/composables/useG5FormulaEngine'
import { ElMessageBox } from 'element-plus'

export interface FactoringCheckRow {
  id: string
  seq: number
  debtor: string
  factor: string
  amount: number
  method: '有追索' | '无追索' | '其他'
  derecognition: '是' | '否'
  basis: string
  conclusion: string
  indexRef: string
}

export function useG5FactoringCheck() {
  const rows = ref<FactoringCheckRow[]>([])
  const conclusion = ref('')

  const totals = computed(() => ({
    amount: rows.value.reduce((s, r) => s + parseNum(r.amount), 0),
    derecognized: rows.value.filter(r => r.derecognition === '是').reduce((s, r) => s + parseNum(r.amount), 0),
    notDerecognized: rows.value.filter(r => r.derecognition === '否').reduce((s, r) => s + parseNum(r.amount), 0),
  }))

  const warningRows = computed(() =>
    rows.value.filter(r => r.method === '有追索' && r.derecognition === '是'),
  )

  async function addRow() {
    const { value } = await ElMessageBox.prompt('请输入债务人名称', '新增保理记录', {
      confirmButtonText: '确定', cancelButtonText: '取消',
    })
    if (!value?.trim()) return
    rows.value.push({
      id: crypto.randomUUID(),
      seq: rows.value.length + 1,
      debtor: value.trim(),
      factor: '', amount: 0, method: '有追索', derecognition: '否',
      basis: '', conclusion: '', indexRef: '',
    })
  }

  function removeRow(id: string) {
    rows.value = rows.value.filter(r => r.id !== id)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
  }

  function loadRows(data: FactoringCheckRow[]) {
    rows.value = data.map((r, i) => ({ ...r, id: r.id || crypto.randomUUID(), seq: i + 1 }))
  }

  return { rows, conclusion, totals, warningRows, addRow, removeRow, loadRows }
}
