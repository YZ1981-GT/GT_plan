<template>
  <div class="i2-project-detail">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2-7 研发项目构成明细表（73列5区段）</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">
          复核
        </el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：核查各研发项目费用构成的完整性与归集准确性，确认材料费、人工费、折旧摊销及其他费用按项目准确归集并与明细表勾稽一致。" />

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 按研发项目分行归集各费用性质（材料/人工/折旧摊销/其他），核对各区段小计与合计计算准确；</p>
        <p>2. 将本表费用合计与 I2-2 研发支出明细表交叉验证，差异为零方可通过；</p>
        <p>3. 依据 CAS6《无形资产》及研发费用相关规定。</p>
      </div>
    </details>

    <!-- 索引工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <GtIndexChip value="wp:I2" :context-project-id="props.projectId" />
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>本表按研发项目分行，按费用性质分5区段（基础/材料费/人工费/折旧摊销/其他费用），合计应与I2-2明细表交叉验证一致。</p>
    </div>

    <!-- 5区段 Tabs -->
    <el-tabs v-model="activeSegment" type="border-card" class="segment-tabs">
      <el-tab-pane label="基础信息" name="basic">
        <el-table :data="rows" border size="small" class="detail-table" max-height="520">
          <el-table-column type="index" label="#" width="40" fixed />
          <el-table-column prop="projectName" label="项目名称" min-width="180" fixed>
            <template #default="{ row }">
              <el-input v-model="row.projectName" size="small" placeholder="项目名称" />
            </template>
          </el-table-column>
          <el-table-column prop="projectCode" label="项目编号" min-width="120">
            <template #default="{ row }">
              <el-input v-model="row.projectCode" size="small" placeholder="编号" />
            </template>
          </el-table-column>
          <el-table-column prop="startDate" label="立项日期" min-width="130">
            <template #default="{ row }">
              <el-date-picker v-model="row.startDate" type="date" size="small" value-format="YYYY-MM-DD" placeholder="立项日" style="width:100%" />
            </template>
          </el-table-column>
          <el-table-column prop="stage" label="阶段" min-width="100">
            <template #default="{ row }">
              <el-select v-model="row.stage" size="small" placeholder="阶段" style="width:100%">
                <el-option label="研究" value="研究" />
                <el-option label="开发" value="开发" />
                <el-option label="完成" value="完成" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column prop="totalAmount" label="费用合计" min-width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtNum(row.totalAmount) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="材料费" name="material">
        <el-table :data="rows" border size="small" class="detail-table" max-height="520">
          <el-table-column type="index" label="#" width="40" fixed />
          <el-table-column prop="projectName" label="项目名称" min-width="160" fixed />
          <el-table-column prop="materialDirect" label="直接材料" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.materialDirect" size="small" :controls="false" :precision="2" @change="recalcRow(row)" style="width:100%" />
            </template>
          </el-table-column>
          <el-table-column prop="materialAux" label="辅助材料" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.materialAux" size="small" :controls="false" :precision="2" @change="recalcRow(row)" style="width:100%" />
            </template>
          </el-table-column>
          <el-table-column prop="materialFuel" label="燃料动力" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.materialFuel" size="small" :controls="false" :precision="2" @change="recalcRow(row)" style="width:100%" />
            </template>
          </el-table-column>
          <el-table-column prop="materialSubtotal" label="材料费小计" min-width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtNum(row.materialSubtotal) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="人工费" name="labor">
        <el-table :data="rows" border size="small" class="detail-table" max-height="520">
          <el-table-column type="index" label="#" width="40" fixed />
          <el-table-column prop="projectName" label="项目名称" min-width="160" fixed />
          <el-table-column prop="laborSalary" label="工资薪金" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.laborSalary" size="small" :controls="false" :precision="2" @change="recalcRow(row)" style="width:100%" />
            </template>
          </el-table-column>
          <el-table-column prop="laborBonus" label="奖金津贴" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.laborBonus" size="small" :controls="false" :precision="2" @change="recalcRow(row)" style="width:100%" />
            </template>
          </el-table-column>
          <el-table-column prop="laborInsurance" label="五险一金" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.laborInsurance" size="small" :controls="false" :precision="2" @change="recalcRow(row)" style="width:100%" />
            </template>
          </el-table-column>
          <el-table-column prop="laborSubtotal" label="人工费小计" min-width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtNum(row.laborSubtotal) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="折旧摊销" name="depreciation">
        <el-table :data="rows" border size="small" class="detail-table" max-height="520">
          <el-table-column type="index" label="#" width="40" fixed />
          <el-table-column prop="projectName" label="项目名称" min-width="160" fixed />
          <el-table-column prop="depEquipment" label="设备折旧" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.depEquipment" size="small" :controls="false" :precision="2" @change="recalcRow(row)" style="width:100%" />
            </template>
          </el-table-column>
          <el-table-column prop="depBuilding" label="房屋折旧" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.depBuilding" size="small" :controls="false" :precision="2" @change="recalcRow(row)" style="width:100%" />
            </template>
          </el-table-column>
          <el-table-column prop="depIntangible" label="无形摊销" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.depIntangible" size="small" :controls="false" :precision="2" @change="recalcRow(row)" style="width:100%" />
            </template>
          </el-table-column>
          <el-table-column prop="depSubtotal" label="折旧摊销小计" min-width="130" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtNum(row.depSubtotal) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="其他费用" name="other">
        <el-table :data="rows" border size="small" class="detail-table" max-height="520">
          <el-table-column type="index" label="#" width="40" fixed />
          <el-table-column prop="projectName" label="项目名称" min-width="160" fixed />
          <el-table-column prop="otherDesign" label="设计费" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.otherDesign" size="small" :controls="false" :precision="2" @change="recalcRow(row)" style="width:100%" />
            </template>
          </el-table-column>
          <el-table-column prop="otherTest" label="检测费" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.otherTest" size="small" :controls="false" :precision="2" @change="recalcRow(row)" style="width:100%" />
            </template>
          </el-table-column>
          <el-table-column prop="otherTravel" label="差旅费" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.otherTravel" size="small" :controls="false" :precision="2" @change="recalcRow(row)" style="width:100%" />
            </template>
          </el-table-column>
          <el-table-column prop="otherMisc" label="其他" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.otherMisc" size="small" :controls="false" :precision="2" @change="recalcRow(row)" style="width:100%" />
            </template>
          </el-table-column>
          <el-table-column prop="otherSubtotal" label="其他费用小计" min-width="130" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtNum(row.otherSubtotal) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 合计行 -->
    <div class="totals-bar">
      <span class="totals-label">合计：</span>
      <el-tag type="info" size="small">材料费 {{ fmtNum(totals.material) }}</el-tag>
      <el-tag type="info" size="small">人工费 {{ fmtNum(totals.labor) }}</el-tag>
      <el-tag type="info" size="small">折旧摊销 {{ fmtNum(totals.depreciation) }}</el-tag>
      <el-tag type="info" size="small">其他费用 {{ fmtNum(totals.other) }}</el-tag>
      <el-tag type="primary" size="small">总计 {{ fmtNum(totals.total) }}</el-tag>
      <!-- 交叉验证 I2-2 -->
      <el-tag v-if="crossValidateI2_2Diff !== 0" type="danger" size="small">
        ⚠ 与I2-2差异 {{ fmtNum(crossValidateI2_2Diff) }}
      </el-tag>
      <el-tag v-else type="success" size="small">✓ I2-2一致</el-tag>
    </div>

    <!-- 行操作 -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain @click="handleAddRow">+ 新增行</el-button>
      <el-button size="small" type="success" @click="handleSave">保存</el-button>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span>审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly"
        :autosize="{ minRows: 5 }" placeholder="记录检查过程、发现的问题及处理..." @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span>审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly"
        :autosize="{ minRows: 3 }" placeholder="填写审计结论..." @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { calcSubtotal } from '../../composables/useI2FormulaEngine'

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  'save': []
  'navigate-sheet': [sheetName: string]
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

