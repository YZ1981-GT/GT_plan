<script setup lang="ts">
/**
 * CutoffPreviewDialog — 截止测试提取结果预览编辑弹窗
 *
 * Spec: .kiro/specs/cutoff-test-auto-sampling/
 * Task: 8.1
 *
 * 功能：
 * - el-dialog 展示提取凭证结果表格
 * - 统计信息卡片：已勾选/总笔数 | 跨期笔数 | 借方合计 | 贷方合计
 * - 表格列：勾选框 | 凭证号 | 凭证日期 | 摘要 | 借方金额 | 贷方金额 | 科目编码 | 科目名称 | 对方科目 | 凭证类型 | 跨期判定 | 备注
 * - 跨期判定="可能跨期" → 红色字体+背景高亮
 * - 备注列 inline 编辑
 * - 金额千分位格式化
 * - 超100行启用虚拟滚动
 * - 底部填充策略选择 + 确认按钮
 * - truncated 时顶部黄色警告提示
 *
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9
 */
import { computed } from 'vue'
import type { ExtractedVoucher, ExtractStats, FillMode } from '../composables/useCutoffAutoSampling'

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  visible: boolean
  vouchers: ExtractedVoucher[]
  stats: ExtractStats | null
  fillMode: FillMode
  selectedCount: number
  cutoffErrorCount: number
  selectedDebitTotal: number
  selectedCreditTotal: number
}

const props = defineProps<Props>()

// ─── Emits ────────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'update:fill-mode', v: FillMode): void
  (e: 'confirm'): void
  (e: 'toggle-select-all', v: boolean): void
}>()

// ─── Computed ─────────────────────────────────────────────────────────────────

const dialogVisible = computed({
  get: () => props.visible,
  set: (v: boolean) => emit('update:visible', v),
})

const totalCount = computed(() => props.stats?.totalCount ?? props.vouchers.length)

const isTruncated = computed(() => props.stats?.truncated ?? false)

/** 超过100行启用虚拟滚动（设置固定高度） */
const tableHeight = computed(() => {
  return props.vouchers.length > 100 ? 500 : undefined
})

// ─── Methods ──────────────────────────────────────────────────────────────────

function handleSelectionChange(selection: ExtractedVoucher[]) {
  // 通过对比全选/全不选来通知父组件
  const selectedNos = new Set(selection.map(v => v.voucherNo))
  props.vouchers.forEach(v => {
    v.selected = selectedNos.has(v.voucherNo)
  })
}

function handleSelectAll(selection: ExtractedVoucher[]) {
  const allSelected = selection.length === props.vouchers.length
  emit('toggle-select-all', allSelected)
}

function getRowClassName({ row }: { row: ExtractedVoucher }): string {
  if (row.cutoffStatus === '可能跨期') {
    return 'cutoff-error-row'
  }
  return ''
}

