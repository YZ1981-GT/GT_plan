<script setup lang="ts">
/**
 * SamplingPreviewDialog — 抽样结果预览编辑弹窗
 *
 * Spec: .kiro/specs/voucher-sampling-engine/
 * Task: 8.1
 *
 * 功能：
 * - el-dialog（width=80vw，max-height=80vh）
 * - 统计卡片（表头上方）：总体笔数/金额 | 已勾选样本笔数/金额 | 笔数覆盖率% | 金额覆盖率%
 * - el-table 列：勾选框 | 凭证号 | 日期 | 摘要 | 借方 | 贷方 | 科目 | 科目名称 | 对方科目 | 凭证类型 | 会计期间 | 核查结果(inline) | 备注(inline)
 * - 默认全部勾选
 * - 金额列格式化
 * - 超100行启用 max-height 虚拟滚动
 * - truncated 时顶部黄色 el-alert
 * - "追加"按钮（搜索框弹出，从序时账搜索追加）— placeholder UI
 * - 底部：填充策略 el-radio-group（年审时 replace/merge disabled）+ "确认填充"按钮
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 7.5
 */
import { computed, ref } from 'vue'
import { Search, Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { SampledVoucher, CoverageStats, FillMode, CheckResult, Phase } from '../composables/useSamplingAlgorithms'

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  visible: boolean
  vouchers: SampledVoucher[]
  coverageStats: CoverageStats | null
  fillMode: FillMode
  isFillModeRestricted: boolean
  selectedCount: number
  selectedDebitTotal: number
  selectedCreditTotal: number
  /** 当前审计阶段，用于手工新增行标注 phase */
  phase?: Phase
  /**
   * 「确认填充」被上游门控阻断的原因（非空 ⇒ 按钮 disabled + tooltip 显示该原因）。
   *
   * 🔴 门控必须**前置**为 disabled，不能等用户勾完样本、点了按钮才弹 warning ——
   * 本弹窗带遮罩，提示里指向的「错报推断与总体结论」区在弹窗背后既看不到也点不到，
   * 那条提示等于死信（2026-08-04 浏览器实测：点确认填充后弹窗不关、四张表全 0 行、
   * 用户无从下手）。缺省 null = 无门控，行为与引入前逐字等价。
   */
  confirmBlockedReason?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  phase: 'preliminary',
  confirmBlockedReason: null,
})

// ─── Emits ────────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'update:fill-mode', v: FillMode): void
  (e: 'confirm'): void
  (e: 'toggle-select-all', v: boolean): void
}>()

// ─── Dialog visibility ────────────────────────────────────────────────────────

const dialogVisible = computed({
  get: () => props.visible,
  set: (v: boolean) => emit('update:visible', v),
})

// ─── Truncated 检测（>=500条） ────────────────────────────────────────────────

const isTruncated = computed(() => props.vouchers.length >= 500)

// ─── 超100行启用虚拟滚动（设置固定高度） ──────────────────────────────────────

const tableHeight = computed(() => {
  return props.vouchers.length > 100 ? 500 : undefined
})

// ─── 核查结果选项 ─────────────────────────────────────────────────────────────

const checkResultOptions: { value: CheckResult; label: string }[] = [
  { value: '', label: '（空）' },
  { value: 'Y', label: 'Y' },
  { value: 'N', label: 'N' },
  { value: '异常', label: '异常' },
]

// ─── 追加按钮：人工增补凭证（凭证号去重）─────────────────────────────────────

const appendSearchVisible = ref(false)
const appendForm = ref<{ voucherNo: string; voucherDate: string; debitAmount: string; creditAmount: string; summary: string }>(
  { voucherNo: '', voucherDate: '', debitAmount: '', creditAmount: '', summary: '' },
)

function handleOpenAppendSearch() {
  appendForm.value = { voucherNo: '', voucherDate: '', debitAmount: '', creditAmount: '', summary: '' }
  appendSearchVisible.value = true
}

/**
 * 人工新增勾选一条系统抽样未选中的凭证（R6.2）；按凭证号去重（R6.4）。
 * 若凭证号已存在则改为勾选该已有行而不重复添加。
 */
