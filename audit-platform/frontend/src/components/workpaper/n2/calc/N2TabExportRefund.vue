<template>
  <div class="n2-tab-export-refund">
    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title>审计目标</template>
      <ol class="ao-list">
        <li><strong>完整性</strong>：出口退税是否完整确认(免抵退税额逐月测算全覆盖)</li>
        <li><strong>准确性</strong>：免抵退计算是否正确(征退税率差额产生进项转出联动N2-6)</li>
      </ol>
    </el-alert>

    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>出口退税核对表 N2-7</span>
        <el-tag type="info" size="small">12月×10列 · 4公式</el-tag>
        <GtIndexChip value="wp:N2-6" />
        <GtIndexChip value="wp:N2-1" />
      </div>
      <div class="section-actions">
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>出口退税核对公式(源模板红字)：</strong>
        ⑤免抵退税额 = ②出口销售额(FOB) × ④退税率；
        ⑥不得免征和抵扣税额 = ②出口销售额 × (③征税率 - ④退税率) ← <em>这是进项转出的来源，联动N2-6!</em>
        ⑧免抵税额 = ⑤免抵退税额 - ⑦应退税额(自动计算)；
        ⑩差异 = ⑦应退税额 - ⑨已退税额。
        征税率是出口货物的增值税税率(13%/9%/6%)，退税率≤征税率。两者差异产生不得免征和抵扣税额。
      </div>
    </div>

    <!-- ═══ 配置提示栏：默认征税率/退税率快捷设置 ═══ -->
    <div class="calc-toolbar">
      <div class="toolbar-section">
        <span class="toolbar-label">全年统一征税率：</span>
        <el-select
          v-model="batchVatRate"
          size="small"
          placeholder="选择"
          style="width: 90px"
          :disabled="isReadonly"
          @change="applyBatchVatRate"
        >
          <el-option :value="0.13" label="13%" />
          <el-option :value="0.09" label="9%" />
          <el-option :value="0.06" label="6%" />
        </el-select>
      </div>
      <div class="toolbar-section">
        <span class="toolbar-label">全年统一退税率：</span>
        <el-select
          v-model="batchRefundRate"
          size="small"
          placeholder="选择"
          style="width: 90px"
          :disabled="isReadonly"
          @change="applyBatchRefundRate"
        >
          <el-option :value="0.13" label="13%" />
          <el-option :value="0.10" label="10%" />
          <el-option :value="0.09" label="9%" />
          <el-option :value="0.06" label="6%" />
          <el-option :value="0.05" label="5%" />
        </el-select>
      </div>
    </div>

    <!-- ═══ Monthly Data Table (12 rows + annual total) ═══ -->
    <el-table
      :data="tableData"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
      class="export-refund-table"
    >
      <!-- ① 月份 -->
      <el-table-column prop="label" label="月份" width="60" align="center" fixed="left">
        <template #default="{ row }">
          <strong v-if="row.isTotal">合计</strong>
          <span v-else>{{ row.label }}</span>
        </template>
      </el-table-column>

      <!-- ② 出口销售额(FOB) -->
      <el-table-column label="出口销售额(FOB)" width="140" align="right">
        <template #default="{ row }">
          <template v-if="row.isTotal">
            <span class="total-cell">{{ fmtAmount(row.exportSalesFob) }}</span>
          </template>
          <template v-else>
            <el-input-number
              :model-value="row.exportSalesFob"
              :disabled="isReadonly"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 120px"
              @change="(val: number) => handleCellChange(row.month, 'exportSalesFob', val ?? 0)"
            />
          </template>
        </template>
      </el-table-column>

      <!-- ③ 征税率 -->
      <el-table-column label="征税率" width="90" align="center">
        <template #header>
          <el-tooltip content="出口货物适用增值税税率: 13%/9%/6%" placement="top">
            <span class="formula-col-header">征税率③</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <template v-if="row.isTotal">—</template>
          <template v-else>
            <el-select
              :model-value="row.vatRate"
              size="small"
              :disabled="isReadonly"
              style="width: 70px"
              @change="(val: number) => handleCellChange(row.month, 'vatRate', val)"
            >
              <el-option :value="0.13" label="13%" />
              <el-option :value="0.09" label="9%" />
              <el-option :value="0.06" label="6%" />
            </el-select>
          </template>
        </template>
      </el-table-column>

      <!-- ④ 退税率 -->
      <el-table-column label="退税率" width="90" align="center">
        <template #header>
          <el-tooltip content="出口退税率，≤征税率" placement="top">
            <span class="formula-col-header">退税率④</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <template v-if="row.isTotal">—</template>
          <template v-else>
            <el-select
              :model-value="row.refundRate"
              size="small"
              :disabled="isReadonly"
              style="width: 70px"
              @change="(val: number) => handleCellChange(row.month, 'refundRate', val)"
            >
              <el-option :value="0.13" label="13%" />
              <el-option :value="0.10" label="10%" />
              <el-option :value="0.09" label="9%" />
              <el-option :value="0.06" label="6%" />
              <el-option :value="0.05" label="5%" />
            </el-select>
          </template>
        </template>
      </el-table-column>

      <!-- ⑤ 免抵退税额 (auto) -->
      <el-table-column label="免抵退税额⑤" width="130" align="right">
        <template #header>
          <el-tooltip content="公式: ② × ④ (出口销售额 × 退税率)" placement="top">
            <span class="formula-col-header">免抵退税额⑤</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="auto-calc-cell">{{ fmtAmount(row.exemptCreditRefundAmt) }}</span>
        </template>
      </el-table-column>

      <!-- ⑥ 不得免征和抵扣税额 (auto) -->
      <el-table-column label="不得免征抵扣⑥" width="140" align="right">
        <template #header>
          <el-tooltip content="公式: ② × (③ - ④) → 进项转出来源!" placement="top">
            <span class="formula-col-header">不得免征抵扣⑥</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="auto-calc-cell">{{ fmtAmount(row.nonDeductible) }}</span>
        </template>
      </el-table-column>

      <!-- ⑦ 应退税额(批复) -->
      <el-table-column label="应退税额⑦" width="130" align="right">
        <template #header>
          <el-tooltip content="税务机关批复通知书金额(手工录入)" placement="top">
            <span>应退税额⑦</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <template v-if="row.isTotal">
            <span class="total-cell">{{ fmtAmount(row.refundApproved) }}</span>
          </template>
          <template v-else>
            <el-input-number
              :model-value="row.refundApproved"
              :disabled="isReadonly"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 110px"
              @change="(val: number) => handleCellChange(row.month, 'refundApproved', val ?? 0)"
            />
          </template>
        </template>
      </el-table-column>

      <!-- ⑧ 免抵税额 (auto) -->
      <el-table-column label="免抵税额⑧" width="120" align="right">
        <template #header>
          <el-tooltip content="公式: ⑤ - ⑦ (免抵退税额 - 应退税额)" placement="top">
            <span class="formula-col-header">免抵税额⑧</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="auto-calc-cell">{{ fmtAmount(row.exemptCreditAmt) }}</span>
        </template>
      </el-table-column>

      <!-- ⑨ 已退税额 -->
      <el-table-column label="已退税额⑨" width="130" align="right">
        <template #default="{ row }">
          <template v-if="row.isTotal">
            <span class="total-cell">{{ fmtAmount(row.actualRefunded) }}</span>
          </template>
          <template v-else>
            <el-input-number
              :model-value="row.actualRefunded"
              :disabled="isReadonly"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 110px"
              @change="(val: number) => handleCellChange(row.month, 'actualRefunded', val ?? 0)"
            />
          </template>
        </template>
      </el-table-column>

      <!-- ⑩ 差异 (auto) -->
      <el-table-column label="差异⑩" width="110" align="right">
        <template #header>
          <el-tooltip content="公式: ⑦ - ⑨ (应退税额 - 已退税额)" placement="top">
            <span class="formula-col-header">差异⑩</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span
            class="auto-calc-cell"
            :class="{ 'diff-highlight': row.hasDiff }"
          >
            {{ fmtAmount(row.difference) }}
          </span>
        </template>
      </el-table-column>

      <!-- ⑪ 批复文号/备注 -->
      <el-table-column label="批复文号/备注" min-width="150">
        <template #default="{ row }">
          <template v-if="row.isTotal">—</template>
          <template v-else>
            <el-input
              :model-value="row.approvalRef"
              size="small"
              :disabled="isReadonly"
              placeholder="批复文号"
              @change="(val: string) => handleCellChange(row.month, 'approvalRef', val)"
            />
          </template>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 联动卡片 ═══ -->
    <el-card shadow="never" class="linkage-card">
      <div class="linkage-content">
        <div class="linkage-value">
          <span class="linkage-label">不得免征和抵扣税额合计</span>
          <span class="linkage-amount">{{ fmtAmount(exportRefund.totalNonDeductible.value) }}</span>
        </div>
        <el-button
          type="primary"
          size="small"
          :disabled="isReadonly"
          @click="handleSyncToN26"
        >
          同步至N2-6(进项转出)
        </el-button>
      </div>
      <div v-if="exportRefund.diffMonths.value.length > 0" class="linkage-warning">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ exportRefund.diffMonths.value.map(m => m + '月').join('、') }}存在差异，需取得管理层解释</span>
      </div>
    </el-card>

    <!-- ═══ 审计说明+结论 ═══ -->
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
        :autosize="{ minRows: 5 }"
        :readonly="isReadonly"
        placeholder="请输入出口退税核对审计说明..."
        @change="handleNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>免抵退税额 = 出口销售额(FOB) × 退税率（自动计算）</li>
        <li>不得免征和抵扣税额 = 出口销售额 × (征税率 - 退税率) → 联动N2-6进项转出</li>
        <li>免抵税额 = 免抵退税额 - 应退税额（自动计算，非手工录入）</li>
        <li>差异 = 应退税额(批复) - 已退税额(实际到账)</li>
        <li>应退税额来自税务机关退税批复通知书(手工录入)，与免抵退测算结果交叉验证</li>
        <li>征税率是出口货物的增值税税率(13%/9%/6%)，退税率≤征税率</li>
        <li>差异≠0需取得合理解释：申报时间差/汇率/退税率调整/审批延迟</li>
        <li>核对结果联动N2-6增值税测算(不得免征和抵扣税额 = 进项转出)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabExportRefund — N2-7 出口退税核对表 (REWRITE)
 *
 * 对齐源xlsx模板：12个月行 + 年度合计，10列含4公式列
 * 核心联动：不得免征和抵扣税额合计 → N2-6进项转出
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, ChatDotSquare, WarningFilled } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useN2FormData } from '../../composables/useN2FormData'
import { useN2ExportRefund } from '../../composables/useN2ExportRefund'
import type { MonthlyExportRow } from '../../composables/useN2ExportRefund'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
  year?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((section: string) => void) | undefined>('openReviewDialog', undefined)
