<script setup lang="ts">
/**
 * GtVoucherSamplingEngine — 通用抽凭引擎主组件
 *
 * Spec: .kiro/specs/voucher-sampling-engine/
 * Task: 6.1
 *
 * 通用组件：通过 props 配置适配 D2-7/D4-14/D4-15/E2-7 等所有抽凭底稿
 * Requirements: 5.4, 8.3, 9.1, 9.3, 10.1, 10.3, 10.4, 10.5, 12.3
 */
import { defineAsyncComponent, toRef, computed, ref } from 'vue'
import { useVoucherSampling } from '../composables/useVoucherSampling'
import { useSamplingPhase, type ViewMode } from '../composables/useSamplingPhase'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import type {
  Phase,
  SamplingMethod,
  FillMode,
  SampledVoucher,
  CheckResult,
} from '../composables/useSamplingAlgorithms'

// ─── 异步加载子组件（后续任务实现） ──────────────────────────────────────────

const SamplingConfigDialog = defineAsyncComponent(() =>
  import('./SamplingConfigDialog.vue'),
)
const SamplingPreviewDialog = defineAsyncComponent(() =>
  import('./SamplingPreviewDialog.vue'),
)
const SamplingHistoryDrawer = defineAsyncComponent(() =>
  import('./SamplingHistoryDrawer.vue'),
)
const SamplingComparePanel = defineAsyncComponent(() =>
  import('./SamplingComparePanel.vue'),
)

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  accountCode: string
  phase: Phase
  defaultMethod?: SamplingMethod
  workpaperId: string
  projectId: string
  year: number
}

const props = defineProps<Props>()

// ─── Emits ────────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  (e: 'filled', payload: { samples: SampledVoucher[]; phase: Phase; fillMode: FillMode; method?: SamplingMethod }): void
  (e: 'phase-changed', payload: { phase: Phase }): void
}>()

// ─── Composable: useVoucherSampling ───────────────────────────────────────────

const {
  config,
  sampledVouchers,
  coverageStats,
  complianceWarnings,
  loading,
  configDialogVisible,
  previewVisible,
  historyVisible,
  historyList,
  fillMode,
  selectedVouchers,
  selectedCount,
  selectedDebitTotal,
  selectedCreditTotal,
  triggerSampling,
  confirmFill,
  loadHistory,
  undoLastExtraction,
  compareVersions,
  toggleSelectAll,
  updateField,
  batchMarkChecked,
  validateConfig,
  configErrors,
  checkCompliance,
} = useVoucherSampling({
  projectId: toRef(props, 'projectId'),
  year: toRef(props, 'year'),
  workpaperId: toRef(props, 'workpaperId'),
  accountCode: props.accountCode,
  phase: toRef(props, 'phase'),
  defaultMethod: props.defaultMethod,
})

// ─── Composable: useSamplingPhase ─────────────────────────────────────────────

const {
  viewMode,
  visibleSamples,
  isRowEditable,
  isFillModeRestricted,
} = useSamplingPhase({
  phase: toRef(props, 'phase'),
  samples: sampledVouchers,
})

// ─── 已填充 samples（由父组件外部管理，本组件内展示 sampledVouchers） ──────────

/** 核查结果选项 */
const checkResultOptions: { label: string; value: CheckResult }[] = [
  { label: '—', value: '' },
  { label: 'Y', value: 'Y' },
  { label: 'N', value: 'N' },
  { label: '异常', value: '异常' },
]

// ─── 行样式：预审行在年审阶段 disabled ───────────────────────────────────────

function getRowClassName({ row }: { row: SampledVoucher }): string {
  if (!isRowEditable(row)) {
    return 'row-disabled'
  }
  return ''
}

// ─── 操作 ─────────────────────────────────────────────────────────────────────

/** 打开配置弹窗 */
function handleOpenConfig() {
  configDialogVisible.value = true
}

/** 打开历史侧栏 */
function handleShowHistory() {
  loadHistory()
}

/** 批量标记已核查：标记当前可见行 */
function handleBatchMarkChecked() {
  const indices: number[] = []
  visibleSamples.value.forEach((row) => {
    if (isRowEditable(row)) {
      const idx = sampledVouchers.value.indexOf(row)
      if (idx >= 0) indices.push(idx)
    }
  })
  if (indices.length > 0) {
    batchMarkChecked(indices)
  }
}

