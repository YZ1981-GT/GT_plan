<template>
  <div class="l7-tab-adjustment">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L7-3 调整分录</h3>
        <el-tag :type="currentBalance.isBalanced ? 'success' : 'danger'" size="small">
          {{ currentBalance.isBalanced ? '借贷平衡 ✓' : '借贷不平衡' }}
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddEntry">
          <el-icon><Plus /></el-icon> 新增分录
        </el-button>
        <el-button
          size="small"
          type="success"
          :disabled="isReadonly || !currentBalance.isBalanced"
          @click="handleSaveAndPublish"
        >
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
        涉及科目2801其他非流动负债（贷方/负债类）。
        借贷必须平衡（∑借方 = ∑贷方）。保存后通过EventBus双向同步L7-1审定表和通知A13。
      </div>
    </div>

    <!-- ═══ AJE/RJE 切换 ═══ -->
    <el-segmented v-model="activeType" :options="typeOptions" size="default" class="type-switcher" />

    <!-- ═══ 分录表 ═══ -->
    <el-table :data="filteredEntries" border size="small" style="width: 100%">
      <el-table-column type="index" label="#" width="50" align="center" />
      <el-table-column label="摘要" min-width="180">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.description"
            size="small"
            placeholder="调整摘要"
            @change="(val: string) => handleUpdateEntry($index, 'description', val)"
          />
          <span v-else>{{ row.description || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类别" min-width="100">
        <template #default="{ row, $index }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.category"
            size="small"
            placeholder="类别"
            @change="(val: string) => handleUpdateEntry($index, 'category', val)"
          >
            <el-option label="报表调整" value="报表调整" />
            <el-option label="账项调整" value="账项调整" />
            <el-option label="其他" value="其他" />
          </el-select>
          <span v-else>{{ row.category || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" min-width="140">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.accountName"
            size="small"
            placeholder="科目名称"
            @change="(val: string) => handleUpdateEntry($index, 'accountName', val)"
          />
          <span v-else>{{ row.accountName || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方金额" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            :controls="false"
            :min="0"
            size="small"
            style="width:100%"
            @change="(val: number | undefined) => handleUpdateEntry($index, 'debitAmount', val ?? 0)"
          />
          <span v-else>{{ row.debitAmount ? fmtAmount(row.debitAmount) : '' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方金额" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            :controls="false"
            :min="0"
            size="small"
            style="width:100%"
            @change="(val: number | undefined) => handleUpdateEntry($index, 'creditAmount', val ?? 0)"
          />
          <span v-else>{{ row.creditAmount ? fmtAmount(row.creditAmount) : '' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center">
        <template #default="{ $index }">
          <el-button type="danger" text size="small" @click="handleRemoveEntry($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 借贷平衡状态 ═══ -->
    <div :class="['balance-bar', currentBalance.isBalanced ? 'balanced' : 'unbalanced']">
      <span>借方合计：<strong>{{ fmtAmount(currentBalance.totalDebit) }}</strong></span>
      <span>贷方合计：<strong>{{ fmtAmount(currentBalance.totalCredit) }}</strong></span>
      <span v-if="!currentBalance.isBalanced" class="diff-warning">
        差额：<strong>{{ fmtAmount(currentBalance.diff) }}</strong>
      </span>
      <span v-else class="balanced-text">✓ 平衡</span>
    </div>

    <!-- ═══ 对科目影响 ═══ -->
    <div v-if="filteredEntries.length > 0" class="impact-area">
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="AJE对其他非流动负债(2801)净影响">{{ fmtAmount(ajeNet2801) }}</el-descriptions-item>
        <el-descriptions-item label="RJE对其他非流动负债(2801)净影响">{{ fmtAmount(rjeNet2801) }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>借贷必须平衡（∑借方 = ∑贷方）才能保存发布</li>
        <li>发布后自动同步L7-1审定表AJE/RJE列</li>
        <li>通知A13审计调整汇总</li>
        <li>涉及科目：2801其他非流动负债（贷方/负债类）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L7TabAdjustment — L7-3 调整分录（借贷平衡+EventBus）
 *
 * Spec: .kiro/specs/l7-other-noncurrent-liabilities/
 * Task: 4.5
 * Requirements: 4.3
 */
import { computed, inject, onMounted } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { useL7FormData } from '../../../composables/useL7FormData'
import { useL7Adjustment, type L7AdjustmentEntry } from '../../../composables/useL7Adjustment'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)

// ─── FormData + Composable ──────────────────────────────────────────────────

const formData = useL7FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const {
  entries,
  activeType,
  filteredEntries,
  currentBalance,
  ajeNet2801,
  rjeNet2801,
  addEntry,
  removeEntry,
  updateEntry,
  saveAndPublish,
} = useL7Adjustment(formData)

const typeOptions = [
  { label: 'AJE 审计调整', value: 'AJE' },
  { label: 'RJE 重分类', value: 'RJE' },
]

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAddEntry() { addEntry() }
function handleRemoveEntry(index: number) { removeEntry(index) }
function handleUpdateEntry(index: number, field: keyof L7AdjustmentEntry, value: string | number) {
  updateEntry(index, field, value)
}
async function handleSaveAndPublish() { await saveAndPublish() }
function handleAI(_section: string) {}
function handleReview() { openReviewDialog?.('L7-3-adjustment', '调整分录') }

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Init ────────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
})
</script>

<style scoped>
.l7-tab-adjustment { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }
.type-switcher { margin-bottom: 12px; }
:deep(.el-table) { font-size: 13px; }
.balance-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; border-radius: 6px; font-size: 13px; align-items: center; }
.balance-bar.balanced { background: #f0f9eb; color: #67c23a; }
.balance-bar.unbalanced { background: #fef0f0; color: #f56c6c; }
.diff-warning { font-weight: 600; }
.balanced-text { font-weight: 600; }
.impact-area { margin-top: 12px; }
.l7-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.l7-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l7-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
