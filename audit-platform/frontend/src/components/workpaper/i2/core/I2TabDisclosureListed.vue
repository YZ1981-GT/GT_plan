<template>
  <div class="i2-disclosure-listed">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2 附注披露（上市公司）— 58行×7列</span>
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
      title="审计目标：核查上市公司开发支出附注披露的完整性与准确性，确认各研发项目期初、增减变动、期末余额及减值披露与审定表I2-1、明细表I2-2一致。" />

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 逐项目核对期初余额、本期增加、本期减少、期末余额及减值披露数据；</p>
        <p>2. 复核附注披露口径与审定表I2-1、明细表I2-2勾稽一致，防止漏披或错披；</p>
        <p>3. 依据 CAS6《无形资产》及企业会计准则披露要求核查开发支出附注列报。</p>
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
      <p>上市公司开发支出附注（CAS6）：按研发项目逐项披露期初余额、本期增减变动、期末余额及减值情况。数据应与审定表I2-1及明细表I2-2一致。</p>
    </div>

    <!-- 附注表格（58行×7列，虚拟滚动） -->
    <el-table :data="rows" border size="small" class="disclosure-table" max-height="520">
      <el-table-column type="index" label="#" width="40" fixed />
      <el-table-column prop="name" label="项目" min-width="180" fixed>
        <template #default="{ row }">
          <el-input v-model="row.name" size="small" placeholder="项目名称" />
        </template>
      </el-table-column>
      <el-table-column prop="beginBalance" label="期初余额" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.beginBalance" size="small" :controls="false" :precision="2" style="width:100%" />
        </template>
      </el-table-column>
      <el-table-column prop="increase" label="本期增加" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.increase" size="small" :controls="false" :precision="2" style="width:100%" />
        </template>
      </el-table-column>
      <el-table-column prop="decrease" label="本期减少" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.decrease" size="small" :controls="false" :precision="2" style="width:100%" />
        </template>
      </el-table-column>
      <el-table-column prop="endBalance" label="期末余额" min-width="120" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="=期初+增加-减少">{{ fmtNum(row.beginBalance + row.increase - row.decrease) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="impairment" label="减值" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.impairment" size="small" :controls="false" :precision="2" style="width:100%" />
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="150">
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
        placeholder="开发支出附注文字描述（如资本化政策说明、重大项目说明等）..."
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
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly" :autosize="{ minRows: 3 }" placeholder="填写审计结论..." @change="saveAuditConclusion" />
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

interface DisclosureListedRow {
  rowId: string; name: string; beginBalance: number; increase: number
  decrease: number; impairment: number; remark: string; isAutoFilled: boolean
}

const STORAGE_KEY = 'I2-disc-listed-rows'
const NOTE_KEY = 'I2-disc-listed-note'
const rows = ref<DisclosureListedRow[]>([])
const noteText = ref('')

function loadData() {
  // Load rows
  const raw = props.allResponses.get(STORAGE_KEY)
  if (raw) {
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : (raw.remark ? JSON.parse(raw.remark) : raw)
      if (Array.isArray(parsed)) rows.value = parsed.map(normRow)
    } catch { rows.value = [] }
  } else { rows.value = [] }
  // Load note text
  const noteRaw = props.allResponses.get(NOTE_KEY)
  if (noteRaw) {
    noteText.value = typeof noteRaw === 'string' ? noteRaw : (noteRaw.remark || noteRaw.conclusion || '')
  }
}

function normRow(r: any): DisclosureListedRow {
  return {
    rowId: r.rowId || `dl-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    name: r.name || '', beginBalance: Number(r.beginBalance) || 0,
    increase: Number(r.increase) || 0, decrease: Number(r.decrease) || 0,
    impairment: Number(r.impairment) || 0, remark: r.remark || '',
    isAutoFilled: !!r.isAutoFilled,
  }
}

watch(() => props.allResponses, () => loadData(), { immediate: true })

function handleAddRow() {
  rows.value.push(normRow({}))
}

function handleAutoFill() {
  // Pull from adjudication data I2-1
  const adjRaw = props.allResponses.get('I2-1-rows')
  if (!adjRaw) { ElMessage.info('暂无审定表数据可供自动取数'); return }
  try {
    const parsed = typeof adjRaw === 'string' ? JSON.parse(adjRaw) : (adjRaw.remark ? JSON.parse(adjRaw.remark) : adjRaw)
    if (Array.isArray(parsed) && parsed.length > 0) {
      rows.value = parsed.map((r: any) => normRow({
        name: r.projectName || r.name || '',
        beginBalance: r.beginBalance ?? r.openingBalance ?? 0,
        increase: r.increase ?? r.debitAmount ?? 0,
        decrease: r.decrease ?? r.creditAmount ?? 0,
        impairment: r.impairment ?? 0,
        isAutoFilled: true,
      }))
      ElMessage.success(`已从审定表取数${rows.value.length}项`)
    }
  } catch { ElMessage.warning('审定表数据解析失败') }
}

async function handleSave() {
  await props.saveResponse('disc-listed', {
    [STORAGE_KEY]: JSON.stringify(rows.value),
    [NOTE_KEY]: noteText.value,
  })
  emit('save')
  ElMessage.success('附注披露（上市公司）已保存')
}

function handleReview() { openReviewDialog('I2-附注披露-上市') }
function fmtNum(v: number): string { return v == null || isNaN(v) ? '—' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.i2-disclosure-listed { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6; }
.disclosure-table { font-size: var(--wp-font-size, 13px); }
.formula-cell { color: #6366f1; font-weight: 500; border-bottom: 1px dashed #a5b4fc; cursor: help; }
.note-text-card { margin-bottom: 12px; }
.note-text-header { display: flex; align-items: center; justify-content: space-between; }
.table-actions { display: flex; gap: 8px; margin-top: 12px; }
</style>