// ─── Types ───────────────────────────────────────────────────────────────────

interface ProjectDetailRow {
  rowId: string
  projectName: string
  projectCode: string
  startDate: string
  stage: string
  // 材料费
  materialDirect: number
  materialAux: number
  materialFuel: number
  materialSubtotal: number
  // 人工费
  laborSalary: number
  laborBonus: number
  laborInsurance: number
  laborSubtotal: number
  // 折旧摊销
  depEquipment: number
  depBuilding: number
  depIntangible: number
  depSubtotal: number
  // 其他费用
  otherDesign: number
  otherTest: number
  otherTravel: number
  otherMisc: number
  otherSubtotal: number
  // 合计
  totalAmount: number
}

// ─── State ───────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'I2-7-rows'
const activeSegment = ref('basic')
const rows = ref<ProjectDetailRow[]>([])

// ─── Load ────────────────────────────────────────────────────────────────────

function loadData() {
  const raw = props.allResponses.get(STORAGE_KEY)
  if (!raw) { rows.value = []; return }
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : (raw.remark ? JSON.parse(raw.remark) : raw)
    if (Array.isArray(parsed)) {
      rows.value = parsed.map(normalizeRow)
    }
  } catch { rows.value = [] }
}

// ─── 审计说明 / 审计结论 ───
const AUDIT_NOTE_KEY = 'I2-7-audit-note'
const AUDIT_CONCLUSION_KEY = 'I2-7-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function readRemark(key: string): string {
  const raw = props.allResponses.get(key)
  if (raw == null) return ''
  return typeof raw === 'string' ? raw : (raw.remark ?? '')
}
function hydrateAudit() { auditNote.value = readRemark(AUDIT_NOTE_KEY); auditConclusion.value = readRemark(AUDIT_CONCLUSION_KEY) }
function saveAuditNote(val: string) { auditNote.value = val; void props.saveResponse('I2-7', { [AUDIT_NOTE_KEY]: val }) }
function saveAuditConclusion(val: string) { auditConclusion.value = val; void props.saveResponse('I2-7', { [AUDIT_CONCLUSION_KEY]: val }) }