const scheduleAutoSnapshot = inject<(() => void) | undefined>('scheduleAutoSnapshot', undefined)

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
const batchVatRate = ref<number | undefined>(undefined)
const batchRefundRate = ref<number | undefined>(undefined)

// ─── Table data (12 monthly + 1 annual total row) ────────────────────────────

interface TableRow extends MonthlyExportRow {
  isTotal?: boolean
}

const tableData = computed<TableRow[]>(() => {
  const rows: TableRow[] = exportRefund.monthlyRows.value.map(r => ({ ...r, isTotal: false }))
  const s = exportRefund.annualSummary.value
  rows.push({
    month: 0,
    label: '合计',
    exportSalesFob: s.exportSalesFob,
    vatRate: 0,
    refundRate: 0,
    exemptCreditRefundAmt: s.exemptCreditRefundAmt,
    nonDeductible: s.nonDeductible,
    refundApproved: s.refundApproved,
    exemptCreditAmt: s.exemptCreditAmt,
    actualRefunded: s.actualRefunded,
    difference: s.difference,
    approvalRef: '',
    hasDiff: !s.allMatch,
    isTotal: true,
  })
  return rows
})

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: TableRow }) {
  if (!row) return ''
  if (row.isTotal) return 'row--annual-total'
  if (row.hasDiff) return 'row--diff'
  return ''
}