function handleAppendSearch() {
  const no = appendForm.value.voucherNo.trim()
  if (!no) {
    ElMessage.warning('请填写凭证号')
    return
  }
  // 凭证号去重：已存在则仅勾选
  const existing = props.vouchers.find(v => v.voucherNo === no)
  if (existing) {
    existing.selected = true
    ElMessage.info(`凭证号 ${no} 已存在，已为其勾选`)
    appendSearchVisible.value = false
    return
  }
  props.vouchers.push({
    voucherNo: no,
    voucherDate: appendForm.value.voucherDate || '',
    summary: appendForm.value.summary || null,
    debitAmount: appendForm.value.debitAmount ? String(appendForm.value.debitAmount) : null,
    creditAmount: appendForm.value.creditAmount ? String(appendForm.value.creditAmount) : null,
    accountCode: '',
    accountName: null,
    counterpartAccount: null,
    voucherType: null,
    accountingPeriod: null,
    checkResult: '',
    abnormal: false,
    remark: '',
    selected: true,
    phase: props.phase,
    editTrail: [],
  })
  ElMessage.success(`已新增凭证 ${no}`)
  appendSearchVisible.value = false
}

/**
 * 人工删除（移出已勾选样本集合）某条凭证（R6.3）。
 */
function handleRemoveRow(row: SampledVoucher) {
  const idx = props.vouchers.indexOf(row)
  if (idx >= 0) props.vouchers.splice(idx, 1)
}

// ─── Methods ──────────────────────────────────────────────────────────────────

function handleSelectionChange(selection: SampledVoucher[]) {
  const selectedNos = new Set(selection.map(v => v.voucherNo))
  props.vouchers.forEach(v => {
    v.selected = selectedNos.has(v.voucherNo)
  })
}

function handleSelectAll(selection: SampledVoucher[]) {
  const allSelected = selection.length === props.vouchers.length
  emit('toggle-select-all', allSelected)
}

/**
 * 金额格式化：千分位显示
 * - null/undefined → "-"
 * - "0" / "0.00" → "-"
 * - 其他 → 千分位格式，保留2位小数
 */
function formatAmount(value: string | null): string {
  if (value == null || value === '') return '-'
  const num = parseFloat(value)
  if (isNaN(num) || num === 0) return '-'
  return num.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

/** 统计金额格式化 */
function formatStatAmount(value: number | string): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(num) || num === 0) return '0.00'
  return num.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function handleFillModeChange(val: FillMode) {
  emit('update:fill-mode', val)
}

/** 确认填充是否被上游门控阻断 */
const isConfirmBlocked = computed(
  () => !!(props.confirmBlockedReason && props.confirmBlockedReason.trim()),
)