watch(() => props.allResponses, () => { loadData(); hydrateAudit() }, { immediate: true })
onMounted(hydrateAudit)

function normalizeRow(r: any): ProjectDetailRow {
  const row: ProjectDetailRow = {
    rowId: r.rowId || `r-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    projectName: r.projectName || '',
    projectCode: r.projectCode || '',
    startDate: r.startDate || '',
    stage: r.stage || '',
    materialDirect: Number(r.materialDirect) || 0,
    materialAux: Number(r.materialAux) || 0,
    materialFuel: Number(r.materialFuel) || 0,
    materialSubtotal: 0,
    laborSalary: Number(r.laborSalary) || 0,
    laborBonus: Number(r.laborBonus) || 0,
    laborInsurance: Number(r.laborInsurance) || 0,
    laborSubtotal: 0,
    depEquipment: Number(r.depEquipment) || 0,
    depBuilding: Number(r.depBuilding) || 0,
    depIntangible: Number(r.depIntangible) || 0,
    depSubtotal: 0,
    otherDesign: Number(r.otherDesign) || 0,
    otherTest: Number(r.otherTest) || 0,
    otherTravel: Number(r.otherTravel) || 0,
    otherMisc: Number(r.otherMisc) || 0,
    otherSubtotal: 0,
    totalAmount: 0,
  }
  recalcRow(row)
  return row
}

// ─── Formulas ────────────────────────────────────────────────────────────────

function recalcRow(row: ProjectDetailRow) {
  row.materialSubtotal = calcSubtotal([row.materialDirect, row.materialAux, row.materialFuel])
  row.laborSubtotal = calcSubtotal([row.laborSalary, row.laborBonus, row.laborInsurance])
  row.depSubtotal = calcSubtotal([row.depEquipment, row.depBuilding, row.depIntangible])
  row.otherSubtotal = calcSubtotal([row.otherDesign, row.otherTest, row.otherTravel, row.otherMisc])
  row.totalAmount = calcSubtotal([row.materialSubtotal, row.laborSubtotal, row.depSubtotal, row.otherSubtotal])
}

// ─── Computed: Totals ────────────────────────────────────────────────────────

const totals = computed(() => ({
  material: calcSubtotal(rows.value.map(r => r.materialSubtotal)),
  labor: calcSubtotal(rows.value.map(r => r.laborSubtotal)),
  depreciation: calcSubtotal(rows.value.map(r => r.depSubtotal)),
  other: calcSubtotal(rows.value.map(r => r.otherSubtotal)),
  total: calcSubtotal(rows.value.map(r => r.totalAmount)),
}))

// Cross-validate with I2-2
const crossValidateI2_2Diff = computed(() => {
  const i2_2Raw = props.allResponses.get('I2-2-rows')
  if (!i2_2Raw) return 0
  try {
    const parsed = typeof i2_2Raw === 'string' ? JSON.parse(i2_2Raw) : (i2_2Raw.remark ? JSON.parse(i2_2Raw.remark) : i2_2Raw)
    if (Array.isArray(parsed)) {
      const i2_2Total = parsed.reduce((sum: number, r: any) => sum + (Number(r.totalInvestment) || 0), 0)
      return Math.round((totals.value.total - i2_2Total) * 100) / 100
    }
  } catch { /* ignore */ }
  return 0
})

// ─── Actions ─────────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入研发项目名称', '新增项目行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    if (value?.trim()) {
      const newRow = normalizeRow({ projectName: value.trim() })
      rows.value.push(newRow)
      ElMessage.success(`已添加：${value.trim()}`)
    }
  } catch { /* cancelled */ }
}

async function handleSave() {
  const persistData = rows.value.map(r => ({
    rowId: r.rowId, projectName: r.projectName, projectCode: r.projectCode,
    startDate: r.startDate, stage: r.stage,
    materialDirect: r.materialDirect, materialAux: r.materialAux, materialFuel: r.materialFuel,
    laborSalary: r.laborSalary, laborBonus: r.laborBonus, laborInsurance: r.laborInsurance,
    depEquipment: r.depEquipment, depBuilding: r.depBuilding, depIntangible: r.depIntangible,
    otherDesign: r.otherDesign, otherTest: r.otherTest, otherTravel: r.otherTravel, otherMisc: r.otherMisc,
  }))
  await props.saveResponse('I2-7', { [STORAGE_KEY]: JSON.stringify(persistData) })
  emit('save')
  ElMessage.success('研发项目构成明细表已保存')
}

function handleReview() { openReviewDialog('I2-7-研发项目构成明细') }

function fmtNum(v: number): string {
  if (v == null || isNaN(v)) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i2-project-detail { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6; }
.segment-tabs { margin-bottom: 12px; }
.detail-table { font-size: var(--wp-font-size, 13px); }
.formula-cell { color: #6366f1; font-weight: 500; border-bottom: 1px dashed #a5b4fc; cursor: help; }
.totals-bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 10px 0; border-top: 1px solid #e5e7eb; margin-top: 8px; }
.totals-label { font-weight: 600; color: #374151; }
.table-actions { display: flex; gap: 8px; margin-top: 12px; }
.objective-alert { margin-bottom: 12px; }
.guidance-details { margin-bottom: 12px; font-size: 12px; color: var(--el-text-color-secondary); background: #f9fafb; border: 1px solid #ebeef5; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 600; color: #374151; }
.guidance-details .guidance-content { margin-top: 8px; line-height: 1.7; }
.guidance-details .guidance-content p { margin: 0 0 4px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 10px; }
.tab-toolbar .toolbar-right { display: flex; align-items: center; gap: 8px; }
.audit-note-card, .audit-conclusion-card { margin-top: 16px; }
</style>
