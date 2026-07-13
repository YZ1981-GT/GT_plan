<template>
  <div class="i2-adjudication">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2-1 审定表 — 开发支出审定(61公式)</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">
          复核
        </el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：核查开发支出(科目1717)期末余额的真实性、完整性与计价准确性，确认资本化归集及审定调整恰当。" />

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 复核期末余额=期初+本期增加(资本化)-本期减少(转无形/转费用)三角勾稽是否成立；</p>
        <p>2. 核对审定数=未审数+AJE+RJE，确认调整分录依据充分、过账准确；</p>
        <p>3. 依据 CAS6《无形资产》开发阶段资本化条件复核归集金额。</p>
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
import { useI2Adjudication, type AdjudicationRow } from '../../composables/useI2Adjudication'
import type { I2TbData } from '../../composables/useI2FormData'
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

// ─── 审计说明 / 审计结论 ───
const AUDIT_NOTE_KEY = 'I2-1-audit-note'
const AUDIT_CONCLUSION_KEY = 'I2-1-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function readRemark(key: string): string { const raw = props.allResponses.get(key); if (raw == null) return ''; return typeof raw === 'string' ? raw : (raw.remark ?? '') }
function hydrateAudit() { auditNote.value = readRemark(AUDIT_NOTE_KEY); auditConclusion.value = readRemark(AUDIT_CONCLUSION_KEY) }
function saveAuditNote(val: string) { auditNote.value = val; void props.saveResponse('I2-1', { [AUDIT_NOTE_KEY]: val }) }
function saveAuditConclusion(val: string) { auditConclusion.value = val; void props.saveResponse('I2-1', { [AUDIT_CONCLUSION_KEY]: val }) }
watch(() => props.allResponses, () => hydrateAudit(), { immediate: true })
onMounted(hydrateAudit)

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

// ─── Review ──────────────────────────────────────────────────────────────────

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
.tb-display {
  margin-bottom: 14px;
}
.adjudication-table {
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
.objective-alert { margin-bottom: 12px; }
.guidance-details { margin-bottom: 12px; font-size: 12px; color: var(--el-text-color-secondary); background: #f9fafb; border: 1px solid #ebeef5; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 600; color: #374151; }
.guidance-details .guidance-content { margin-top: 8px; line-height: 1.7; }
.guidance-details .guidance-content p { margin: 0 0 4px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 10px; }
.tab-toolbar .toolbar-right { display: flex; align-items: center; gap: 8px; }
.audit-note-card, .audit-conclusion-card { margin-top: 16px; }
</style>
