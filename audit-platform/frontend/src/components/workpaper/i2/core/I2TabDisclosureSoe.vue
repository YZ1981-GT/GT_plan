<template>
  <div class="i2-disclosure-soe">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2 附注披露（国有企业）— 17行×8列</span>
      <div class="section-actions">
        <el-button size="small" type="info" text @click="handleAutoFill">
          自动取数
        </el-button>
        <el-button size="small" type="default" text @click="handleReview">
          复核
        </el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：核查国有企业开发支出附注披露的完整性与准确性，确认各研发项目期初、资本化/费用化增加、转无形/转费用减少及期末余额的披露与审定表I2-1、明细表I2-2勾稽一致。" />

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 逐项目核对期初余额、本期增加（资本化/费用化转入）、本期减少（转无形/转费用）及期末余额；</p>
        <p>2. 国企格式较上市版更细致，须区分资本化增加与费用化转入、转无形资产与转费用的变动方向；</p>
        <p>3. 复核附注披露口径与审定表I2-1、明细表I2-2勾稽一致，防止漏披或错披；</p>
        <p>4. 依据 CAS6《无形资产》及企业会计准则披露要求核查开发支出附注列报。</p>
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
      <p>国有企业开发支出附注：区分资本化增加/费用化转入/转无形/转费用等变动方向。数据应与审定表I2-1及明细表I2-2一致。国企格式较上市版更细致。</p>
    </div>

    <!-- 附注表格（17行×8列） -->
    <el-table :data="rows" border size="small" class="disclosure-table" max-height="480">
      <el-table-column type="index" label="#" width="40" fixed />
      <el-table-column prop="name" label="项目" min-width="160" fixed>
        <template #default="{ row }">
          <el-input v-model="row.name" size="small" placeholder="项目名称" />
        </template>
      </el-table-column>
      <el-table-column prop="beginBalance" label="期初余额" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.beginBalance" size="small" :controls="false" :precision="2" style="width:100%" />
        </template>
      </el-table-column>
      <el-table-column prop="increaseCapitalized" label="本期增加-资本化" min-width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.increaseCapitalized" size="small" :controls="false" :precision="2" style="width:100%" />
        </template>
      </el-table-column>
      <el-table-column prop="increaseExpensed" label="本期增加-费用化转入" min-width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.increaseExpensed" size="small" :controls="false" :precision="2" style="width:100%" />
        </template>
      </el-table-column>
      <el-table-column prop="decreaseToIntangible" label="本期减少-转无形" min-width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.decreaseToIntangible" size="small" :controls="false" :precision="2" style="width:100%" />
        </template>
      </el-table-column>
      <el-table-column prop="decreaseToExpense" label="本期减少-转费用" min-width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.decreaseToExpense" size="small" :controls="false" :precision="2" style="width:100%" />
        </template>
      </el-table-column>
      <el-table-column label="期末余额" min-width="120" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="=期初+资本化+费用化-转无形-转费用">
            {{ fmtNum(row.beginBalance + row.increaseCapitalized + row.increaseExpensed - row.decreaseToIntangible - row.decreaseToExpense) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="130">
        <template #default="{ row }">
          <el-input v-model="row.remark" size="small" placeholder="备注" />
        </template>
      </el-table-column>
    </el-table>

    <!-- 附注文字说明 -->
    <el-card class="note-text-card" shadow="never" style="margin-top:14px">
      <template #header>
        <div class="note-text-header">
          <span>附注文字说明</span>
        </div>
      </template>
      <el-input
        v-model="noteText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="开发支出附注文字描述（资本化政策/重大项目/研发投入强度等）..."
      />
    </el-card>

    <!-- 行操作 -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain @click="handleAddRow">+ 新增行</el-button>
      <el-button size="small" type="success" @click="handleSave">保存</el-button>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span>审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly" :autosize="{ minRows: 5 }" placeholder="记录审计过程、发现的问题及处理..." @change="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span>审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly" :autosize="{ minRows: 3 }" placeholder="填写附注披露审计结论..." @change="saveAuditConclusion" />
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

interface DisclosureSoeRow {
  rowId: string; name: string; beginBalance: number
  increaseCapitalized: number; increaseExpensed: number
  decreaseToIntangible: number; decreaseToExpense: number
  remark: string; isAutoFilled: boolean
}

const STORAGE_KEY = 'I2-disc-soe-rows'
const NOTE_KEY = 'I2-disc-soe-note'
const rows = ref<DisclosureSoeRow[]>([])
const noteText = ref('')

function loadData() {
  const raw = props.allResponses.get(STORAGE_KEY)
  if (raw) {
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : (raw.remark ? JSON.parse(raw.remark) : raw)
      if (Array.isArray(parsed)) rows.value = parsed.map(normRow)
    } catch { rows.value = [] }
  } else { rows.value = [] }
  const noteRaw = props.allResponses.get(NOTE_KEY)
  if (noteRaw) {
    noteText.value = typeof noteRaw === 'string' ? noteRaw : (noteRaw.remark || noteRaw.conclusion || '')
  }
}

function normRow(r: any): DisclosureSoeRow {
  return {
    rowId: r.rowId || `ds-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    name: r.name || '', beginBalance: Number(r.beginBalance) || 0,
    increaseCapitalized: Number(r.increaseCapitalized) || 0,
    increaseExpensed: Number(r.increaseExpensed) || 0,
    decreaseToIntangible: Number(r.decreaseToIntangible) || 0,
    decreaseToExpense: Number(r.decreaseToExpense) || 0,
    remark: r.remark || '', isAutoFilled: !!r.isAutoFilled,
  }
}

watch(() => props.allResponses, () => loadData(), { immediate: true })

function handleAddRow() { rows.value.push(normRow({})) }

function handleAutoFill() {
  const adjRaw = props.allResponses.get('I2-1-rows')
  if (!adjRaw) { ElMessage.info('暂无审定表数据可供自动取数'); return }
  try {
    const parsed = typeof adjRaw === 'string' ? JSON.parse(adjRaw) : (adjRaw.remark ? JSON.parse(adjRaw.remark) : adjRaw)
    if (Array.isArray(parsed) && parsed.length > 0) {
      rows.value = parsed.map((r: any) => normRow({
        name: r.projectName || r.name || '',
        beginBalance: r.beginBalance ?? r.openingBalance ?? 0,
        increaseCapitalized: r.increaseCapitalized ?? r.debitAmount ?? 0,
        increaseExpensed: r.increaseExpensed ?? 0,
        decreaseToIntangible: r.decreaseToIntangible ?? 0,
        decreaseToExpense: r.decreaseToExpense ?? 0,
        isAutoFilled: true,
      }))
      ElMessage.success(`已从审定表取数${rows.value.length}项`)
    }
  } catch { ElMessage.warning('审定表数据解析失败') }
}

async function handleSave() {
  await props.saveResponse('disc-soe', {
    [STORAGE_KEY]: JSON.stringify(rows.value),
    [NOTE_KEY]: noteText.value,
  })
  emit('save')
  ElMessage.success('附注披露（国企）已保存')
}

function handleReview() { openReviewDialog('I2-附注披露-国企') }
function fmtNum(v: number): string { return v == null || isNaN(v) ? '—' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

// ─── 审计说明 / 审计结论 ───
const AUDIT_NOTE_KEY = 'I2-disc-soe-audit-note'
const AUDIT_CONCLUSION_KEY = 'I2-disc-soe-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function readRemark(key: string): string { const raw = props.allResponses.get(key); if (raw == null) return ''; return typeof raw === 'string' ? raw : (raw.remark ?? '') }
function hydrateAudit() { auditNote.value = readRemark(AUDIT_NOTE_KEY); auditConclusion.value = readRemark(AUDIT_CONCLUSION_KEY) }
function saveAuditNote(val: string) { auditNote.value = val; void props.saveResponse('disc-soe', { [AUDIT_NOTE_KEY]: val }) }
function saveAuditConclusion(val: string) { auditConclusion.value = val; void props.saveResponse('disc-soe', { [AUDIT_CONCLUSION_KEY]: val }) }
watch(() => props.allResponses, () => hydrateAudit(), { immediate: true })
onMounted(hydrateAudit)
</script>

<style scoped>
.i2-disclosure-soe { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6; }
.disclosure-table { font-size: var(--wp-font-size, 13px); }
.formula-cell { color: #6366f1; font-weight: 500; border-bottom: 1px dashed #a5b4fc; cursor: help; }
.note-text-card { margin-bottom: 12px; }
.note-text-header { display: flex; align-items: center; justify-content: space-between; }
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
