<template>
  <div class="n2-tab-vat-calc">
    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>增值税测算表 N2-6</span>
        <el-tag type="info" size="small">48×8 销项-进项</el-tag>
      </div>
      <div class="section-actions">
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
        <strong>增值税测算逻辑：</strong>
        应交增值税 = 销项税额 - (进项税额 - 进项转出)。销项税额 = 销售额 × 适用税率。
        按月/季度分行汇总全年增值税应交额，并计算税负率 = 应交增值税 / 销售额。
        测算结果回填N2-1审定表增值税行，并为N2-8城建税等提供计税依据。
      </div>
    </div>

    <!-- ═══ 计算周期切换 + 税负率展示 ═══ -->
    <div class="calc-toolbar">
      <div class="period-switch">
        <span class="toolbar-label">计算周期：</span>
        <el-segmented
          :model-value="vatCalc.periodMode.value"
          :options="[{ label: '按月', value: 'monthly' }, { label: '按季度', value: 'quarterly' }]"
          @change="handlePeriodModeChange"
        />
      </div>
      <div class="burden-rate-display">
        <span class="toolbar-label">年度税负率：</span>
        <el-tag
          :type="burdenRateType"
          size="large"
          effect="dark"
        >
          {{ fmtPercent(vatCalc.annualSummary.value.annualBurdenRate) }}
        </el-tag>
      </div>
    </div>

    <!-- ═══ 增值税测算明细表 ═══ -->
    <el-table
      :data="vatCalc.rows.value"
      border
      size="small"
      style="width: 100%"
      show-summary
      :summary-method="getSummaryRow"
    >
      <el-table-column prop="period" label="期间" width="90" fixed />
      <el-table-column label="销售额" width="130" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            :model-value="row.salesAmount"
            :disabled="isReadonly"
            :controls="false"
            :precision="2"
            size="small"
            style="width: 110px"
            @change="(val: number) => handleCellChange($index, 'salesAmount', val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="税率" width="90" align="center">
        <template #default="{ row, $index }">
          <el-select
            :model-value="row.taxRate"
            size="small"
            :disabled="isReadonly"
            style="width: 72px"
            @change="(val: number) => handleCellChange($index, 'taxRate', val)"
          >
            <el-option :value="0.13" label="13%" />
            <el-option :value="0.09" label="9%" />
            <el-option :value="0.06" label="6%" />
            <el-option :value="0.05" label="5%" />
            <el-option :value="0.03" label="3%" />
            <el-option :value="0" label="免税" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="销项税额" width="130" align="right">
        <template #header>
          <el-tooltip content="公式：销售额 × 税率" placement="top">
            <span class="formula-col-header">销项税额</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-cell">{{ fmtAmount(row.outputVat) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="进项税额" width="130" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            :model-value="row.inputVat"
            :disabled="isReadonly"
            :controls="false"
            :precision="2"
            size="small"
            style="width: 110px"
            @change="(val: number) => handleCellChange($index, 'inputVat', val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="进项转出" width="130" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            :model-value="row.inputTransferOut"
            :disabled="isReadonly"
            :controls="false"
            :precision="2"
            size="small"
            style="width: 110px"
            @change="(val: number) => handleCellChange($index, 'inputTransferOut', val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="应交增值税" width="130" align="right">
        <template #header>
          <el-tooltip content="公式：销项税额 - (进项税额 - 进项转出)" placement="top">
            <span class="formula-col-header">应交增值税</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-cell" :class="{ 'formula-cell--negative': row.payableVat < 0 }">
            {{ fmtAmount(row.payableVat) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="已交税额" width="130" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            :model-value="row.paidVat"
            :disabled="isReadonly"
            :controls="false"
            :precision="2"
            size="small"
            style="width: 110px"
            @change="(val: number) => handleCellChange($index, 'paidVat', val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="未交税额" width="120" align="right">
        <template #header>
          <el-tooltip content="公式：应交 - 已交" placement="top">
            <span class="formula-col-header">未交税额</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-cell" :class="{ 'formula-cell--negative': row.unpaidVat < 0 }">
            {{ fmtAmount(row.unpaidVat) }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 申报表核对 ═══ -->
    <el-card shadow="never" class="declaration-card">
      <template #header>
        <div class="card-header">
          <span>与增值税纳税申报表核对</span>
          <el-tag
            :type="vatCalc.declarationCheck.value.isMatch ? 'success' : 'danger'"
            size="small"
          >
            {{ vatCalc.declarationCheck.value.isMatch ? '核对一致' : '存在差异' }}
          </el-tag>
        </div>
      </template>
      <div class="declaration-grid">
        <div class="decl-item">
          <span class="decl-label">测算应交增值税：</span>
          <span class="decl-value">{{ fmtAmount(vatCalc.annualSummary.value.totalPayableVat) }}</span>
        </div>
        <div class="decl-item">
          <span class="decl-label">申报表应交增值税：</span>
          <el-input-number
            :model-value="vatCalc.declarationCheck.value.declaredPayableVat"
            :disabled="isReadonly"
            :controls="false"
            :precision="2"
            size="small"
            style="width: 140px"
            @change="handleDeclaredChange"
          />
        </div>
        <div class="decl-item">
          <span class="decl-label">差异：</span>
          <span
            class="decl-value"
            :class="{ 'decl-value--diff': !vatCalc.declarationCheck.value.isMatch }"
          >
            {{ fmtAmount(vatCalc.declarationCheck.value.diff) }}
          </span>
        </div>
      </div>
    </el-card>

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
        placeholder="请输入增值税测算审计说明..."
        @change="handleNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>按月/季度逐期录入销售额、进项税额、进项转出、已交税额</li>
        <li>销项税额 = 销售额 × 适用税率（公式自动计算）</li>
        <li>应交增值税 = 销项 - (进项 - 进项转出)（公式自动计算）</li>
        <li>税负率 = 年度应交增值税 / 年度销售额（汇总自动计算）</li>
        <li>应交为负（留抵）时红色显示，提示留抵税额</li>
        <li>与增值税纳税申报表核对，差异需说明原因</li>
        <li>测算结果自动回填N2-1增值税行、供N2-8城建税计税依据</li>
      </ul>
    </details>

    <!-- ═══ 跨底稿联动（cross_wp_ref GtIndexChip）Task 6.2 ═══ -->
    <div class="cross-wp-links">
      <span class="cross-wp-label">cross_wp_ref 联动去向：</span>
      <GtIndexChip value="N2-1" />
      <span class="cross-wp-desc">审定表增值税行回填</span>
      <GtIndexChip value="N2-8" />
      <span class="cross-wp-desc">城建税计税依据（应交增值税）</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabVatCalc — N2-6 增值税测算表
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 4.9
 * Requirements: 4.1-4.6
 *
 * 核心职责：
 * - 48×8 销项-进项测算
 * - 按月/季度分行 + 税负率分析
 * - 回填N2-1增值税行 + 供N2-8计税依据
 * - Uses useN2VatCalc composable
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useN2FormData } from '../../composables/useN2FormData'
import { useN2VatCalc, type VatCalcPeriodMode } from '../../composables/useN2VatCalc'

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

const vatCalc = useN2VatCalc({
  allResponses: formData.allResponses,
  saveField: formData.saveField,
  getField: formData.getField,
})

// ─── State ───────────────────────────────────────────────────────────────────

const isReadonly = computed(() => props.isReadonly ?? false)
const auditNote = ref('')

// ─── Computed ────────────────────────────────────────────────────────────────

/** 税负率颜色级别 */
const burdenRateType = computed(() => {
  const rate = vatCalc.annualSummary.value.annualBurdenRate
  if (rate <= 0) return 'info'
  if (rate < 0.02) return 'warning' // 偏低
  if (rate > 0.10) return 'danger' // 偏高
  return 'success' // 正常
})

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number): string {
  if (!Number.isFinite(val)) return '—'
  return (val * 100).toFixed(2) + '%'
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function handlePeriodModeChange(val: string | number) {
  vatCalc.setPeriodMode(val as VatCalcPeriodMode)
}

function handleCellChange(index: number, field: 'salesAmount' | 'taxRate' | 'inputVat' | 'inputTransferOut' | 'paidVat', val: number) {
  vatCalc.updateRow(index, field, val ?? 0)
}

function handleDeclaredChange(val: number) {
  formData.saveField('6', 'declared-payable-vat', val ?? 0)
}

function handleNoteChange() {
  formData.debouncedSave('N2-6-note', { remark: auditNote.value || null })
}

function handleAiAssist() {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'n2-vat-calc',
      prompt: '请基于应交税费底稿数据，给出审计分析建议',
      context: { wpId: props.wpId },
    }).catch(() => {})
  })
}

