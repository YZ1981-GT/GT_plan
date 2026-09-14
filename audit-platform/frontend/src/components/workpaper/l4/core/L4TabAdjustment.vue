<template>
  <div class="l4-tab-adjustment">
    <!-- ═══ 标题 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L4-4 调整分录汇总</h3>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" plain :loading="centralSyncing" :disabled="isReadonly || !currentBalance.isBalanced || filteredEntries.length === 0" @click="syncToCentral" title="把本页调整分录汇聚到集中调整登记，供合伙人跨循环审阅">同步到集中登记</el-button>
        <el-tag v-if="centralStatus?.review_status" size="small" :type="centralStatus.review_status==='approved'?'success':(centralStatus.review_status==='rejected'?'danger':'info')" :title="centralStatus.rejection_reason||''">集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status]||centralStatus.review_status }}</el-tag>
        <el-button size="small" type="success" :disabled="isReadonly || !currentBalance.isBalanced" @click="handleSavePublish">
          保存并发布
        </el-button>
        <el-button size="small" @click="handleAI('adjustment')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>调整分录（AJE/RJE）：</strong>
        借贷必须平衡（∑借方 = ∑贷方）。保存后自动发布EventBus通知A13审计调整汇总，
        并双向同步L4-1审定表的AJE/RJE列。科目2502应付债券为贷方增加/借方减少。
      </div>
    </div>

    <!-- ═══ AJE/RJE Tab切换 ═══ -->
    <el-segmented v-model="activeType" :options="typeOptions" size="default" class="type-switcher" />

    <!-- ═══ 借贷平衡指示器 ═══ -->
    <div class="balance-indicator" :class="currentBalance.isBalanced ? 'balanced' : 'unbalanced'">
      <span>借方合计：<strong>{{ fmtAmount(currentBalance.totalDebit) }}</strong></span>
      <span>贷方合计：<strong>{{ fmtAmount(currentBalance.totalCredit) }}</strong></span>
      <span>差额：<strong :class="!currentBalance.isBalanced ? 'text-danger' : ''">{{ fmtAmount(currentBalance.diff) }}</strong></span>
      <el-tag :type="currentBalance.isBalanced ? 'success' : 'danger'" size="small">
        {{ currentBalance.isBalanced ? '✓ 平衡' : '✗ 不平衡' }}
      </el-tag>
    </div>

    <!-- ═══ 调整分录表 ═══ -->
    <el-table
      :data="filteredEntries"
      border
      size="small"
      style="width: 100%"
    >
      <el-table-column prop="index" label="序号" width="60" align="center" />

      <el-table-column label="摘要" min-width="200">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.description" size="small" placeholder="调整事项摘要" @change="(val: string) => handleUpdate($index, 'description', val)" />
          <span v-else>{{ row.description || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目编码" min-width="100">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.accountCode" size="small" placeholder="如2502" @change="(val: string) => handleUpdate($index, 'accountCode', val)" />
          <span v-else>{{ row.accountCode || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目名称" min-width="140">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.accountName" size="small" @change="(val: string) => handleUpdate($index, 'accountName', val)" />
          <span v-else>{{ row.accountName || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方金额" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'debitAmount', val ?? 0)" />
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方金额" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'creditAmount', val ?? 0)" />
          <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ $index }">
          <el-button type="danger" text size="small" @click="handleRemove($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 新增按钮 ═══ -->
    <div class="add-row-bar" v-if="!isReadonly">
      <el-button size="small" @click="handleAdd">
        <el-icon><Plus /></el-icon> 新增分录行
      </el-button>
    </div>

    <!-- ═══ 科目2502净影响 ═══ -->
    <div class="net-impact-section">
      <span>AJE对2502净影响（贷-借）：<strong>{{ fmtAmount(ajeNetAmount) }}</strong></span>
      <span>RJE对2502净影响（贷-借）：<strong>{{ fmtAmount(rjeNetAmount) }}</strong></span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>调整分录必须借贷平衡后才能保存发布</li>
        <li>科目2502为负债类贷方：贷方增加负债（发行/计提），借方减少负债（兑付/偿还）</li>
        <li>发布后自动同步L4-1审定表并通知A13审计调整汇总</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L4TabAdjustment — L4-4 调整分录汇总
 *
 * Requirements: 8.1
 * - 借贷平衡校验
 * - EventBus publish 'adjustment:created'
 * - 双向同步L4-1
 */
import { computed, inject, onMounted, watch, toRef, type Ref } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { useL4FormData } from '../../composables/useL4FormData'
import { useL4Adjustment, type L4AdjustmentEntry, type L4AdjustmentType } from '../../composables/useL4Adjustment'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '@/components/workpaper/composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

const formData = useL4FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const {
  activeType,
  filteredEntries,
  currentBalance,
  ajeNetAmount,
  rjeNetAmount,
  addEntry,
  removeEntry,
  updateEntry,
  switchType,
  saveAndPublish,
} = useL4Adjustment(formData)

// ─── 同步到集中调整登记 ───────────────────────────────────────────────────────

const { year: auditYear } = useAuditContext()
const {
  centralStatus,
  syncing: centralSyncing,
  syncToCentral,
  refreshStatus,
} = useAdjustmentCentralSync({
  projectId: toRef(props, 'projectId') as Ref<string>,
  year: auditYear,
  wpId: toRef(props, 'wpId') as Ref<string>,
  wpCode: 'L4',
  itemId: () => `L4-adj-${activeType.value}`,
  buildLineItems: () =>
    filteredEntries.value.map((e: any) => ({
      standard_account_code: e.accountCode || undefined,
      account_name: e.accountName,
      debit_amount: e.debitAmount,
      credit_amount: e.creditAmount,
    })),
  buildMeta: () => ({
    description:
      filteredEntries.value.find((e: any) => e.description)?.description ||
      `L4 应付债券调整（${activeType.value}）`,
    adjustmentType: activeType.value === 'RJE' ? 'rje' : 'aje',
  }),
})
watch(activeType, () => refreshStatus())

const typeOptions = [
  { label: 'AJE 审计调整', value: 'AJE' },
  { label: 'RJE 重分类调整', value: 'RJE' },
]

function handleAdd() { addEntry() }
function handleRemove(index: number) { removeEntry(index) }
function handleUpdate(index: number, field: keyof L4AdjustmentEntry, value: string | number) {
  updateEntry(index, field, value)
}
function handleSavePublish() { saveAndPublish() }

function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `l4-adjustment-${section}`,
      prompt: `请基于应付债券调整分录"${section}"数据，给出审计建议`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleReview() { openReviewDialog?.() }

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(async () => {
  await formData.loadData()
  refreshStatus()
})
</script>

<style scoped>
.l4-tab-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context {
  border-left: 4px solid #e6a23c; background: #fdf6ec;
  padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px;
}
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }

.type-switcher { margin-bottom: 12px; }

.balance-indicator {
  display: flex; align-items: center; gap: 16px; padding: 8px 16px;
  border-radius: 6px; margin-bottom: 12px; font-size: var(--wp-font-size, 13px);
}
.balance-indicator.balanced { background: #f0f9eb; border: 1px solid #b3e19d; }
.balance-indicator.unbalanced { background: #fef0f0; border: 1px solid #f9a7a7; }

.text-danger { color: #f56c6c; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }

.add-row-bar { margin-top: 8px; }

.net-impact-section {
  display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px;
  background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266;
}

.l4-details-tip {
  margin-top: 16px; padding: 12px 16px; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266;
}
.l4-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l4-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
