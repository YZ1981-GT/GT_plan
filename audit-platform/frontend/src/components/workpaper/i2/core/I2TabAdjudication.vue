<template>
  <div class="i2-adjudication">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2-1 审定表 — 开发支出审定(61公式)</span>
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
      <p><strong>三角勾稽原理：</strong>科目1717开发支出（借方/资产类）。</p>
      <p>期末余额 = 期初余额 + 本期增加(资本化) - 本期减少(转无形资产) - 本期减少(转费用)</p>
      <p>审定数 = 未审数 + AJE + RJE。三角勾稽差额≠0将红色高亮。</p>
    </div>

    <!-- TB取数显示区 -->
    <div class="tb-display">
      <el-descriptions :column="4" border size="small">
        <el-descriptions-item label="TB未审数(1717)">
          {{ fmtAmount(tbData.unadjusted1717) }}
        </el-descriptions-item>
        <el-descriptions-item label="TB审定数(1717)">
          {{ fmtAmount(tbData.audited1717) }}
        </el-descriptions-item>
        <el-descriptions-item label="AJE(1717)">
          {{ fmtAmount(tbData.aje1717) }}
        </el-descriptions-item>
        <el-descriptions-item label="RJE(1717)">
          {{ fmtAmount(tbData.rje1717) }}
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- 审定表 el-table -->
    <el-table
      :data="displayRows"
      border
      size="small"
      :row-class-name="getRowClassName"
      class="adjudication-table"
    >
      <el-table-column prop="projectName" label="项目" min-width="150" fixed>
        <template #default="{ row }">
          <span :class="{ 'total-text': row._isTotal }">{{ row.projectName }}</span>
        </template>
      </el-table-column>

      <el-table-column prop="cipBegin" label="期初余额" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!row._isTotal"
            :model-value="row.cipBegin"
            size="small"
            :controls="false"
            @change="(v: number) => onFieldChange($index, 'cipBegin', v)"
          />
          <span v-else class="total-text">{{ fmtAmount(row.cipBegin) }}</span>
        </template>
      </el-table-column>

      <el-table-column prop="increaseCapitalized" label="本期增加(资本化)" min-width="140" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!row._isTotal"
            :model-value="row.increaseCapitalized"
            size="small"
            :controls="false"
            @change="(v: number) => onFieldChange($index, 'increaseCapitalized', v)"
          />
          <span v-else class="total-text">{{ fmtAmount(row.increaseCapitalized) }}</span>
        </template>
      </el-table-column>

      <el-table-column prop="decreaseTransfer" label="本期减少(转无形)" min-width="140" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!row._isTotal"
            :model-value="row.decreaseTransfer"
            size="small"
            :controls="false"
            @change="(v: number) => onFieldChange($index, 'decreaseTransfer', v)"
          />
          <span v-else class="total-text">{{ fmtAmount(row.decreaseTransfer) }}</span>
        </template>
      </el-table-column>

      <el-table-column prop="decreaseExpense" label="本期减少(转费用)" min-width="140" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!row._isTotal"
            :model-value="row.decreaseExpense"
            size="small"
            :controls="false"
            @change="(v: number) => onFieldChange($index, 'decreaseExpense', v)"
          />
          <span v-else class="total-text">{{ fmtAmount(row.decreaseExpense) }}</span>
        </template>
      </el-table-column>

      <!-- 公式列：期末余额 -->
      <el-table-column label="期末余额(公式)" min-width="130" align="right">
        <template #header>
          <el-tooltip content="期末 = 期初 + 增加(资本化) - 减少(转无形) - 减少(转费用)" placement="top">
            <span class="formula-col-header">期末余额</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span :class="['formula-value', { 'total-text': row._isTotal }]">
            {{ fmtAmount(row.cipEnd) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column prop="unadjusted" label="未审数" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!row._isTotal"
            :model-value="row.unadjusted"
            size="small"
            :controls="false"
            @change="(v: number) => onFieldChange($index, 'unadjusted', v)"
          />
          <span v-else class="total-text">{{ fmtAmount(row.unadjusted) }}</span>
        </template>
      </el-table-column>

      <el-table-column prop="aje" label="AJE" min-width="100" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!row._isTotal"
            :model-value="row.aje"
            size="small"
            :controls="false"
            @change="(v: number) => onFieldChange($index, 'aje', v)"
          />
          <span v-else class="total-text">{{ fmtAmount(row.aje) }}</span>
        </template>
      </el-table-column>

      <el-table-column prop="rje" label="RJE" min-width="100" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!row._isTotal"
            :model-value="row.rje"
            size="small"
            :controls="false"
            @change="(v: number) => onFieldChange($index, 'rje', v)"
          />
          <span v-else class="total-text">{{ fmtAmount(row.rje) }}</span>
        </template>
      </el-table-column>

      <!-- 公式列：审定数 -->
      <el-table-column label="审定数(公式)" min-width="120" align="right">
        <template #header>
          <el-tooltip content="审定数 = 未审数 + AJE + RJE" placement="top">
            <span class="formula-col-header">审定数</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span :class="['formula-value', { 'total-text': row._isTotal }]">
            {{ fmtAmount(row.audited) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column prop="remark" label="备注" min-width="150">
        <template #default="{ row, $index }">
          <el-input
            v-if="!row._isTotal"
            :model-value="row.remark"
            size="small"
            @change="(v: string) => onFieldChange($index, 'remark', v)"
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

    <!-- 审计说明+结论 -->
    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>审计说明与结论</span>
          <el-button size="small" type="primary" text @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        placeholder="请填写审计说明及结论..."
        @blur="onNoteSave"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useI2Adjudication, type AdjudicationRow } from '../../composables/useI2Adjudication'
import type { I2TbData } from '../../composables/useI2FormData'

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

// ─── TB Data (from parent via allResponses) ──────────────────────────────────

const tbData = computed<I2TbData>(() => {
  const raw = props.allResponses.get('I2-tb-data')
  return {
    unadjusted1717: Number(raw?.unadjusted1717) || 0,
    audited1717: Number(raw?.audited1717) || 0,
    aje1717: Number(raw?.aje1717) || 0,
    rje1717: Number(raw?.rje1717) || 0,
  }
})

// ─── Composable ──────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)
const tbDataRef = computed(() => tbData.value)

const {
  rows,
  totalRow,
  reconciliationErrors,
  hasErrors,
  addRow,
  removeRow,
  updateRow,
  save: saveData,
} = useI2Adjudication({
  allResponses: allResponsesRef,
  tbData: tbDataRef,
  saveResponses: props.saveResponse,
})

// ─── Display Rows (data + total) ─────────────────────────────────────────────

const displayRows = computed(() => {
  const dataRows = rows.value.map((r) => ({ ...r, _isTotal: false }))
  const total = { ...totalRow.value, _isTotal: true }
  return [...dataRows, total]
})

// ─── Audit Note ──────────────────────────────────────────────────────────────

const auditNote = ref('')

function onNoteSave() {
  props.saveResponse('1', { 'I2-1-note': auditNote.value })
}

// ─── Row Styling ─────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: any }): string {
  if (row._isTotal) return 'total-row'
  const errors = reconciliationErrors.value
  const idx = rows.value.findIndex((r) => r.projectName === row.projectName)
  if (errors.some((e) => e.rowIndex === idx)) return 'reconciliation-error-row'
  return ''
}

// ─── Cell Change ─────────────────────────────────────────────────────────────

function onFieldChange(displayIndex: number, field: string, value: any) {
  // displayIndex includes total row at end, skip if total
  if (displayIndex >= rows.value.length) return
  updateRow(displayIndex, field, value ?? 0)
}

// ─── Add Row ─────────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入研发项目名称', '新增项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：XX智能平台开发',
    })
    if (value?.trim()) {
      addRow(value.trim())
      ElMessage.success('已添加项目')
    }
  } catch {
    // cancelled
  }
}

// ─── Save ────────────────────────────────────────────────────────────────────

async function handleSave() {
  await saveData()
  emit('save')
  ElMessage.success('审定表已保存')
}

// ─── AI / Review ─────────────────────────────────────────────────────────────

function handleAiGenerate() {
  console.log('[I2-Adjudication] AI generate')
}

function handleReview() {
  openReviewDialog('I2-1-审定表')
}

// ─── Formatter ───────────────────────────────────────────────────────────────

function fmtAmount(value: number | null | undefined): string {
  if (value == null) return '-'
  if (Math.abs(value) < 0.005) return '-'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i2-adjudication {
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
.tb-display {
  margin-bottom: 14px;
}
.adjudication-table {
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
.total-text {
  font-weight: 600;
  color: #303133;
}
.table-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.audit-note-card {
  margin-top: 16px;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
:deep(.total-row) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}
:deep(.reconciliation-error-row) {
  background-color: #fef2f2 !important;
}
</style>
