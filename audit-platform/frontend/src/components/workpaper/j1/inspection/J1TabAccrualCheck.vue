<template>
  <div class="j1-tab-accrual">
    <!-- 顶部工具栏 -->
    <div class="ie-toolbar">
      <el-dropdown size="small" trigger="click">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate('accrual')">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData('accrual')">导出数据</el-dropdown-item>
            <el-dropdown-item @click="triggerImport">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>审计目标：复核各类薪酬计提基数、比例与应提金额，与实际计提对比，验证计提的完整性与准确性。</template>
    </el-alert>

    <!-- 审计过程（琥珀块） -->
    <div class="amber-context">
      <div class="amber-title">二、审计过程</div>
      <p>1. 了解企业应付职工薪酬各项目计算政策，对照职工提供服务情况和工资标准计算的职工薪酬（如工资），获取工资计算表，将工资标准与有关规定进行核对</p>
      <p>2. 对照国家规定计提基础和计提比例的职工薪酬（如失业保险金、工伤保险金等），检查是否按照规定的计提基础和比例计提</p>
      <p>3. 分析设定提存计划计提缴存情况，验查是否按照规定的计提基础即比例计提</p>
      <p>4. 对被审计单位按照历史经验数据和当期计划的应付职工薪酬（如加班工资标准），获取管理层进行估计的资料，分析其合理性</p>
    </div>

    <!-- 蓝色引导区 -->
    <div class="guide-area">
      <div class="guide-step"><span class="step-num">1</span>录入计提基数（名称/金额/索引）</div>
      <div class="guide-step"><span class="step-num">2</span>录入计提比例，系统测算应提金额</div>
      <div class="guide-step"><span class="step-num">3</span>录入实际计提数，系统计算差异</div>
    </div>

    <!-- (1) 短期薪酬 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">（1）短期薪酬</span>
          <el-tag size="small" type="info">{{ shortTermRows.length }} 项</el-tag>
        </div>
      </template>
      <AccrualTable :rows="shortTermRows" :is-readonly="isReadonly" @update="(id, f, v) => updateCell('shortTerm', id, f, v)" />
    </el-card>

    <!-- (2) 离职后福利 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">（2）离职后福利中设定提存计划、其他长期福利中符合设定提存条件的负债</span>
        </div>
      </template>
      <AccrualTable :rows="postEmploymentRows" :is-readonly="isReadonly" @update="(id, f, v) => updateCell('postEmployment', id, f, v)" />
    </el-card>

    <!-- 审计说明（5问题格式） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">三、审计说明</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="aiLoading" @click="generateAi">🤖 AI辅助</el-button>
        </div>
      </template>
      <div v-for="(q, idx) in auditQuestions" :key="idx" class="audit-question">
        <div class="q-label">{{ idx + 1 }}. {{ q.label }}</div>
        <el-input v-model="q.answer" type="textarea" :autosize="{ minRows: 2 }" :placeholder="q.placeholder" :disabled="isReadonly" @change="saveOpinion" />
      </div>
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">四、审计结论</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="aiConcLoading" @click="generateAiConc">🤖 AI辅助</el-button>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="审计结论..." :disabled="isReadonly" @change="saveOpinion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据CAS 9，短期薪酬应在职工提供服务的会计期间确认为负债并计入成本费用。</p>
        <p>2. 灰色底纹"应提金额"列为自动计算（计提基数金额×计提比例），"差异"列=实际计提-应提金额。</p>
        <p>3. 差异≠0自动标红，须在"差异原因"栏填写原因，"结论"栏给出判断。</p>
        <p>4. 计提合计应与J1-2明细表贷方发生额、J1-7分配检查表勾稽一致。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import AccrualTable from './AccrualTable.vue'
import { useJ1ImportExport } from '@/composables/workpaper/j1/useJ1ImportExport'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
  allResponses?: Map<string, any>
  isReadonly?: boolean
  saveImmediate?: (items: Array<any>) => Promise<void>
}>()

const isReadonly = computed(() => props.isReadonly ?? false)
const allResponsesRef = ref(props.allResponses || new Map())

// ─── 行模型 ────────────────────────────────────────────────────────────
export interface AccrualRow {
  id: string; label: string; indent: number
  baseName: string; baseAmount: number; baseIndex: string
  rate: number; estimated: number; actual: number
  diff: number; diffReason: string; conclusion: string
}

function recalcRow(r: AccrualRow): AccrualRow {
  const estimated = r.baseAmount * r.rate
  const diff = r.actual - estimated
  return { ...r, estimated, diff }
}

