<template>
  <div class="i2-staff-check">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2-9 研发人员认定检查表</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">
          复核
        </el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：核查研发人员认定的合理性与真实性，确认认定人员确系从事研发活动的岗位并具备相应资质。" />

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 逐人核对岗位、学历/职称/资质是否满足研发岗位要求，剔除行政、销售等非研发人员；</p>
        <p>2. 核查人员实际参与的研发项目是否属实，与工时记录、项目立项名单交叉印证；</p>
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
      <p>核查研发人员认定的合理性：验证人员是否确系研发岗位，资质是否满足研发要求，参与项目是否属实。</p>
    </div>

    <!-- 数据表 -->
    <el-table :data="rows" border size="small" class="check-table" max-height="500">
      <el-table-column type="index" label="#" width="40" fixed />
      <el-table-column prop="staffName" label="姓名" min-width="100">
        <template #default="{ row }">
          <el-input v-model="row.staffName" size="small" placeholder="姓名" />
        </template>
      </el-table-column>
      <el-table-column prop="position" label="岗位" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.position" size="small" placeholder="岗位" />
        </template>
      </el-table-column>
      <el-table-column prop="qualification" label="资质" min-width="140">
        <template #default="{ row }">
          <el-input v-model="row.qualification" size="small" placeholder="学历/职称/资质" />
        </template>
      </el-table-column>
      <el-table-column prop="projects" label="参与项目" min-width="180">
        <template #default="{ row }">
          <el-input v-model="row.projects" size="small" placeholder="参与的研发项目" />
        </template>
      </el-table-column>
      <el-table-column label="📎" width="50" align="center">
        <template #default="{ $index }">
          <el-button size="small" text @click="handleOcr($index)">📎</el-button>
        </template>
      </el-table-column>
      <el-table-column prop="conclusion" label="认定结论" min-width="120">
        <template #default="{ row }">
          <el-select v-model="row.conclusion" size="small" placeholder="结论" style="width:100%">
            <el-option label="认定为研发人员" value="认定为研发人员" />
            <el-option label="不予认定" value="不予认定" />
            <el-option label="待核实" value="待核实" />
          </el-select>
        </template>
      </el-table-column>
    </el-table>

    <!-- 行操作 -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain @click="handleAddRow">+ 新增行</el-button>
      <el-button size="small" type="warning" plain @click="handleSampling">抽凭引擎</el-button>
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
import { ref, watch, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
  isReadonly?: boolean
}>()

const emit = defineEmits<{ 'save': []; 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

interface StaffRow {
  staffName: string; position: string; qualification: string
  projects: string; conclusion: string
}

const STORAGE_KEY = 'I2-9-rows'
const rows = ref<StaffRow[]>([])

function loadData() {
  const raw = props.allResponses.get(STORAGE_KEY)
  if (!raw) { rows.value = []; return }
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : (raw.remark ? JSON.parse(raw.remark) : raw)
    if (Array.isArray(parsed)) rows.value = parsed.map((r: any) => ({
      staffName: r.staffName || '', position: r.position || '',
      qualification: r.qualification || '', projects: r.projects || '',
      conclusion: r.conclusion || '',
    }))
  } catch { rows.value = [] }
}

// ─── 审计说明 / 审计结论 ───
const AUDIT_NOTE_KEY = 'I2-9-audit-note'
const AUDIT_CONCLUSION_KEY = 'I2-9-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function readRemark(key: string): string {
  const raw = props.allResponses.get(key)
  if (raw == null) return ''
  return typeof raw === 'string' ? raw : (raw.remark ?? '')
}
function hydrateAudit() { auditNote.value = readRemark(AUDIT_NOTE_KEY); auditConclusion.value = readRemark(AUDIT_CONCLUSION_KEY) }
function saveAuditNote(val: string) { auditNote.value = val; void props.saveResponse('I2-9', { [AUDIT_NOTE_KEY]: val }) }
function saveAuditConclusion(val: string) { auditConclusion.value = val; void props.saveResponse('I2-9', { [AUDIT_CONCLUSION_KEY]: val }) }

watch(() => props.allResponses, () => { loadData(); hydrateAudit() }, { immediate: true })
onMounted(hydrateAudit)

function handleAddRow() {
  rows.value.push({ staffName: '', position: '', qualification: '', projects: '', conclusion: '' })
}

async function handleSave() {
  await props.saveResponse('I2-9', { [STORAGE_KEY]: JSON.stringify(rows.value) })
  emit('save'); ElMessage.success('研发人员认定检查表已保存')
}

function handleOcr(idx: number) { ElMessage.info('OCR识别人员证明材料...') }
function handleSampling() { ElMessage.info('抽凭引擎(GtVoucherSamplingEngine)加载中...') }
function handleReview() { openReviewDialog('I2-9-研发人员认定检查') }
</script>

<style scoped>
.i2-staff-check { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6; }
.check-table { font-size: var(--wp-font-size, 13px); }
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
