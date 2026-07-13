<template>
  <div class="i2-analysis">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2-5 实质性分析 — 开发支出波动分析(31公式)</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">
          复核
        </el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：通过实质性分析程序评价开发支出各项目余额的合理性，识别异常波动并追查研发资本化的完整性与准确性。" />

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 计算各项目期末余额同比变动率并与预期值比较，关注偏离重要性水平的差异；</p>
        <p>2. 对超阈值项目追查异常原因，结合研发进度、立项与资本化政策评价合理性；</p>
        <p>3. 依据 CAS6《无形资产》资本化条件复核开发支出归集是否恰当。</p>
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
      <p><strong>实质性分析程序：</strong>通过对开发支出各项目的期末余额进行同比分析和预期比较。</p>
      <p>同比变动率 = (期末 - 上期期末) / 上期期末 × 100%。差异 = 期末 - 预期值。</p>
      <p>差异超过重要性水平时红色标记，需进一步分析异常原因并制定审计应对。</p>
    </div>

    <!-- 异常汇总提示 -->
    <el-alert
      v-if="hasAnomalies"
      type="error"
      :closable="false"
      show-icon
      class="anomaly-alert"
    >
      发现 {{ anomalyRows.length }} 个项目差异超过重要性水平，请关注异常原因。
    </el-alert>

    <!-- 分析表 -->
    <el-table
      :data="displayRows"
      border
      size="small"
      :row-class-name="getRowClassName"
      class="analysis-table"
    >
      <el-table-column prop="projectName" label="项目" min-width="150" fixed>
        <template #default="{ row }">
          <span :class="{ 'total-text': row._isTotal }">{{ row.projectName }}</span>
        </template>
      </el-table-column>

      <el-table-column prop="beginAmount" label="期初" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!row._isTotal"
            :model-value="row.beginAmount"
            size="small"
            :controls="false"
            @change="(v: number) => onFieldChange($index, 'beginAmount', v)"
          />
          <span v-else class="total-text">{{ fmtAmount(row.beginAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column prop="increaseAmount" label="本期增加" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!row._isTotal"
            :model-value="row.increaseAmount"
            size="small"
            :controls="false"
            @change="(v: number) => onFieldChange($index, 'increaseAmount', v)"
          />
          <span v-else class="total-text">{{ fmtAmount(row.increaseAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column prop="decreaseAmount" label="本期减少" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!row._isTotal"
            :model-value="row.decreaseAmount"
            size="small"
            :controls="false"
            @change="(v: number) => onFieldChange($index, 'decreaseAmount', v)"
          />
          <span v-else class="total-text">{{ fmtAmount(row.decreaseAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 公式列：期末 -->
      <el-table-column label="期末" min-width="120" align="right">
        <template #header>
          <el-tooltip content="期末 = 期初 + 本期增加 - 本期减少" placement="top">
            <span class="formula-col-header">期末</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span :class="['formula-value', { 'total-text': row._isTotal }]">
            {{ fmtAmount(row.endAmount) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column prop="priorEndAmount" label="上期期末" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!row._isTotal"
            :model-value="row.priorEndAmount"
            size="small"
            :controls="false"
            @change="(v: number) => onFieldChange($index, 'priorEndAmount', v)"
          />
          <span v-else class="total-text">{{ fmtAmount(row.priorEndAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 公式列：同比变动率 -->
      <el-table-column label="同比变动率" min-width="110" align="right">
        <template #header>
          <el-tooltip content="同比变动率 = (期末 - 上期期末) / 上期期末" placement="top">
            <span class="formula-col-header">同比变动率</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span :class="['formula-value', { 'total-text': row._isTotal }]">
            {{ row.changeRate != null ? (row.changeRate * 100).toFixed(2) + '%' : '-' }}
          </span>
        </template>
      </el-table-column>

      <el-table-column prop="expectedValue" label="预期值" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!row._isTotal"
            :model-value="row.expectedValue"
            size="small"
            :controls="false"
            @change="(v: number) => onFieldChange($index, 'expectedValue', v)"
          />
          <span v-else class="total-text">{{ fmtAmount(row.expectedValue) }}</span>
        </template>
      </el-table-column>

      <!-- 公式列：差异 -->
      <el-table-column label="差异" min-width="120" align="right">
        <template #header>
          <el-tooltip content="差异 = 期末 - 预期值" placement="top">
            <span class="formula-col-header">差异</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span :class="['formula-value', { 'total-text': row._isTotal, 'exceed-threshold': row.exceedThreshold }]">
            {{ fmtAmount(row.variance) }}
          </span>
        </template>
      </el-table-column>

      <!-- 超阈值标记 -->
      <el-table-column label="超阈值" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.exceedThreshold" type="danger" size="small">超标</el-tag>
        </template>
      </el-table-column>

      <el-table-column prop="analysisConclusion" label="分析结论" min-width="160">
        <template #default="{ row, $index }">
          <el-input
            v-if="!row._isTotal"
            :model-value="row.analysisConclusion"
            size="small"
            placeholder="分析结论"
            @change="(v: string) => onFieldChange($index, 'analysisConclusion', v)"
          />
        </template>
      </el-table-column>

      <el-table-column prop="anomalyReason" label="异常原因" min-width="160">
        <template #default="{ row, $index }">
          <el-input
            v-if="!row._isTotal"
            :model-value="row.anomalyReason"
            size="small"
            placeholder="异常原因说明"
            @change="(v: string) => onFieldChange($index, 'anomalyReason', v)"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- 操作按钮 -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain @click="handleAddRow">
        + 新增项目
      </el-button>
      <el-button size="small" type="success" @click="handleSave">
        保存
      </el-button>
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
import { ref, computed, inject, onMounted, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useI2Analysis } from '../../composables/useI2Analysis'
import GtIndexChip from '../../GtIndexChip.vue'

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

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  rows,
  totalRow,
  anomalyRows,
  hasAnomalies,
  addRow,
  removeRow,
  updateField,
  save: saveData,
} = useI2Analysis({
  allResponses: allResponsesRef,
  saveResponses: props.saveResponse,
})

// ─── 审计说明 / 审计结论 ───
const AUDIT_NOTE_KEY = 'I2-5-audit-note'
const AUDIT_CONCLUSION_KEY = 'I2-5-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function readRemark(key: string): string { const raw = props.allResponses.get(key); if (raw == null) return ''; return typeof raw === 'string' ? raw : (raw.remark ?? '') }
function hydrateAudit() { auditNote.value = readRemark(AUDIT_NOTE_KEY); auditConclusion.value = readRemark(AUDIT_CONCLUSION_KEY) }
function saveAuditNote(val: string) { auditNote.value = val; void props.saveResponse('I2-5', { [AUDIT_NOTE_KEY]: val }) }
function saveAuditConclusion(val: string) { auditConclusion.value = val; void props.saveResponse('I2-5', { [AUDIT_CONCLUSION_KEY]: val }) }
watch(() => props.allResponses, () => hydrateAudit(), { immediate: true })
onMounted(hydrateAudit)

// ─── Display Rows ────────────────────────────────────────────────────────────

const displayRows = computed(() => {
  const dataRows = rows.value.map((r) => ({ ...r, _isTotal: false }))
  const total = { ...totalRow.value, _isTotal: true }
  return [...dataRows, total]
})

// ─── Row Class ───────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: any }): string {
  if (row._isTotal) return 'total-row'
  if (row.exceedThreshold) return 'exceed-row'
  return ''
}

// ─── Cell Change ─────────────────────────────────────────────────────────────

function onFieldChange(displayIndex: number, field: string, value: any) {
  if (displayIndex >= rows.value.length) return
  updateField(displayIndex, field, value ?? 0)
}

// ─── Add Row ─────────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入研发项目名称', '新增分析项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：XX项目开发支出',
    })
    if (value?.trim()) {
      addRow(value.trim())
      ElMessage.success('已添加分析项目')
    }
  } catch {
    // cancelled
  }
}

// ─── Save ────────────────────────────────────────────────────────────────────

async function handleSave() {
  await saveData()
  emit('save')
  ElMessage.success('实质性分析已保存')
}

// ─── Review ──────────────────────────────────────────────────────────────────

function handleReview() {
  openReviewDialog('I2-5-实质性分析')
}

// ─── Formatter ───────────────────────────────────────────────────────────────

function fmtAmount(value: number | null | undefined): string {
  if (value == null) return '-'
  if (Math.abs(value) < 0.005) return '-'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i2-analysis {
  font-size: var(--wp-font-size, 13px);
  padding: 16px;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
}
.section-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 14px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.7;
}
.methodology-context p { margin: 0; }
.methodology-context strong { color: #78350f; }
.anomaly-alert {
  margin-bottom: 12px;
}
.analysis-table {
  font-size: var(--wp-font-size, 13px);
  margin-bottom: 12px;
}
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}
.formula-value {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  color: #409eff;
}
.exceed-threshold {
  color: #f56c6c;
  font-weight: 600;
}
.total-text {
  font-weight: 600;
  color: #303133;
}
.table-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
:deep(.total-row) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}
:deep(.exceed-row) {
  background-color: #fef2f2 !important;
}
.objective-alert { margin-bottom: 12px; }
.guidance-details { margin-bottom: 12px; font-size: 12px; color: var(--el-text-color-secondary); background: #f9fafb; border: 1px solid #ebeef5; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 600; color: #374151; }
.guidance-details .guidance-content { margin-top: 8px; line-height: 1.7; }
.guidance-details .guidance-content p { margin: 0 0 4px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 10px; }
.tab-toolbar .toolbar-right { display: flex; align-items: center; gap: 8px; }
.audit-note-card, .audit-conclusion-card { margin-top: 16px; }
</style>