// ─── 默认行 ─────────────────────────────────────────────────────────────
const SHORT_TERM_DEFAULTS = [
  { label: '一、工资、奖金、津贴和补贴', indent: 0 },
  { label: '其中：1.工资', indent: 1 }, { label: '2.奖金', indent: 1 },
  { label: '3.津贴', indent: 1 }, { label: '4.补贴', indent: 1 },
  { label: '二、职工福利费', indent: 0 },
  { label: '三、社会保险费', indent: 0 },
  { label: '其中：1.医疗保险费', indent: 1 }, { label: '2.年金缴费', indent: 1 },
  { label: '3.工伤保险费', indent: 1 }, { label: '4.生育保险费', indent: 1 },
  { label: '四、住房公积金', indent: 0 },
  { label: '五、工会经费', indent: 0 },
  { label: '六、职工教育经费', indent: 0 },
  { label: '七、非货币性福利', indent: 0 },
  { label: '八、辞退福利（因解除劳动关系给予的补偿）', indent: 0 },
  { label: '九、职工奖励及福利基金（外资）', indent: 0 },
  { label: '十、以现金结算的股份支付', indent: 0 },
  { label: '十一、其他', indent: 0 },
]

const POST_EMPLOYMENT_DEFAULTS = [
  { label: '一、离职后福利', indent: 0 },
  { label: '其中：1.基本养老保险费', indent: 1 }, { label: '2.失业保险费', indent: 1 },
  { label: '3.企业年金缴费', indent: 1 }, { label: '4.其他', indent: 1 },
  { label: '二、其他长期职工福利', indent: 0 },
  { label: '其中：1.xxx', indent: 1 }, { label: '2.其他', indent: 1 },
]

function createRows(defaults: Array<{ label: string; indent: number }>): AccrualRow[] {
  return defaults.map((d, i) => recalcRow({
    id: `acr-${Date.now()}-${i}-${Math.random().toString(36).slice(2, 5)}`,
    label: d.label, indent: d.indent,
    baseName: '', baseAmount: 0, baseIndex: '', rate: 0,
    estimated: 0, actual: 0, diff: 0, diffReason: '', conclusion: '',
  }))
}

// ─── State ──────────────────────────────────────────────────────────────
const KEYS = { shortTerm: 'J1-6-short-term', postEmployment: 'J1-6-post-employment', questions: 'J1-6-questions', conclusion: 'J1-6-conclusion' }

const shortTermRows = ref<AccrualRow[]>(loadSection('shortTerm'))
const postEmploymentRows = ref<AccrualRow[]>(loadSection('postEmployment'))

function loadSection(section: 'shortTerm' | 'postEmployment'): AccrualRow[] {
  const key = section === 'shortTerm' ? KEYS.shortTerm : KEYS.postEmployment
  const raw = allResponsesRef.value.get(key)?.remark
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) return parsed.map((r: any) => recalcRow(r))
    } catch {}
  }
  return createRows(section === 'shortTerm' ? SHORT_TERM_DEFAULTS : POST_EMPLOYMENT_DEFAULTS)
}

function updateCell(section: 'shortTerm' | 'postEmployment', rowId: string, field: string, value: any) {
  if (isReadonly.value) return
  const rows = section === 'shortTerm' ? shortTermRows : postEmploymentRows
  const idx = rows.value.findIndex(r => r.id === rowId)
  if (idx === -1) return
  const row = { ...rows.value[idx], [field]: value }
  rows.value[idx] = recalcRow(row)
  scheduleSave()
}

let saveTimer: ReturnType<typeof setTimeout> | null = null
function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(persist, 1500)
}

function persist() {
  const items = [
    { item_id: KEYS.shortTerm, conclusion: null, remark: JSON.stringify(shortTermRows.value) },
    { item_id: KEYS.postEmployment, conclusion: null, remark: JSON.stringify(postEmploymentRows.value) },
    { item_id: KEYS.questions, conclusion: null, remark: JSON.stringify(auditQuestions.map(q => q.answer)) },
    { item_id: KEYS.conclusion, conclusion: null, remark: auditConclusion.value },
  ]
  items.forEach(it => allResponsesRef.value.set(it.item_id, it))
  const save = props.saveImmediate || (async () => {})
  save(items).catch(() => {})
}

// ─── 审计说明5问 ────────────────────────────────────────────────────────
const auditQuestions = reactive([
  { label: '公司对社会保险费的缴费方法', answer: '', placeholder: '计提，或按实列支' },
  { label: '国家关于计缴比例、计缴基数的规定', answer: '', placeholder: '' },
  { label: '相关部门为公司确定的计缴基数的依据', answer: '', placeholder: '' },
  { label: '公司未给员工计缴社会保险的情况', answer: '', placeholder: '' },
  { label: '其他需要说明的事项', answer: '', placeholder: '' },
])

