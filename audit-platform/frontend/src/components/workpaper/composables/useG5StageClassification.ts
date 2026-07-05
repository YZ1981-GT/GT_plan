/** useG5StageClassification — G5-9 三阶段划分（行式交互） */
import { ref, computed } from 'vue'
import { determineStage } from '@/composables/useG5FormulaEngine'
import { ElMessageBox } from 'element-plus'

export interface StageClassificationRow {
  id: string
  seq: number
  debtor: string
  significantIncrease: boolean
  lowCreditRisk: boolean
  creditImpairment: boolean
  companyStage: 'Stage1' | 'Stage2' | 'Stage3'
  auditStage: 'Stage1' | 'Stage2' | 'Stage3'
  consistent: boolean
  varianceDesc: string
  indexRef: string
}

export function useG5StageClassification() {
  const rows = ref<StageClassificationRow[]>([])
  const conclusion = ref('')

  function recalcRow(row: StageClassificationRow) {
    row.auditStage = determineStage(row.significantIncrease, row.lowCreditRisk, row.creditImpairment)
    row.consistent = row.auditStage === row.companyStage
  }

  const summary = computed(() => {
    const s1 = rows.value.filter(r => r.auditStage === 'Stage1').length
    const s2 = rows.value.filter(r => r.auditStage === 'Stage2').length
    const s3 = rows.value.filter(r => r.auditStage === 'Stage3').length
    const inconsistent = rows.value.filter(r => !r.consistent).length
    return { s1, s2, s3, inconsistent }
  })

  async function addRow() {
    const { value } = await ElMessageBox.prompt('请输入债务人名称', '新增债务人', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (!value?.trim()) return
    const row: StageClassificationRow = {
      id: crypto.randomUUID(), seq: rows.value.length + 1, debtor: value.trim(),
      significantIncrease: false, lowCreditRisk: false, creditImpairment: false,
      companyStage: 'Stage1', auditStage: 'Stage1', consistent: true, varianceDesc: '', indexRef: '',
    }
    recalcRow(row)
    rows.value.push(row)
  }

  function removeRow(id: string) {
    rows.value = rows.value.filter(r => r.id !== id)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
  }

  function loadRows(data: StageClassificationRow[]) {
    rows.value = data.map((r, i) => {
      const row = { ...r, id: r.id || crypto.randomUUID(), seq: i + 1 }
      recalcRow(row)
      return row
    })
  }

  return { rows, conclusion, recalcRow, summary, addRow, removeRow, loadRows }
}
