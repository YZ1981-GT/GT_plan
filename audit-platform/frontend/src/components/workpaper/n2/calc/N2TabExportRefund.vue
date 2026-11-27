<template>
  <div class="n2-tab-export-refund">
    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title>审计目标</template>
      <ol class="ao-list">
        <li><strong>完整性</strong>：出口货物免抵退税申报汇总表 22 栏是否完整取数</li>
        <li><strong>准确性</strong>：免抵退税额、当期应退税额、免抵税额计算是否正确（征退税率差额产生的不予免征和抵扣税额联动 N2-6 进项转出）</li>
      </ol>
    </el-alert>

    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>免抵退税申报汇总表 N2-7</span>
        <el-tag type="info" size="small">22 栏 · 12 栏公式</el-tag>
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
        <strong>免抵退税公式（源模板）：</strong>
        ⑬免抵退税额 = ②免抵退出口销售额 × 退税率；
        ⑥不予免征和抵扣税额 = ①出口销售额 × (征税率 − 退税率) − ⑤ ← <em>进项转出的来源，联动 N2-6！</em>
        ㉑当期应退税额 = min(⑯当期免抵退税额, ⑳可退留抵税额)；㉒当期免抵税额 = ⑯ − ㉑。
        征税率是出口货物的增值税税率（13%/9%/6%），退税率 ≤ 征税率。
      </div>
    </div>

    <!-- ═══ 参数区：征税率 / 退税率 / 免税原材料 ═══ -->
    <div class="calc-toolbar">
      <div class="toolbar-section">
        <span class="toolbar-label">征税率：</span>
        <el-select
          :model-value="exportRefund.params.value.taxRateParam"
          size="small"
          style="width: 90px"
          :disabled="isReadonly"
          @change="(v: number) => handleParamChange('taxRateParam', v)"
        >
          <el-option :value="0.13" label="13%" />
          <el-option :value="0.09" label="9%" />
          <el-option :value="0.06" label="6%" />
        </el-select>
      </div>
      <div class="toolbar-section">
        <span class="toolbar-label">退税率：</span>
        <el-select
          :model-value="exportRefund.params.value.refundRateParam"
          size="small"
          style="width: 90px"
          :disabled="isReadonly"
          @change="(v: number) => handleParamChange('refundRateParam', v)"
        >
          <el-option :value="0.13" label="13%" />
          <el-option :value="0.10" label="10%" />
          <el-option :value="0.09" label="9%" />
          <el-option :value="0.06" label="6%" />
          <el-option :value="0.05" label="5%" />
        </el-select>
      </div>
      <div class="toolbar-section">
        <span class="toolbar-label">免税购进原材料成本：</span>
        <el-input-number
          :model-value="exportRefund.params.value.exemptMaterialCost"
          :precision="2"
          :controls="false"
          size="small"
          style="width: 160px"
          :disabled="isReadonly"
          @change="(v: number | undefined) => handleParamChange('exemptMaterialCost', v ?? 0)"
        />
      </div>
      <el-tag v-if="refundRateAboveTaxRate" type="danger" size="small">退税率高于征税率，请核对</el-tag>
    </div>

    <!-- ═══ 22 栏台账 ═══ -->
    <el-table
      :data="exportRefund.ledgerRows.value"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
      class="export-refund-table"
    >
      <el-table-column prop="line" label="栏次" width="60" align="center" />
      <el-table-column prop="label" label="项目" min-width="320" />
      <el-table-column label="金额" width="170" align="right">
        <template #default="{ row }">
          <el-tooltip v-if="row.auto" :content="`公式：${row.formula}`" placement="top">
            <span class="auto-calc-cell">{{ fmtAmount(row.amount) }}</span>
          </el-tooltip>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.amount"
            :precision="2"
            :controls="false"
            size="small"
            style="width: 100%"
            @change="(v: number | undefined) => handleAmountChange(row.line, v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注 / 文号" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            @change="(v: string) => handleRemarkChange(row.line, v)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 核心结论 + 联动 ═══ -->
    <el-card shadow="never" class="linkage-card">
      <div class="linkage-content">
        <div class="linkage-value">
          <span class="linkage-label">㉑当期应退税额</span>
          <span class="linkage-amount">{{ fmtAmount(exportRefund.totalRefundDue.value) }}</span>
          <span class="linkage-label">㉒当期免抵税额</span>
          <span class="linkage-amount">{{ fmtAmount(exportRefund.currentExemptCredit.value) }}</span>
        </div>
      </div>
      <div class="linkage-content linkage-row">
        <div class="linkage-value">
          <span class="linkage-label">⑥不予免征和抵扣税额（→N2-6 进项转出）</span>
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
        <li>⑬免抵退税额 = ②免抵退出口货物销售额 × 退税率（自动计算）</li>
        <li>⑥不予免征和抵扣税额 = ①出口销售额 × (征税率 − 退税率) − ⑤ → 联动N2-6进项转出</li>
        <li>㉑当期应退税额 = min(⑯当期免抵退税额, ⑳可退留抵税额)；㉒免抵税额 = ⑯ − ㉑（自动计算）</li>
        <li>录入栏取自企业《免抵退税申报汇总表》与增值税纳税申报表，与税务机关退税批复交叉核对</li>
        <li>征税率是出口货物的增值税税率(13%/9%/6%)，退税率≤征税率</li>
        <li>差异≠0需取得合理解释：申报时间差/汇率/退税率调整/审批延迟</li>
        <li>核对结果联动N2-6增值税测算(不得免征和抵扣税额 = 进项转出)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabExportRefund — N2-7 免抵退税申报汇总表（22 栏）
 *
 * 🔴 composable 早在 5ae6cd97d 改成 22 栏台账（REFUND_TEMPLATE），本页仍按旧「12 个月 × 10 列」读
 *    monthlyRows / annualSummary / diffMonths 等已删除的字段 ⇒ 渲染即报错、台账也从未 loadLedger。
 *    本页改按 22 栏台账渲染：参数区（征税率 / 退税率 / 免税原材料）+ 录入栏 + 公式栏只读。
 * 核心联动：⑥不予免征和抵扣税额 → N2-6 进项转出
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useN2FormData } from '../../composables/useN2FormData'
import { LINE_EXEMPT_CREDIT, LINE_REFUND_DUE, useN2ExportRefund } from '../../composables/useN2ExportRefund'
import type { RefundLedgerRow, RefundParams } from '../../composables/useN2ExportRefund'

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