/** 确认填充后 emit */
async function handleConfirmFill() {
  const result = await confirmFill()
  if (result.length > 0) {
    emit('filled', {
      samples: result,
      phase: props.phase,
      fillMode: isFillModeRestricted.value ? 'append' : fillMode.value,
      method: config.value.samplingMethod,
    })
    // 检查合规性
    checkCompliance()
  }
}

/** 视图模式切换 */
function handleViewModeChange(val: ViewMode) {
  viewMode.value = val
}

// ─── 版本对比 ─────────────────────────────────────────────────────────────────

const comparePanelVisible = ref(false)
const compareResult = ref<{ added: string[]; removed: string[]; retained: string[] }>({
  added: [],
  removed: [],
  retained: [],
})

/** 处理历史侧栏的对比请求 */
async function handleCompare(logIdA: string, logIdB: string) {
  const result = await compareVersions(logIdA, logIdB)
  compareResult.value = {
    added: result.added.map(v => v.voucherNo),
    removed: result.removed.map(v => v.voucherNo),
    retained: result.retained.map(v => v.voucherNo),
  }
  comparePanelVisible.value = true
}

/** 行内编辑：核查结果 */
function handleCheckResultChange(row: SampledVoucher, val: CheckResult) {
  const idx = sampledVouchers.value.indexOf(row)
  if (idx >= 0) updateField(idx, 'checkResult', val)
}

/** 行内编辑：异常标记 */
function handleAbnormalChange(row: SampledVoucher, val: boolean) {
  const idx = sampledVouchers.value.indexOf(row)
  if (idx >= 0) updateField(idx, 'abnormal', val)
}

/** 行内编辑：备注 */
function handleRemarkChange(row: SampledVoucher, val: string) {
  const idx = sampledVouchers.value.indexOf(row)
  if (idx >= 0) updateField(idx, 'remark', val)
}

// ─── 覆盖率 computed ──────────────────────────────────────────────────────────

const countCoverageDisplay = computed(() => {
  if (!coverageStats.value) return '—'
  return `${coverageStats.value.countCoverageRate}%`
})

const amountCoverageDisplay = computed(() => {
  if (!coverageStats.value) return '—'
  return `${coverageStats.value.amountCoverageRate}%`
})
</script>