async function handleCellChange(month: number, field: string, value: any) {
  await exportRefund.setMonthlyData(
    month,
    field as any,
    value,
  )
  scheduleAutoSnapshot?.()
}

async function applyBatchVatRate(val: number) {
  if (!val) return
  await exportRefund.setBatchVatRate(val)
  ElMessage.success(`已设置全年征税率 ${(val * 100).toFixed(0)}%`)
  scheduleAutoSnapshot?.()
}

async function applyBatchRefundRate(val: number) {
  if (!val) return
  await exportRefund.setBatchRefundRate(val)
  ElMessage.success(`已设置全年退税率 ${(val * 100).toFixed(0)}%`)
  scheduleAutoSnapshot?.()
}

async function handleSyncToN26() {
  await exportRefund.syncToN26()
  scheduleAutoSnapshot?.()
  ElMessage.success('已同步不得免征和抵扣税额至N2-6(进项转出)')
}

function handleNoteChange() {
  formData.debouncedSave('N2-7-note', { remark: auditNote.value || null })
}

function handleAiAssist() {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'n2-export-refund',
      prompt: '请基于出口退税核对表数据，分析免抵退税额与批复差异原因，给出审计说明',
      context: {
        totalExportSales: String(exportRefund.annualSummary.value.exportSalesFob),
        totalNonDeductible: String(exportRefund.totalNonDeductible.value),
        totalDifference: String(exportRefund.annualSummary.value.difference),
        diffMonths: exportRefund.diffMonths.value.join(','),
      },
    }).then((res: any) => {
      if (res?.data?.content) {
        auditNote.value = res.data.content
        handleNoteChange()
      }
    }).catch(() => {})
  })
}

