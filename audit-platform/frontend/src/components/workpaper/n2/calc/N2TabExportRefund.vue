<template>
  <div class="n2-tab-export-refund">
    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>出口退税核对表 N2-7</span>
        <el-tag type="info" size="small">免抵退税额测算</el-tag>
      </div>
      <div class="section-actions">
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增
        </el-button>
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>出口退税核对：</strong>
        免抵退税额 = 出口销售额 × 退税率。核对企业测算的免抵退税额是否与主管税务机关批复金额一致，
        差异部分需取得管理层解释或调整。结果联动N2-6增值税测算。
      </div>
    </div>

    <!-- ═══ 核对汇总 ═══ -->
    <div class="refund-summary">
      <div class="summary-item">
        <span class="summary-label">出口销售额合计</span>
        <span class="summary-value">{{ fmtAmount(exportRefund.summary.value.totalExportSales) }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">免抵退税额合计</span>
        <span class="summary-value">{{ fmtAmount(exportRefund.summary.value.totalTaxRefund) }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">应退税额合计</span>
        <span class="summary-value">{{ fmtAmount(exportRefund.summary.value.totalRefundDue) }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">已退税额合计</span>
        <span class="summary-value">{{ fmtAmount(exportRefund.summary.value.totalActualRefunded) }}</span>
      </div>
      <div class="summary-item" :class="{ 'summary-item--diff': !exportRefund.summary.value.allMatch }">
        <span class="summary-label">差异合计</span>
        <span class="summary-value">{{ fmtAmount(exportRefund.summary.value.totalDiff) }}</span>
      </div>
    </div>

    <!-- ═══ 出口退税核对明细表 ═══ -->
    <el-table
      :data="exportRefund.rows.value"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
    >
      <el-table-column prop="description" label="产品/批次" width="150">
        <template #default="{ row }">
          <el-input
            :model-value="row.description"
            size="small"
            :disabled="isReadonly"
            placeholder="产品描述"
            @change="(val: string) => exportRefund.updateRow(row.id, 'description', val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="出口销售额" width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.exportSales"
            :disabled="isReadonly"
            :controls="false"
            :precision="2"
            size="small"
            style="width: 110px"
            @change="(val: number) => exportRefund.updateRow(row.id, 'exportSales', val ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="退税率" width="100" align="center">
        <template #default="{ row }">
          <el-select
            :model-value="row.refundRate"
            size="small"
            :disabled="isReadonly"
            style="width: 80px"
            @change="(val: number) => exportRefund.updateRow(row.id, 'refundRate', val)"
          >
            <el-option :value="0.13" label="13%" />
            <el-option :value="0.10" label="10%" />
            <el-option :value="0.09" label="9%" />
            <el-option :value="0.06" label="6%" />
            <el-option :value="0.05" label="5%" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="免抵退税额" width="130" align="right">
        <template #header>
          <el-tooltip content="公式：出口销售额 × 退税率" placement="top">
            <span class="formula-col-header">免抵退税额</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-cell">{{ fmtAmount(row.taxRefundAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="应退税额(批复)" width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.refundDue"
            :disabled="isReadonly"
            :controls="false"
            :precision="2"
            size="small"
            style="width: 110px"
            @change="(val: number) => exportRefund.updateRow(row.id, 'refundDue', val ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="免抵税额(批复)" width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.exemptCreditAmount"
            :disabled="isReadonly"
            :controls="false"
            :precision="2"
            size="small"
            style="width: 110px"
            @change="(val: number) => exportRefund.updateRow(row.id, 'exemptCreditAmount', val ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="已退税额" width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.actualRefunded"
            :disabled="isReadonly"
            :controls="false"
            :precision="2"
            size="small"
            style="width: 110px"
            @change="(val: number) => exportRefund.updateRow(row.id, 'actualRefunded', val ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="差异" width="110" align="right">
        <template #header>
          <el-tooltip content="差异 = 应退税额 - 已退税额" placement="top">
            <span class="formula-col-header">差异</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span
            class="formula-cell"
            :class="{ 'formula-cell--diff': row.hasDiff }"
          >
            {{ fmtAmount(row.diff) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            size="small"
            type="danger"
            :icon="Delete"
            circle
            :disabled="isReadonly"
            @click="exportRefund.removeRow(row.id)"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 空状态 ─── -->
    <el-empty
      v-if="exportRefund.rows.value.length === 0"
      description="暂无出口退税数据，点击“新增”添加"
      :image-size="60"
    />

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="card-header">
          <span>审计说明与结论</span>
          <el-button size="small" @click="handleAiAssist">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="请输入出口退税核对审计说明..."
        @change="handleNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>免抵退税额 = 出口销售额(FOB) × 退税率（公式自动计算）</li>
        <li>应退税额/免抵税额应与税务机关批复通知书核对</li>
        <li>差异需取得合理解释：汇率差异/退税率调整/申报时间差</li>
        <li>关注退税率与实际出口货物类型的匹配</li>
        <li>核对结果联动N2-6增值税测算（留抵退税影响）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabExportRefund — N2-7 出口退税核对表
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 4.10
 * Requirements: 8.1-8.4
 *
 * 核心职责：
 * - 免抵退税额测算 + 与批复核对 + 差异标记
 * - 联动N2-6增值税测算
 * - Uses useN2ExportRefund composable
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare, Plus, Delete } from '@element-plus/icons-vue'
import { useN2FormData } from '../../composables/useN2FormData'
import { useN2ExportRefund } from '../../composables/useN2ExportRefund'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((section: string) => void) | undefined>('openReviewDialog', undefined)

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useN2FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Composable ──────────────────────────────────────────────────────────────

const exportRefund = useN2ExportRefund({
  allResponses: formData.allResponses,
  saveField: formData.saveField,
  getField: formData.getField,
})

// ─── State ───────────────────────────────────────────────────────────────────

const isReadonly = computed(() => props.isReadonly ?? false)
const auditNote = ref('')

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: any }) {
  return row.hasDiff ? 'row--diff' : ''
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入产品/批次描述', '新增出口退税行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：产品A 202X年第X批',
    })
    if (value?.trim()) {
      await exportRefund.addRow(value.trim())
    }
  } catch { /* cancelled */ }
}

function handleNoteChange() {
  formData.debouncedSave('N2-7-note', { remark: auditNote.value || null })
}

function handleAiAssist() {
  ElMessage.info('AI辅助出口退税核对...')
}

function handleReview() {
  openReviewDialog?.('N2-7-出口退税核对')
}

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  const noteResp = formData.allResponses.value.get('N2-7-note')
  if (noteResp?.remark) auditNote.value = noteResp.remark
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  restoreData()
})
</script>

<style scoped>
.n2-tab-export-refund {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 方法论上下文 ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── 汇总 ─── */
.refund-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.summary-item--diff .summary-value {
  color: #f56c6c;
  font-weight: 700;
}

.summary-label {
  font-size: 12px;
  color: #909399;
}

.summary-value {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

/* ─── 表格 ─── */
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.formula-cell {
  color: #409eff;
  font-weight: 500;
}

.formula-cell--diff {
  color: #f56c6c;
  font-weight: 700;
}

:deep(.row--diff) {
  background: #fdf6ec !important;
}

/* ─── 结论卡片 ─── */
.conclusion-card {
  margin-top: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

/* ─── 编制提示 ─── */
.n2-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.n2-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n2-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
