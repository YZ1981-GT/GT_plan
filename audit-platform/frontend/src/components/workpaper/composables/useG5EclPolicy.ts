/** useG5EclPolicy — G5-8 会计政策检查（四 section 问卷） */
import { ref } from 'vue'
import { ElMessageBox } from 'element-plus'

export interface PolicyCheckRow {
  id: string
  checkItem: string
  requirement: string
  companyPolicy: string
  compliance: '合规' | '不合规' | '待核实'
  explanation: string
}

export interface PolicyChangeRow {
  id: string
  item: string
  priorYear: string
  currentYear: string
  changed: '是' | '否'
  reason: string
  rationality: string
}

export function useG5EclPolicy() {
  const section1 = ref<PolicyCheckRow[]>([
    { id: 's1-1', checkItem: '预期信用损失模型', requirement: '采用三阶段模型', companyPolicy: '', compliance: '待核实', explanation: '' },
    { id: 's1-2', checkItem: '损失率确定方法', requirement: '有合理依据', companyPolicy: '', compliance: '待核实', explanation: '' },
  ])
  const section2 = ref<PolicyCheckRow[]>([])
  const section3 = ref<PolicyCheckRow[]>([])
  const section4 = ref<PolicyChangeRow[]>([])
  const conclusion = ref('')

  async function addSection2Row() {
    const { value } = await ElMessageBox.prompt('请输入检查项', '新增检查项', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (!value?.trim()) return
    section2.value.push({ id: crypto.randomUUID(), checkItem: value.trim(), requirement: '', companyPolicy: '', compliance: '待核实', explanation: '' })
  }

  async function addSection3Row() {
    const { value } = await ElMessageBox.prompt('请输入检查项', '新增检查项', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (!value?.trim()) return
    section3.value.push({ id: crypto.randomUUID(), checkItem: value.trim(), requirement: '', companyPolicy: '', compliance: '待核实', explanation: '' })
  }

  return { section1, section2, section3, section4, conclusion, addSection2Row, addSection3Row }
}