/**
 * 金额格式化：千分位显示
 * - null/undefined → "-"
 * - "0" / "0.00" → "-"
 * - 其他 → 千分位格式
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
function formatStatAmount(value: number): string {
  if (value === 0) return '0.00'
  return value.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function handleConfirm() {
  emit('confirm')
}

function handleFillModeChange(val: FillMode) {
  emit('update:fill-mode', val)
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="提取结果预览"
    width="80vw"
    :destroy-on-close="false"
    :close-on-click-modal="false"
    class="cutoff-preview-dialog"
  >
    <!-- 截断警告提示 -->
    <el-alert
      v-if="isTruncated"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
    >
      <template #title>
        查询结果已截断：共匹配 {{ totalCount }} 笔凭证，当前仅显示前 {{ vouchers.length }} 笔。建议缩小条件范围以获取完整结果。
      </template>
    </el-alert>

    <!-- 统计信息卡片 -->
    <div class="stats-card">
      <div class="stats-item">
        <span class="stats-label">已勾选/总笔数</span>
        <span class="stats-value">
          <strong>{{ selectedCount }}</strong> / {{ totalCount }}
        </span>
      </div>
      <div class="stats-divider" />
      <div class="stats-item">
        <span class="stats-label">跨期笔数</span>
        <span class="stats-value stats-error">
          <strong>{{ cutoffErrorCount }}</strong>
        </span>
      </div>
      <div class="stats-divider" />
      <div class="stats-item">
        <span class="stats-label">借方合计</span>
        <span class="stats-value">{{ formatStatAmount(selectedDebitTotal) }}</span>
      </div>
      <div class="stats-divider" />
      <div class="stats-item">
        <span class="stats-label">贷方合计</span>
        <span class="stats-value">{{ formatStatAmount(selectedCreditTotal) }}</span>
      </div>
    </div>

    <!-- 凭证表格 -->
    <el-table
      :data="vouchers"
      :height="tableHeight"
      :row-class-name="getRowClassName"
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
      <el-table-column prop="voucherDate" label="凭证日期" min-width="100" show-overflow-tooltip />

      <!-- 摘要 -->
      <el-table-column prop="summary" label="摘要" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.summary || '-' }}
        </template>
      </el-table-column>

      <!-- 借方金额 -->
      <el-table-column label="借方金额" min-width="110" align="right">
        <template #default="{ row }">
          {{ formatAmount(row.debitAmount) }}
        </template>
      </el-table-column>

      <!-- 贷方金额 -->
      <el-table-column label="贷方金额" min-width="110" align="right">
        <template #default="{ row }">
          {{ formatAmount(row.creditAmount) }}
        </template>
      </el-table-column>

      <!-- 科目编码 -->
      <el-table-column prop="accountCode" label="科目编码" min-width="100" show-overflow-tooltip />

      <!-- 科目名称 -->
      <el-table-column prop="accountName" label="科目名称" min-width="110" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.accountName || '-' }}
        </template>
      </el-table-column>

      <!-- 对方科目 -->
      <el-table-column prop="counterpartAccount" label="对方科目" min-width="100" show-overflow-tooltip>
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

      <!-- 跨期判定 -->
      <el-table-column label="跨期判定" width="90" align="center">
        <template #default="{ row }">
          <span :class="{ 'cutoff-error-text': row.cutoffStatus === '可能跨期' }">
            {{ row.cutoffStatus }}
          </span>
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
    </el-table>

    <!-- 底部操作区 -->
    <div class="dialog-footer">
      <div class="fill-mode-section">
        <span class="fill-mode-label">填充策略：</span>
        <el-radio-group :model-value="fillMode" @change="handleFillModeChange">
          <el-radio value="append">追加</el-radio>
          <el-radio value="replace">替换</el-radio>
          <el-radio value="merge">合并去重</el-radio>
        </el-radio-group>
      </div>
      <el-button type="primary" @click="handleConfirm">
        确认填充
      </el-button>
    </div>
  </el-dialog>
</template>

<style scoped>
.cutoff-preview-dialog :deep(.el-dialog__body) {
  max-height: 80vh;
  overflow-y: auto;
  padding: 16px 20px;
}

/* 统计信息卡片 */
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

.stats-error {
  color: #f56c6c;
}

.stats-error strong {
  color: #f56c6c;
}

.stats-divider {
  width: 1px;
  height: 32px;
  background: #dcdfe6;
  margin: 0 8px;
}

/* 表格样式 */
.voucher-table {
  font-size: var(--wp-font-size, 13px);
}

.voucher-table :deep(.el-table__row) {
  font-size: var(--wp-font-size, 13px);
}

.voucher-table :deep(.el-table__header th) {
  font-size: var(--wp-font-size, 13px);
}

/* 跨期行高亮 */
.voucher-table :deep(.cutoff-error-row) {
  background-color: #fef0f0 !important;
}

.voucher-table :deep(.cutoff-error-row td) {
  color: #f56c6c;
}

.voucher-table :deep(.cutoff-error-row:hover > td) {
  background-color: #fde2e2 !important;
}

/* 跨期判定文字 */
.cutoff-error-text {
  color: #f56c6c;
  font-weight: 600;
}

/* 底部操作区 */
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

/* 备注输入框优化 */
.voucher-table :deep(.el-input__inner) {
  font-size: var(--wp-font-size, 13px);
}
</style>