function handleConfirm() {
  // 双保险：即便调用方没传 confirmBlockedReason（旧调用点），命中门控也不 emit
  if (isConfirmBlocked.value) return
  emit('confirm')
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="抽样结果预览"
    width="80vw"
    :destroy-on-close="false"
    :close-on-click-modal="false"
    class="sampling-preview-dialog"
  >
    <!-- ═══ 截断警告提示 ═══ -->
    <el-alert
      v-if="isTruncated"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
    >
      <template #title>
        抽样结果已截断，仅显示前500条。建议缩小抽样条件范围或增加过滤约束。
      </template>
    </el-alert>

    <!-- ═══ 统计信息卡片 ═══ -->
    <div class="stats-card">
      <div class="stats-item">
        <span class="stats-label">总体笔数/金额</span>
        <span class="stats-value">
          <strong>{{ coverageStats?.populationCount ?? 0 }}</strong>
          <span class="stats-sub">/ {{ formatStatAmount(coverageStats?.populationAmount ?? '0') }}</span>
        </span>
      </div>
      <div class="stats-divider" />
      <div class="stats-item">
        <span class="stats-label">已勾选样本笔数/金额</span>
        <span class="stats-value">
          <strong>{{ selectedCount }}</strong>
          <span class="stats-sub">/ {{ formatStatAmount(selectedDebitTotal + selectedCreditTotal) }}</span>
        </span>
      </div>
      <div class="stats-divider" />
      <div class="stats-item">
        <span class="stats-label">笔数覆盖率</span>
        <span class="stats-value stats-rate">
          <strong>{{ coverageStats?.countCoverageRate ?? '0.00' }}%</strong>
        </span>
      </div>
      <div class="stats-divider" />
      <div class="stats-item">
        <span class="stats-label">金额覆盖率</span>
        <span class="stats-value stats-rate">
          <strong>{{ coverageStats?.amountCoverageRate ?? '0.00' }}%</strong>
        </span>
      </div>
    </div>

    <!-- ═══ 操作按钮区 ═══ -->
    <div class="action-bar">
      <el-button size="small" type="primary" plain @click="handleOpenAppendSearch">
        + 追加凭证
      </el-button>
    </div>

    <!-- ═══ 凭证表格 ═══ -->
    <el-table
      :data="vouchers"
      :height="tableHeight"
      :max-height="500"
      border
      size="small"
      class="voucher-table"
      @selection-change="handleSelectionChange"
      @select-all="handleSelectAll"
    >
      <!-- 勾选框列 -->
      <el-table-column type="selection" width="45" align="center" />

      <!-- 凭证号 -->
      <el-table-column prop="voucherNo" label="凭证号" min-width="100" show-overflow-tooltip />

      <!-- 凭证日期 -->
      <el-table-column prop="voucherDate" label="日期" min-width="100" show-overflow-tooltip />

      <!-- 摘要 -->
      <el-table-column prop="summary" label="摘要" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.summary || '-' }}
        </template>
      </el-table-column>

      <!-- 借方金额 -->
      <el-table-column label="借方" min-width="110" align="right">
        <template #default="{ row }">
          {{ formatAmount(row.debitAmount) }}
        </template>
      </el-table-column>

      <!-- 贷方金额 -->
      <el-table-column label="贷方" min-width="110" align="right">
        <template #default="{ row }">
          {{ formatAmount(row.creditAmount) }}
        </template>
      </el-table-column>

      <!-- 科目编码 -->
      <el-table-column prop="accountCode" label="科目" min-width="90" show-overflow-tooltip />

      <!-- 科目名称 -->
      <el-table-column prop="accountName" label="科目名称" min-width="110" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.accountName || '-' }}
        </template>
      </el-table-column>

      <!-- 对方科目 -->
      <el-table-column prop="counterpartAccount" label="对方科目" min-width="90" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.counterpartAccount || '-' }}
        </template>
      </el-table-column>

      <!-- 凭证类型 -->
      <el-table-column prop="voucherType" label="凭证类型" width="80" align="center">
        <template #default="{ row }">
          {{ row.voucherType || '-' }}
        </template>
      </el-table-column>

      <!-- 会计期间 -->
      <el-table-column prop="accountingPeriod" label="会计期间" width="80" align="center">
        <template #default="{ row }">
          {{ row.accountingPeriod != null ? `${row.accountingPeriod}月` : '-' }}
        </template>
      </el-table-column>

      <!-- 核查结果（inline 编辑） -->
      <el-table-column label="核查结果" width="100" align="center">
        <template #default="{ row }">
          <el-select
            v-model="row.checkResult"
            size="small"
            placeholder="选择"
            clearable
            style="width: 80px"
          >
            <el-option
              v-for="opt in checkResultOptions"
              :key="opt.value"
              :value="opt.value"
              :label="opt.label"
            />
          </el-select>
        </template>
      </el-table-column>

      <!-- 高值必选标识（MUS，R17.4） -->
      <el-table-column label="高值" width="70" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.isHighValue" size="small" type="danger" effect="plain">
            高值必选
          </el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>

      <!-- 特定选取原因（inline 编辑，随样本回填，R6.5） -->
      <el-table-column label="特定选取原因" min-width="140">
        <template #default="{ row }">
          <el-input
            v-model="row.selectionReason"
            size="small"
            placeholder="如：大额/关联方/异常"
            clearable
          />
        </template>
      </el-table-column>

      <!-- 备注（inline 编辑） -->
      <el-table-column label="备注" min-width="140">
        <template #default="{ row }">
          <el-input
            v-model="row.remark"
            size="small"
            placeholder="输入备注"
            clearable
          />
        </template>
      </el-table-column>

      <!-- 操作：人工删除（移出样本，R6.3） -->
      <el-table-column label="操作" width="70" align="center">
        <template #default="{ row }">
          <el-button
            type="danger"
            :icon="Delete"
            circle
            size="small"
            plain
            @click="handleRemoveRow(row)"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 底部操作区 ═══ -->
    <div class="dialog-footer">
      <div class="fill-mode-section">
        <span class="fill-mode-label">填充策略：</span>
        <el-radio-group :model-value="fillMode" @change="handleFillModeChange">
          <el-radio value="append">追加</el-radio>
          <el-tooltip
            :disabled="!isFillModeRestricted"
            content="年审阶段不可覆盖预审数据"
            placement="top"
          >
            <el-radio value="replace" :disabled="isFillModeRestricted">替换</el-radio>
          </el-tooltip>
          <el-tooltip
            :disabled="!isFillModeRestricted"
            content="年审阶段不可覆盖预审数据"
            placement="top"
          >
            <el-radio value="merge" :disabled="isFillModeRestricted">合并去重</el-radio>
          </el-tooltip>
        </el-radio-group>
      </div>
      <el-tooltip
        :disabled="!isConfirmBlocked"
        :content="confirmBlockedReason || ''"
        placement="top"
      >
        <!-- disabled 按钮不触发鼠标事件 → 必须套一层 span 才有 tooltip 宿主 -->
        <span class="confirm-fill-wrap">
          <el-button
            type="primary"
            :disabled="isConfirmBlocked"
            data-testid="sampling-preview-confirm"
            @click="handleConfirm"
          >
            确认填充
          </el-button>
        </span>
      </el-tooltip>
    </div>

    <!-- ═══ 人工增补凭证弹窗（凭证号去重）═══ -->
    <el-dialog
      v-model="appendSearchVisible"
      title="人工增补凭证"
      width="500px"
      append-to-body
      :close-on-click-modal="false"
    >
      <div class="append-search-content">
        <el-form label-width="80px" size="small">
          <el-form-item label="凭证号" required>
            <el-input v-model="appendForm.voucherNo" placeholder="必填，如 记-0123" clearable>
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </el-form-item>
          <el-form-item label="日期">
            <el-input v-model="appendForm.voucherDate" placeholder="如 2025-12-31" clearable />
          </el-form-item>
          <el-form-item label="借方金额">
            <el-input v-model="appendForm.debitAmount" placeholder="选填（元）" clearable />
          </el-form-item>
          <el-form-item label="贷方金额">
            <el-input v-model="appendForm.creditAmount" placeholder="选填（元）" clearable />
          </el-form-item>
          <el-form-item label="摘要">
            <el-input v-model="appendForm.summary" placeholder="选填" clearable />
          </el-form-item>
        </el-form>
        <div class="append-hint">
          手工增补的凭证将默认勾选并纳入样本；相同凭证号自动去重。
        </div>
      </div>
      <template #footer>
        <el-button @click="appendSearchVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAppendSearch">确认追加</el-button>
      </template>
    </el-dialog>
  </el-dialog>