// Load saved questions
const savedQ = allResponsesRef.value.get(KEYS.questions)?.remark
if (savedQ) {
  try {
    const arr = JSON.parse(savedQ)
    if (Array.isArray(arr)) arr.forEach((a: string, i: number) => { if (i < auditQuestions.length) auditQuestions[i].answer = a || '' })
  } catch {}
}

const auditConclusion = ref(allResponsesRef.value.get(KEYS.conclusion)?.remark || '')

function saveOpinion() { scheduleSave() }

// ─── 导入导出 ───────────────────────────────────────────────────────────
const { exportTemplate, exportData, importData } = useJ1ImportExport(props.wpId)
function triggerImport() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const f = (e.target as HTMLInputElement).files?.[0]
    if (!f) return
    const ok = await importData('accrual', f)
    if (!ok) return
    const res = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const arr = res.data?.data || res.data || []
    for (const it of arr) allResponsesRef.value.set(it.item_id, it)
    shortTermRows.value = loadSection('shortTerm')
    postEmploymentRows.value = loadSection('postEmployment')
    const sq = allResponsesRef.value.get(KEYS.questions)?.remark
    if (sq) {
      try {
        const a = JSON.parse(sq)
        if (Array.isArray(a)) a.forEach((x: string, i: number) => { if (i < auditQuestions.length) auditQuestions[i].answer = x || '' })
      } catch { /* */ }
    }
    auditConclusion.value = allResponsesRef.value.get(KEYS.conclusion)?.remark || ''
  }
  input.click()
}

// ─── AI ─────────────────────────────────────────────────────────────────
const aiLoading = ref(false)
const aiConcLoading = ref(false)

async function generateAi() {
  if (isReadonly.value) return
  aiLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'j1-6-note', prompt: '根据J1-6计提检查数据，回答5个审计说明问题。', context: {}, existingContent: auditQuestions.map(q => `${q.label}: ${q.answer}`).join('\n'),
    })
    const text = res.data?.data?.content || res.data?.content
    if (text) { auditQuestions[0].answer = text; saveOpinion(); ElMessage.success('AI生成完成') }
  } catch { ElMessage.warning('AI生成失败') }
  finally { aiLoading.value = false }
}

async function generateAiConc() {
  if (isReadonly.value) return
  aiConcLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'j1-6-conclusion', prompt: '根据J1-6计提检查数据和审计说明，生成审计结论。', context: {}, existingContent: auditConclusion.value,
    })
    const text = res.data?.data?.content || res.data?.content
    if (text) { auditConclusion.value = text; saveOpinion(); ElMessage.success('AI生成完成') }
  } catch { ElMessage.warning('AI生成失败') }
  finally { aiConcLoading.value = false }
}
</script>

<style scoped>
.j1-tab-accrual { padding: 12px; }
.ie-toolbar { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.j1-tab-accrual :deep(.el-table) { font-size: 13px !important; }
.j1-tab-accrual :deep(.el-table th), .j1-tab-accrual :deep(.el-table td) { font-size: 13px !important; padding: 4px 0 !important; }
.j1-tab-accrual :deep(.el-table th .cell) { white-space: normal !important; line-height: 1.3; }
.audit-objective { margin-bottom: 10px; }
.amber-context { border-left: 3px solid #e6a23c; background: #fdf6ec; padding: 10px 14px; border-radius: 4px; margin-bottom: 12px; font-size: 13px; color: #606266; line-height: 1.7; }
.amber-context .amber-title { font-weight: 600; color: #303133; margin-bottom: 4px; }
.amber-context p { margin: 3px 0; }
.guide-area { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 12px; padding: 10px; background: linear-gradient(135deg, #ecf5ff, #f0f9ff); border-radius: 6px; }
.guide-step { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.step-num { width: 20px; height: 20px; border-radius: 50%; background: #409eff; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 600; flex-shrink: 0; }
.section-card { margin-bottom: 12px; }
.section-card :deep(.el-card__header) { padding: 8px 12px; }
.section-card :deep(.el-card__body) { padding: 12px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-title { font-weight: 600; font-size: 13px; }
.audit-question { margin-bottom: 12px; }
.audit-question:last-child { margin-bottom: 0; }
.q-label { font-size: 13px; font-weight: 500; color: #303133; margin-bottom: 4px; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