function handleReview() {
  openReviewDialog?.('N2-7-出口退税核对')
}

// ─── 导入导出 (placeholder) ──────────────────────────────────────────────────

function handleExportTemplate() {
  ElMessage.info('导出模板功能开发中')
}
function handleExportData() {
  ElMessage.info('导出数据功能开发中')
}
function handleImportData() {
  ElMessage.info('导入数据功能开发中')
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

.audit-objective {
  margin-bottom: 14px;
}
:deep(.el-alert__content) { padding: 2px 0; }
.ao-list {
  padding-left: 18px;
  line-height: 1.55;
  font-size: 12px;
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
.methodology-text strong { color: #b88230; }
.methodology-text em { color: #e6a23c; font-style: normal; font-weight: 600; }

/* ─── 配置工具栏 ─── */
.calc-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 14px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}
.toolbar-section {
  display: flex;
  align-items: center;
  gap: 6px;
}
.toolbar-label {
  font-size: 12px;
  color: #606266;
  white-space: nowrap;
}

/* ─── 表格 ─── */
.export-refund-table {
  font-size: 13px;
}
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}
.auto-calc-cell {
  background: #f5f7fa;
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  padding: 2px 4px;
  border-radius: 2px;
  color: #606266;
}
.diff-highlight {
  background: #fdf6ec !important;
  color: #e6a23c !important;
  font-weight: 700;
}
.total-cell {
  font-weight: 700;
  color: #303133;
}
:deep(.row--annual-total) {
  background: #f0f9eb !important;
  border-top: 2px solid #67c23a;
  font-weight: 700;
}
:deep(.row--diff) {
  background: #fdf6ec !important;
}

/* ─── 联动卡片 ─── */
.linkage-card {
  margin-top: 16px;
}
.linkage-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.linkage-value {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.linkage-label {
  font-size: 14px;
  color: #606266;
  font-weight: 500;
}
.linkage-amount {
  font-size: 18px;
  font-weight: 700;
  color: #409eff;
}
.linkage-warning {
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
  color: #e6a23c;
  font-size: 12px;
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