function handleReview() {
  openReviewDialog?.('N2-6-增值税测算')
}

/** 合计行 */
function getSummaryRow({ columns, data }: { columns: any[]; data: any[] }) {
  const sums: string[] = []
  columns.forEach((_col: any, index: number) => {
    if (index === 0) { sums[index] = '合计'; return }
    const s = vatCalc.annualSummary.value
    const map: Record<number, number> = {
      1: s.totalSales,
      3: s.totalOutputVat,
      4: s.totalInputVat,
      5: s.totalInputTransferOut,
      6: s.totalPayableVat,
      7: s.totalPaidVat,
      8: s.totalUnpaidVat,
    }
    sums[index] = map[index] != null ? fmtAmount(map[index]) : ''
  })
  return sums
}

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  const noteResp = formData.allResponses.value.get('N2-6-note')
  if (noteResp?.remark) auditNote.value = noteResp.remark
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  restoreData()
})
</script>

<style scoped>
.n2-tab-vat-calc {
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

/* ─── 工具栏 ─── */
.calc-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding: 10px 14px;
  background: #f5f7fa;
  border-radius: 6px;
}

.period-switch,
.burden-rate-display {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-label {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  white-space: nowrap;
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

.formula-cell--negative {
  color: #f56c6c;
}

/* ─── 申报表核对 ─── */
.declaration-card {
  margin-top: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

.declaration-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.decl-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.decl-label {
  color: #606266;
  white-space: nowrap;
}

.decl-value {
  font-weight: 600;
  color: #303133;
}

.decl-value--diff {
  color: #f56c6c;
}

/* ─── 结论卡片 ─── */
.conclusion-card {
  margin-top: 16px;
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

/* ─── 跨底稿联动 cross_wp_ref ─── */
.cross-wp-links {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  margin-top: 12px;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 6px;
  font-size: 12px;
}

.cross-wp-label {
  color: #0369a1;
  font-weight: 500;
  margin-right: 4px;
}

.cross-wp-desc {
  color: #64748b;
  margin-right: 8px;
}
</style>