/** 退税率不应高于征税率（源模板口径）；高于时只提示，不拦截 */
const refundRateAboveTaxRate = computed(
  () => exportRefund.params.value.refundRateParam > exportRefund.params.value.taxRateParam,
)

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (!val) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: RefundLedgerRow }) {
  if (!row) return ''
  if (row.line === LINE_REFUND_DUE || row.line === LINE_EXEMPT_CREDIT) return 'row--annual-total'
  return row.auto ? 'row--auto' : ''
}

async function handleParamChange(key: keyof RefundParams, value: number) {
  await exportRefund.setParam(key, value)
  scheduleAutoSnapshot?.()
}

async function handleAmountChange(line: number, value: number) {
  await exportRefund.setRowAmount(line, value)
  scheduleAutoSnapshot?.()
}

async function handleRemarkChange(line: number, value: string) {
  await exportRefund.setRowRemark(line, value)
  scheduleAutoSnapshot?.()
}

async function handleSyncToN26() {
  await exportRefund.syncToN26()
  scheduleAutoSnapshot?.()
  ElMessage.success('已同步不予免征和抵扣税额至N2-6(进项转出)')
}

function handleNoteChange() {
  formData.debouncedSave('N2-7-note', { remark: auditNote.value || null })
}

function handleAiAssist() {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'n2-export-refund',
      prompt: '请基于免抵退税申报汇总表数据，分析免抵退税额、当期应退税额与免抵税额，给出审计说明',
      context: {
        exportSalesFob: String(exportRefund.ledgerRows.value.find((r) => r.line === 1)?.amount ?? 0),
        totalRefundDue: String(exportRefund.totalRefundDue.value),
        currentExemptCredit: String(exportRefund.currentExemptCredit.value),
        totalNonDeductible: String(exportRefund.totalNonDeductible.value),
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
  exportRefund.loadLedger()
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
.linkage-row {
  margin-top: 10px;
}
:deep(.row--auto) {
  background: #fafafa;
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
