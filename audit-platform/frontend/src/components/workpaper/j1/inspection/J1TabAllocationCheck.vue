<template>
  <div class="j1-tab-allocation">
    <!-- 顶部工具栏 -->
    <div class="ie-toolbar">
      <el-dropdown size="small" trigger="click">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate('allocation')">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData('allocation')">导出数据</el-dropdown-item>
            <el-dropdown-item @click="triggerImport">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>审计目标：验证应付职工薪酬按受益对象在各费用/成本科目间分配的合理性与完整性，确保分配合计与实际计提数一致。</template>
    </el-alert>

    <!-- 审计过程（4问题填空） -->
    <div class="amber-context">
      <div class="amber-title">二、审计过程 — 被审计单位职工薪酬计提分配政策</div>
      <div v-for="(q, idx) in policyQuestions" :key="idx" class="policy-question">
        <span class="q-label">（{{ idx + 1 }}）{{ q.label }}</span>
        <el-input v-model="q.answer" size="small" :placeholder="q.placeholder" :disabled="isReadonly" @change="scheduleSave" />
      </div>
    </div>

    <!-- 分配表（3分区合并展示） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">应付职工薪酬成本、费用分配情况</span>
          <GtIndexChip value="wp:J1-6" :context-project-id="projectId" />
        </div>
      </template>
      <el-table :data="allRows" border size="small" class="alloc-table"
        :row-class-name="({ row }) => row.isSection ? 'section-row' : ''">
        <el-table-column label="项目名称" min-width="160" fixed>
          <template #default="{ row }">
            <span :style="{ paddingLeft: row.indent * 14 + 'px', fontWeight: row.isSection ? 600 : 400 }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="生产成本" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isSection" :model-value="row.productionCost" :controls="false" size="small" style="width:88px" @change="(v: number) => updateCell(row.id, 'productionCost', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.productionCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="制造费用" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isSection" :model-value="row.manufacturing" :controls="false" size="small" style="width:88px" @change="(v: number) => updateCell(row.id, 'manufacturing', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.manufacturing) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="管理费用" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isSection" :model-value="row.adminExpense" :controls="false" size="small" style="width:88px" @change="(v: number) => updateCell(row.id, 'adminExpense', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.adminExpense) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="销售费用" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isSection" :model-value="row.sellingExpense" :controls="false" size="small" style="width:88px" @change="(v: number) => updateCell(row.id, 'sellingExpense', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.sellingExpense) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="其他" width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isSection" :model-value="row.otherExpense" :controls="false" size="small" style="width:78px" @change="(v: number) => updateCell(row.id, 'otherExpense', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.otherExpense) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期合计" width="110" align="right" class-name="calc-col">
          <template #default="{ row }">
            <el-tooltip content="本期合计 = 生产成本+制造费用+管理费用+销售费用+其他" placement="top">
              <span class="formula-cell">{{ fmtAmt(row.rowTotal) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="本期实际计提数" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isSection" :model-value="row.actualAccrual" :controls="false" size="small" style="width:98px" @change="(v: number) => updateCell(row.id, 'actualAccrual', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.actualAccrual) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期差异" width="100" align="right" class-name="calc-col">
          <template #default="{ row }">
            <el-tooltip content="差异 = 实际计提 - 本期合计" placement="top">
              <span class="formula-cell" :class="{ 'text-danger': row.diff !== 0 }">{{ fmtAmt(row.diff) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="差异原因" width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly && !row.isSection" :model-value="row.diffReason" size="small" @change="(v: string) => updateCell(row.id, 'diffReason', v)" />
            <span v-else>{{ row.diffReason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结论" width="90">
          <template #default="{ row }">
            <el-select v-if="!isReadonly && !row.isSection" :model-value="row.conclusion" size="small" clearable @change="(v: string) => updateCell(row.id, 'conclusion', v)">
              <el-option label="合理" value="合理" />
              <el-option label="需调整" value="需调整" />
            </el-select>
            <span v-else>{{ row.conclusion || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计说明与结论 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">三、审计说明</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="aiLoading" @click="generateAi('note')">🤖 AI辅助</el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" placeholder="审计说明..." :disabled="isReadonly" @change="scheduleSave" />
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">四、审计结论</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="aiLoading" @click="generateAi('conclusion')">🤖 AI辅助</el-button>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2 }" placeholder="审计结论..." :disabled="isReadonly" @change="scheduleSave" />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 了解被审计单位工资核算、计提及支付政策及流程，关注是否符合CAS 9规定。</p>
        <p>2. 了解发放标准（高管、销售人员、技术人员、业务人员、生产人员、行政人员），发薪周期、年度及季度奖金计提原则。</p>
        <p>3. 关注职工薪酬的发放方式和发放频率。</p>
        <p>4. 了解是否存在同一员工同时承担技术服务、研发、销售等多项职责的情况，关注此种情况下人工成本分配准确性。</p>
        <p>5. 检查分配方法与上年是否一致。分配原则：(1)应由生产产品、提供劳务负担的→计入产品成本或劳务成本；(2)应由在建工程、无形资产负担的→计入建造固定资产或无形资产；(3)其他→计入当期损益。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
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
interface AllocRow {
  id: string; label: string; indent: number; isSection: boolean
  productionCost: number; manufacturing: number; adminExpense: number
  sellingExpense: number; otherExpense: number
  rowTotal: number; actualAccrual: number; diff: number
  diffReason: string; conclusion: string
}

function recalcRow(r: AllocRow): AllocRow {
  const rowTotal = r.productionCost + r.manufacturing + r.adminExpense + r.sellingExpense + r.otherExpense
  const diff = r.actualAccrual - rowTotal
  return { ...r, rowTotal, diff }
}

// ─── 默认行 ─────────────────────────────────────────────────────────────
const DEFAULT_ROWS: Array<{ label: string; indent: number; isSection: boolean }> = [
  { label: '(1)短期薪酬', indent: 0, isSection: true },
  { label: '工资、奖金、津贴和补贴', indent: 1, isSection: false },
  { label: '职工福利费', indent: 1, isSection: false },
  { label: '社会保险费', indent: 1, isSection: false },
  { label: '住房公积金', indent: 1, isSection: false },
  { label: '工会经费', indent: 1, isSection: false },
  { label: '职工教育经费', indent: 1, isSection: false },
  { label: '短期带薪缺勤', indent: 1, isSection: false },
  { label: '短期利润分享计划', indent: 1, isSection: false },
  { label: '非货币性福利', indent: 1, isSection: false },
  { label: '(2)离职后福利中设定提存计划', indent: 0, isSection: true },
  { label: '离职后福利', indent: 1, isSection: false },
  { label: '其他长期职工福利', indent: 1, isSection: false },
  { label: '(3)一年内支付的辞退福利', indent: 0, isSection: false },
  { label: '(4)其他', indent: 0, isSection: false },
]

function createRows(defaults: typeof DEFAULT_ROWS): AllocRow[] {
  return defaults.map((d, i) => recalcRow({
    id: `alloc-${Date.now()}-${i}-${Math.random().toString(36).slice(2, 5)}`,
    label: d.label, indent: d.indent, isSection: d.isSection,
    productionCost: 0, manufacturing: 0, adminExpense: 0,
    sellingExpense: 0, otherExpense: 0,
    rowTotal: 0, actualAccrual: 0, diff: 0,
    diffReason: '', conclusion: '',
  }))
}

// ─── State ──────────────────────────────────────────────────────────────
const KEYS = { rows: 'J1-7-alloc-rows', policy: 'J1-7-policy', note: 'J1-7-note', conclusion: 'J1-7-conclusion' }

const allRows = ref<AllocRow[]>(loadRows())

function loadRows(): AllocRow[] {
  const raw = allResponsesRef.value.get(KEYS.rows)?.remark
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) return parsed.map((r: any) => recalcRow(r))
    } catch {}
  }
  return createRows(DEFAULT_ROWS)
}

function updateCell(rowId: string, field: string, value: any) {
  if (isReadonly.value) return
  const idx = allRows.value.findIndex(r => r.id === rowId)
  if (idx === -1) return
  const row = { ...allRows.value[idx], [field]: typeof value === 'string' ? value : Number(value) || 0 }
  allRows.value[idx] = recalcRow(row as AllocRow)
  scheduleSave()
}

// ─── 审计过程4问题 ──────────────────────────────────────────────────────
const policyQuestions = reactive([
  { label: '工资总额的组成部分', answer: '', placeholder: '基本工资+绩效奖金+津贴+补贴' },
  { label: '公司是否执行工效挂钩', answer: '', placeholder: '是/否' },
  { label: '福利政策', answer: '', placeholder: '' },
  { label: '职工薪酬核算、计提分配及支付政策及流程', answer: '', placeholder: '' },
])

const savedPolicy = allResponsesRef.value.get(KEYS.policy)?.remark
if (savedPolicy) {
  try {
    const arr = JSON.parse(savedPolicy)
    if (Array.isArray(arr)) arr.forEach((a: string, i: number) => { if (i < policyQuestions.length) policyQuestions[i].answer = a || '' })
  } catch {}
}

// ─── 审计说明/结论 ──────────────────────────────────────────────────────
const auditNote = ref(allResponsesRef.value.get(KEYS.note)?.remark || '')
const auditConclusion = ref(allResponsesRef.value.get(KEYS.conclusion)?.remark || '')

// ─── Save ───────────────────────────────────────────────────────────────
let saveTimer: ReturnType<typeof setTimeout> | null = null
function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(persist, 1500)
}

function persist() {
  const items = [
    { item_id: KEYS.rows, conclusion: null, remark: JSON.stringify(allRows.value) },
    { item_id: KEYS.policy, conclusion: null, remark: JSON.stringify(policyQuestions.map(q => q.answer)) },
    { item_id: KEYS.note, conclusion: null, remark: auditNote.value },
    { item_id: KEYS.conclusion, conclusion: null, remark: auditConclusion.value },
  ]
  items.forEach(it => allResponsesRef.value.set(it.item_id, it))
  const save = props.saveImmediate || (async () => {})
  save(items).catch(() => {})
}

// ─── 导入导出 ───────────────────────────────────────────────────────────
const { exportTemplate, exportData, importData } = useJ1ImportExport(props.wpId)
function triggerImport() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const f = (e.target as HTMLInputElement).files?.[0]
    if (!f) return
    const ok = await importData('allocation', f)
    if (!ok) return
    const res = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const arr = res.data?.data || res.data || []
    for (const it of arr) allResponsesRef.value.set(it.item_id, it)
    allRows.value = loadRows()
    const sp = allResponsesRef.value.get(KEYS.policy)?.remark
    if (sp) {
      try {
        const a = JSON.parse(sp)
        if (Array.isArray(a)) a.forEach((x: string, i: number) => { if (i < policyQuestions.length) policyQuestions[i].answer = x || '' })
      } catch { /* */ }
    }
    auditNote.value = allResponsesRef.value.get(KEYS.note)?.remark || ''
    auditConclusion.value = allResponsesRef.value.get(KEYS.conclusion)?.remark || ''
  }
  input.click()
}

// ─── AI ─────────────────────────────────────────────────────────────────
const aiLoading = ref(false)
async function generateAi(section: 'note' | 'conclusion') {
  if (isReadonly.value) return
  aiLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `j1-7-${section}`,
      prompt: section === 'note' ? '根据J1-7分配检查数据生成审计说明。' : '根据J1-7分配检查数据和审计说明生成审计结论。',
      context: {}, existingContent: section === 'note' ? auditNote.value : auditConclusion.value,
    })
    const text = res.data?.data?.content || res.data?.content
    if (text) {
      if (section === 'note') auditNote.value = text; else auditConclusion.value = text
      scheduleSave(); ElMessage.success('AI生成完成')
    }
  } catch { ElMessage.warning('AI生成失败') }
  finally { aiLoading.value = false }
}

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped>
.j1-tab-allocation { padding: 12px; }
.ie-toolbar { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.j1-tab-allocation :deep(.el-table) { font-size: 13px !important; }
.j1-tab-allocation :deep(.el-table th), .j1-tab-allocation :deep(.el-table td) { font-size: 13px !important; padding: 4px 0 !important; }
.j1-tab-allocation :deep(.el-table th .cell) { white-space: normal !important; line-height: 1.3; }
.alloc-table { font-size: 13px; }
.audit-objective { margin-bottom: 10px; }
.amber-context { border-left: 3px solid #e6a23c; background: #fdf6ec; padding: 12px 14px; border-radius: 4px; margin-bottom: 12px; font-size: 13px; color: #606266; }
.amber-context .amber-title { font-weight: 600; color: #303133; margin-bottom: 8px; }
.policy-question { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.policy-question .q-label { min-width: 200px; font-size: 13px; color: #303133; flex-shrink: 0; }
.section-card { margin-bottom: 12px; }
.section-card :deep(.el-card__header) { padding: 8px 12px; }
.section-card :deep(.el-card__body) { padding: 12px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-title { font-weight: 600; font-size: 13px; }
:deep(.calc-col) { background-color: #f5f7fa !important; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; color: #606266; }
.text-danger { color: #f56c6c !important; font-weight: 600; }
:deep(.section-row) { background: #f0f5ff !important; }
:deep(.section-row td) { font-weight: 600; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 3px 0; }
</style>