</template>

<style scoped>
.sampling-preview-dialog :deep(.el-dialog__body) {
  max-height: 80vh;
  overflow-y: auto;
  padding: 16px 20px;
}

/* ── 统计信息卡片 ── */
.stats-card {
  display: flex;
  align-items: center;
  gap: 0;
  padding: 10px 16px;
  margin-bottom: 12px;
  background: #f5f7fa;
  border-radius: 4px;
  border: 1px solid #e4e7ed;
}

.stats-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  gap: 2px;
}

.stats-label {
  font-size: 12px;
  color: #909399;
}

.stats-value {
  font-size: 14px;
  color: #303133;
}

.stats-value strong {
  font-size: 16px;
}

.stats-sub {
  font-size: 12px;
  color: #909399;
  margin-left: 4px;
}

.stats-rate strong {
  color: #409eff;
}

.stats-divider {
  width: 1px;
  height: 32px;
  background: #dcdfe6;
  margin: 0 8px;
}

/* ── 操作按钮区 ── */
.action-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  margin-bottom: 8px;
}

/* ── 表格样式 ── */
.voucher-table {
  font-size: var(--wp-font-size, 13px);
}

.voucher-table :deep(.el-table__row) {
  font-size: var(--wp-font-size, 13px);
}

.voucher-table :deep(.el-table__header th) {
  font-size: var(--wp-font-size, 13px);
}

/* ── 底部操作区 ── */
.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #ebeef5;
}

.fill-mode-section {
  display: flex;
  align-items: center;
  gap: 8px;
}

.fill-mode-label {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  white-space: nowrap;
}

/* ── 人工增补弹窗 ── */
.append-search-content {
  min-height: 200px;
}

.append-hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  margin-top: 8px;
  line-height: 1.5;
}

/* ── 表格内输入框优化 ── */
.voucher-table :deep(.el-input__inner) {
  font-size: var(--wp-font-size, 13px);
}

.voucher-table :deep(.el-select .el-input__inner) {
  font-size: var(--wp-font-size, 13px);
}
</style>
