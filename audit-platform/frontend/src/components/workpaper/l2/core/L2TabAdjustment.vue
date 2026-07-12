<template>
  <div class="l2-tab-adjustment">
    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>调整分录编制规范：</strong>
        审计调整分录(AJE)更正被审计单位报表错报；重分类调整分录(RJE)重新归类列报项目。
        每组分录必须借贷平衡（∑借方 = ∑贷方）方可提交。应付利息科目(2231)为贷方/负债类。
      </div>
    </div>

    <!-- ═══ 标题行 + 复核按钮 ═══ -->
    <div class="section-header">
      <h3 class="section-title">L2-3 应付利息调整分录汇总</h3>
      <div class="section-actions">
        <el-button
          v-if="!isReadonly"
          type="primary"
          text
          size="small"
          @click="handleReview"
        >
          复核
        </el-button>
      </div>
    </div>

    <!-- ═══ AJE/RJE 类型切换 ═══ -->
    <div class="type-toggle">
      <el-segmented
        v-model="activeEntryType"
        :options="entryTypeOptions"
        :disabled="isReadonly"
      />
    </div>

    <!-- ═══ 借贷平衡校验指示器 ═══ -->
    <div class="balance-indicator" :class="balanceIndicatorClass">
      <span class="balance-label">借贷平衡：</span>
      <template v-if="currentBalanceCheck.isBalanced">
        <span class="balance-status balanced">✓ 平衡</span>
      </template>
      <template v-else>
        <span class="balance-status unbalanced">
          ✗ 不平衡（差额 {{ fmtAmount(currentBalanceCheck.diff) }}）
        </span>
      </template>
      <span class="balance-detail">
        借方合计 {{ fmtAmount(currentBalanceCheck.totalDebit) }}
        &nbsp;|&nbsp;
        贷方合计 {{ fmtAmount(currentBalanceCheck.totalCredit) }}
      </span>
    </div>

    <!-- ═══ 分录表格 ═══ -->
    <el-card shadow="never" class="adjustment-table-card">
      <el-table
        :data="currentEntries"
        border
        size="small"
        style="width: 100%"
        empty-text="暂无调整分录"
      >
        <!-- 序号 -->
        <el-table-column label="序号" width="60" align="center">
          <template #default="{ row }">
            {{ row.seqNo }}
          </template>
        </el-table-column>

        <!-- 科目编码 -->
        <el-table-column label="科目编码" min-width="110">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input
                :model-value="row.accountCode"
                size="small"
                placeholder="如2231"
                @input="(val: string) => updateEntry(row.entryId, 'accountCode', val)"
              />
            </template>
            <span v-else>{{ row.accountCode || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 科目名称 -->
        <el-table-column label="科目名称" min-width="140">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input
                :model-value="row.accountName"
                size="small"
                placeholder="应付利息"
                @input="(val: string) => updateEntry(row.entryId, 'accountName', val)"
              />
            </template>
            <span v-else>{{ row.accountName || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 借方 -->
        <el-table-column label="借方" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input-number
                :model-value="row.debitAmount"
                :controls="false"
                :min="0"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateEntry(row.entryId, 'debitAmount', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 贷方 -->
        <el-table-column label="贷方" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input-number
                :model-value="row.creditAmount"
                :controls="false"
                :min="0"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateEntry(row.entryId, 'creditAmount', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 摘要 -->
        <el-table-column label="摘要" min-width="180">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input
                :model-value="row.description"
                size="small"
                placeholder="调整摘要..."
                @input="(val: string) => updateEntry(row.entryId, 'description', val)"
              />
            </template>
            <span v-else>{{ row.description || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="操作" width="70" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              type="danger"
              text
              size="small"
              @click="handleRemoveEntry(row.entryId)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 操作按钮行 ═══ -->
    <div class="adjustment-actions">
      <el-button
        v-if="!isReadonly"
        type="primary"
        plain
        size="small"
        @click="handleAddEntry"
      >
        + 新增分录
      </el-button>
      <el-button
        v-if="!isReadonly"
        type="success"
        :disabled="!currentBalanceCheck.isBalanced || currentEntries.length === 0"
        :loading="isSubmitting"
        @click="handleSubmit"
      >
        提交调整
      </el-button>
      <span v-if="!currentBalanceCheck.isBalanced && currentEntries.length > 0" class="balance-warn-hint">
        借贷不平衡，无法提交
      </span>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>AJE</strong>：审计调整分录，更正被审计单位财务报表中识别的错报</li>
        <li><strong>RJE</strong>：重分类调整分录，不改变利润总额只影响报表列报</li>
        <li><strong>借贷平衡</strong>：每组分录∑借方 = ∑贷方，差额≤0.01元视为平衡</li>
        <li><strong>科目2231</strong>：应付利息（负债类贷方），贷方增加/借方减少</li>
        <li><strong>联动</strong>：提交后自动通知L2-1审定表累计AJE/RJE调整额</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L2TabAdjustment — L2-3 应付利息调整分录汇总
 *
 * 功能：
 * - AJE/RJE 类型切换（el-segmented）
 * - 分录表格：序号/科目编码/科目名称/借方/贷方/摘要
 * - 借贷平衡校验指示器
 * - Add entry + delete row
 * - Balance validation before submit
 * - EventBus publish 'adjustment:created'
 * - Uses useL2Adjustment composable
 * - inject openReviewDialog
 *
 * Spec: .kiro/specs/l2-interest-payable/
 * Task: 4.5
 * Requirements: 5.3
 *
 * 科目：2231 应付利息（贷方/负债类）
 */
import { computed, ref, inject, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useL2FormData } from '../../composables/useL2FormData'
import { useL2Adjustment } from '../../composables/useL2Adjustment'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── Inject openReviewDialog ─────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>(
  'openReviewDialog',
  () => {},
)

// ─── Composable: useL2FormData ───────────────────────────────────────────────

const {
  allResponses,
  isLoading,
  loadData,
  saveField,
  debouncedSave,
} = useL2FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

// 加载数据
loadData()

// ─── Composable: useL2Adjustment ─────────────────────────────────────────────

const {
  entries,
  currentEntries,
  activeEntryType,
  currentBalanceCheck,
  addEntry,
  removeEntry,
  updateEntry,
  submitAdjustment,
} = useL2Adjustment({
  allResponses,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  saveField,
  debouncedSave,
})

// ─── AJE/RJE 选项 ───────────────────────────────────────────────────────────

const entryTypeOptions = [
  { label: 'AJE', value: 'AJE' },
  { label: 'RJE', value: 'RJE' },
]

// ─── 平衡指示器样式 ──────────────────────────────────────────────────────────

const balanceIndicatorClass = computed(() => ({
  'balance-ok': currentBalanceCheck.value.isBalanced,
  'balance-err': !currentBalanceCheck.value.isBalanced && currentEntries.value.length > 0,
}))

// ─── 新增分录 ────────────────────────────────────────────────────────────────

function handleAddEntry(): void {
  addEntry()
}

// ─── 删除分录 ────────────────────────────────────────────────────────────────

function handleRemoveEntry(entryId: string): void {
  removeEntry(entryId)
}

// ─── 提交 ────────────────────────────────────────────────────────────────────

const isSubmitting = ref(false)

async function handleSubmit(): Promise<void> {
  isSubmitting.value = true
  try {
    const success = await submitAdjustment()
    if (success) {
      ElMessage.success('调整分录已提交，已通知审定表')
    }
  } catch {
    ElMessage.error('提交失败，请稍后重试')
  } finally {
    isSubmitting.value = false
  }
}

// ─── 复核 ────────────────────────────────────────────────────────────────────

function handleReview(): void {
  openReviewDialog('L2-3-adjustment', 'L2-3 应付利息调整分录')
}

// ─── 金额格式化 ──────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.l2-tab-adjustment {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── Section标题行 + 复核按钮右对齐 ─── */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── AJE/RJE切换 ─── */
.type-toggle {
  margin-bottom: 14px;
}

/* ─── 借贷平衡指示器 ─── */
.balance-indicator {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 6px;
  margin-bottom: 14px;
  font-size: var(--wp-font-size, 13px);
  border: 1px solid #ebeef5;
  background: #fafafa;
  flex-wrap: wrap;
}

.balance-indicator.balance-ok {
  background: #f0f9eb;
  border-color: #c2e7b0;
}

.balance-indicator.balance-err {
  background: #fef0f0;
  border-color: #fbc4c4;
}

.balance-label {
  color: #606266;
  font-weight: 500;
}

.balance-status.balanced {
  color: #67c23a;
  font-weight: 600;
}

.balance-status.unbalanced {
  color: #f56c6c;
  font-weight: 600;
}

.balance-detail {
  color: #909399;
  font-size: 12px;
  margin-left: auto;
}

/* ─── 分录表格卡片 ─── */
.adjustment-table-card {
  margin-bottom: 14px;
}

:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

/* ─── 操作按钮行 ─── */
.adjustment-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.balance-warn-hint {
  font-size: 12px;
  color: #f56c6c;
}

/* ─── 编制提示折叠 ─── */
.l2-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l2-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l2-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