<template>
  <div class="gt-voucher-sampling-engine">
    <!-- ═══ 覆盖率统计卡片 ═══ -->
    <div class="coverage-stats-bar">
      <div class="stat-card">
        <span class="stat-label">笔数覆盖率</span>
        <span class="stat-value">{{ countCoverageDisplay }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">金额覆盖率</span>
        <span class="stat-value">{{ amountCoverageDisplay }}</span>
      </div>
      <div class="stat-card" v-if="coverageStats">
        <span class="stat-label">样本/总体</span>
        <span class="stat-value">{{ coverageStats.sampleCount }} / {{ coverageStats.populationCount }}</span>
      </div>
    </div>

    <!-- ═══ 视图模式切换 ═══ -->
    <div class="view-mode-bar">
      <el-radio-group
        :model-value="viewMode"
        size="small"
        @change="handleViewModeChange"
      >
        <el-radio-button value="all">全量</el-radio-button>
        <el-radio-button value="preliminary">仅预审</el-radio-button>
        <el-radio-button value="final">仅年审</el-radio-button>
      </el-radio-group>
    </div>

    <!-- ═══ CAS 1314 合规警告区 ═══ -->
    <div v-if="complianceWarnings.length > 0" class="compliance-warnings">
      <el-alert
        v-for="(warn, idx) in complianceWarnings"
        :key="idx"
        :title="warn.message"
        :type="warn.level === 'warning' ? 'warning' : 'info'"
        :closable="false"
        show-icon
        class="compliance-alert"
      />
    </div>

    <!-- ═══ 操作栏 ═══ -->
    <div class="action-bar">
      <el-button type="primary" size="small" :loading="loading" @click="handleOpenConfig">
        自动抽凭
      </el-button>
      <el-button size="small" @click="handleShowHistory">
        抽凭历史
      </el-button>
      <el-button size="small" @click="handleBatchMarkChecked">
        批量标记已核查
      </el-button>
    </div>

    <!-- ═══ 主体表格 ═══ -->
    <el-table
      :data="visibleSamples"
      :row-class-name="getRowClassName"
      border
      stripe
      size="small"
      class="sampling-table"
      empty-text='暂无抽凭数据，请点击「自动抽凭」开始'
    >
      <el-table-column prop="voucherNo" label="凭证号" min-width="100" show-overflow-tooltip />
      <el-table-column prop="voucherDate" label="日期" min-width="100" show-overflow-tooltip />
      <el-table-column prop="summary" label="摘要" min-width="160" show-overflow-tooltip />
      <el-table-column label="借方" min-width="110" align="right">
        <template #default="{ row }">
          <GtAmountCell :value="row.debitAmount" />
        </template>
      </el-table-column>
      <el-table-column label="贷方" min-width="110" align="right">
        <template #default="{ row }">
          <GtAmountCell :value="row.creditAmount" />
        </template>
      </el-table-column>
      <el-table-column prop="accountCode" label="科目" min-width="90" show-overflow-tooltip />
      <el-table-column prop="voucherType" label="凭证类型" min-width="80" align="center" />
      <!-- 核查结果（inline select） -->
      <el-table-column label="核查结果" min-width="100" align="center">
        <template #default="{ row }">
          <el-select
            :model-value="row.checkResult"
            size="small"
            :disabled="!isRowEditable(row)"
            placeholder="—"
            @change="(val: CheckResult) => handleCheckResultChange(row, val)"
          >
            <el-option
              v-for="opt in checkResultOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </template>
      </el-table-column>
      <!-- 异常（inline switch） -->
      <el-table-column label="异常" min-width="70" align="center">
        <template #default="{ row }">
          <el-switch
            :model-value="row.abnormal"
            size="small"
            :disabled="!isRowEditable(row)"
            @change="(val: boolean) => handleAbnormalChange(row, val)"
          />
        </template>
      </el-table-column>
      <!-- 备注（inline input） -->
      <el-table-column label="备注" min-width="140">
        <template #default="{ row }">
          <el-input
            :model-value="row.remark"
            size="small"
            :disabled="!isRowEditable(row)"
            placeholder="备注"
            @change="(val: string) => handleRemarkChange(row, val)"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 嵌入子组件（异步加载） ═══ -->
    <SamplingConfigDialog
      v-if="configDialogVisible"
      v-model:visible="configDialogVisible"
      :config="config"
      :config-errors="configErrors"
      :loading="loading"
      @execute="triggerSampling"
    />

    <SamplingPreviewDialog
      v-if="previewVisible"
      v-model:visible="previewVisible"
      :vouchers="sampledVouchers"
      :coverage-stats="coverageStats"
      :fill-mode="fillMode"
      :is-fill-mode-restricted="isFillModeRestricted"
      :selected-count="selectedCount"
      :selected-debit-total="selectedDebitTotal"
      :selected-credit-total="selectedCreditTotal"
      @update:fill-mode="(v: FillMode) => fillMode = v"
      @confirm="handleConfirmFill"
      @toggle-select-all="toggleSelectAll"
    />

    <SamplingHistoryDrawer
      v-if="historyVisible"
      v-model:visible="historyVisible"
      :history-list="historyList"
      @undo="undoLastExtraction"
      @compare="handleCompare"
    />

    <SamplingComparePanel
      v-if="comparePanelVisible"
      v-model:visible="comparePanelVisible"
      :compare-result="compareResult"
    />
  </div>
</template>

<style scoped>
.gt-voucher-sampling-engine {
  padding: 12px 0;
}

/* ── 覆盖率统计卡片 ── */
.coverage-stats-bar {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: 6px;
  padding: 10px 20px;
  min-width: 120px;
}

.stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
  margin-bottom: 4px;
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--el-color-primary, #409eff);
}

/* ── 视图模式切换 ── */
.view-mode-bar {
  margin-bottom: 12px;
}

/* ── CAS 1314 合规警告 ── */
.compliance-warnings {
  margin-bottom: 12px;
}

.compliance-alert {
  margin-bottom: 6px;
}

.compliance-alert:last-child {
  margin-bottom: 0;
}

/* ── 操作栏 ── */
.action-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

/* ── 主体表格 ── */
.sampling-table {
  font-size: 13px;
}

.sampling-table :deep(.el-table__row) {
  font-size: 13px;
}

/* 预审行在年审阶段 disabled 样式 */
.sampling-table :deep(.row-disabled) {
  background-color: var(--el-fill-color-lighter, #fafafa) !important;
  opacity: 0.65;
  pointer-events: none;
}

.sampling-table :deep(.row-disabled) .el-input,
.sampling-table :deep(.row-disabled) .el-select,
.sampling-table :deep(.row-disabled) .el-switch {
  cursor: not-allowed;
}

/* inline 编辑控件紧凑 */
.sampling-table :deep(.el-select) {
  width: 80px;
}

.sampling-table :deep(.el-input) {
  width: 100%;
}
</style>
