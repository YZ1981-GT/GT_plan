<template>
  <div class="i2-analysis">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2-5 实质性分析 — 开发支出波动分析(31公式)</span>
      <div class="section-actions">
        <el-button size="small" type="primary" text @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" type="default" text @click="handleReview">
          复核
        </el-button>
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

      <!-- AI分析按钮 per row -->
      <el-table-column label="AI分析" width="80" align="center">
        <template #default="{ row, $index }">
          <el-button
            v-if="!row._isTotal && row.exceedThreshold"
            size="small"
            type="primary"
            text
            @click="handleRowAi($index)"
          >
            AI
          </el-button>
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
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useI2Analysis } from '../../../composables/useI2Analysis'

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
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

// ─── AI (per row) ────────────────────────────────────────────────────────────

function handleRowAi(index: number) {
  const row = rows.value[index]
  console.log('[I2-Analysis] AI per-row analysis for:', row?.projectName)
  ElMessage.info(`AI正在分析 ${row?.projectName} 的异常原因...`)
}

// ─── AI / Review (section level) ─────────────────────────────────────────────

function handleAiGenerate() {
  console.log('[I2-Analysis] AI generate')
}

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
  font-size: 13px;
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
  font-size: 13px;
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
</style>
