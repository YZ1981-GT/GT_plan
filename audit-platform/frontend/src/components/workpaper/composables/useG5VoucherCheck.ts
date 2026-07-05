/** useG5VoucherCheck — G5-12 凭证检查（3 区段 Tab 行同步） */
import { ref, computed } from 'vue'
import { parseNum } from '@/composables/useG5FormulaEngine'
import { ElMessageBox } from 'element-plus'

export interface VoucherCheckRow {
  id: string
  seq: number
  summary: string
  counterAccount: string
  amount: number
  voucherDate: string
  voucherNo: string
  debtor: string
  businessType: string
  attachment: string
  check1: '✓' | '✗' | ''
  check2: '✓' | '✗' | ''
  check3: '✓' | '✗' | ''
  check4: '✓' | '✗' | ''
  check5: '✓' | '✗' | ''
  check6: '✓' | '✗' | ''
  check7: '✓' | '✗' | ''
  isAbnormal: '是' | '否'
  conclusion: string
  indexRef: string
  source?: string
}

export function useG5VoucherCheck() {
  const rows = ref<VoucherCheckRow[]>([])
  const activeTab = ref<'basic' | 'check' | 'conclusion'>('basic')
  const activeRowIndex = ref(0)

  function recalcRow(row: VoucherCheckRow) {
    const checks = [row.check1, row.check2, row.check3, row.check4, row.check5, row.check6, row.check7]
    const hasFail = checks.some(c => c === '✗')
    row.isAbnormal = hasFail ? '是' : '否'
    if (hasFail && !row.conclusion) row.conclusion = '存在核对异常项，需进一步追查'
  }

  const debitTotal = computed(() => rows.value.reduce((s, r) => s + parseNum(r.amount), 0))
  const abnormalCount = computed(() => rows.value.filter(r => r.isAbnormal === '是').length)

  async function addRow() {
    const { value } = await ElMessageBox.prompt('请输入摘要', '新增凭证行', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (!value?.trim()) return
    const row: VoucherCheckRow = {
      id: crypto.randomUUID(), seq: rows.value.length + 1, summary: value.trim(),
      counterAccount: '', amount: 0, voucherDate: '', voucherNo: '', debtor: '', businessType: '',
      attachment: '', check1: '', check2: '', check3: '', check4: '', check5: '', check6: '', check7: '',
      isAbnormal: '否', conclusion: '', indexRef: '',
    }
    rows.value.push(row)
  }

  function removeRow(id: string) {
    rows.value = rows.value.filter(r => r.id !== id)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
  }

  function loadRows(data: VoucherCheckRow[]) {
    rows.value = data.map((r, i) => {
      const row = { ...r, id: r.id || crypto.randomUUID(), seq: i + 1 }
      recalcRow(row)
      return row
    })
  }

  function mergeSample(sample: Partial<VoucherCheckRow>) {
    const row: VoucherCheckRow = {
      id: crypto.randomUUID(), seq: rows.value.length + 1,
      summary: sample.summary || '', counterAccount: sample.counterAccount || '',
      amount: parseNum(sample.amount), voucherDate: sample.voucherDate || '', voucherNo: sample.voucherNo || '',
      debtor: '', businessType: '', attachment: '',
      check1: '', check2: '', check3: '', check4: '', check5: '', check6: '', check7: '',
      isAbnormal: '否', conclusion: '', indexRef: '', source: sample.source || '抽凭',
    }
    rows.value.push(row)
  }

  return {
    rows, activeTab, activeRowIndex, recalcRow, debitTotal, abnormalCount,
    addRow, removeRow, loadRows, mergeSample,
  }
}
