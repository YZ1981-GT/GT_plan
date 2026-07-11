<template>
  <div class="l6-tab-adjustment">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L6-3 调整分录</h3>
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
        涉及科目2601专项应付款（贷方/负债类）。
        借贷必须平衡（∑借方 = ∑贷方）。保存后通过EventBus双向同步L6-1审定表和通知A13。
      </div>
    </div>

    <!-- ═══ AJE/RJE 切换 ═══ -->
    <el-segmented v-model="activeType" :options="typeOptions" size="default" class="type-switcher" />

    <!-- ═══ 分录表 ═══ -->
    <el-table :data="filteredEntries" border size="small" style="width: 100%">
      <el-table-column type="index" label="#" width="50" align="center" />
      <el-table-column label="调整事项说明" min-width="160">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.description" size="small" placeholder="调整事项说明" @change="(val: string) => handleUpdateEntry($index, 'description', val)" />
          <span v-else>{{ row.description || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类别" min-width="120">
        <template #default="{ row, $index }">
          <el-select v-if="!isReadonly" :model-value="row.category" size="small" placeholder="选择" @change="(val: string) => handleUpdateEntry($index, 'category', val)">
            <el-option label="报表调整" value="报表调整" />
            <el-option label="账项调整" value="账项调整" />
            <el-option label="其他" value="其他" />
          </el-select>
          <span v-else>{{ row.category || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="报表项目" min-width="120">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.reportItem" size="small" placeholder="报表项目" @change="(val: string) => handleUpdateEntry($index, 'reportItem', val)" />
          <span v-else>{{ row.reportItem || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" min-width="130">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.accountName" size="small" placeholder="科目名称" @change="(val: string) => handleUpdateEntry($index, 'accountName', val)" />
          <span v-else>{{ row.accountName || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="附注项目" min-width="110">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.noteItem" size="small" placeholder="附注项目" @change="(val: string) => handleUpdateEntry($index, 'noteItem', val)" />
          <span v-else>{{ row.noteItem || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方金额" min-width="130" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateEntry($index, 'debitAmount', val ?? 0)" />
          <span v-else>{{ row.debitAmount ? fmtAmount(row.debitAmount) : '' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方金额" min-width="130" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateEntry($index, 'creditAmount', val ?? 0)" />
          <span v-else>{{ row.creditAmount ? fmtAmount(row.creditAmount) : '' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" min-width="80">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" placeholder="索引" @change="(val: string) => handleUpdateEntry($index, 'indexRef', val)" />
          <span v-else>{{ row.indexRef || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="120">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" placeholder="备注" @change="(val: string) => handleUpdateEntry($index, 'remark', val)" />
          <span v-else>{{ row.remark || '—' }}</span>
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
    <div class="impact-area" v-if="filteredEntries.length > 0">
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="AJE对专项应付款(2601)净影响">{{ fmtAmount(ajeNet2601) }}</el-descriptions-item>
        <el-descriptions-item label="RJE对专项应付款(2601)净影响">{{ fmtAmount(rjeNet2601) }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>借贷必须平衡（∑借方 = ∑贷方）才能保存发布</li>
        <li>发布后自动同步L6-1审定表AJE/RJE列</li>
        <li>通知A13审计调整汇总</li>
        <li>涉及科目：2601专项应付款（贷方/负债类）</li>
        <li>类别：报表调整 / 账项调整 / 其他</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L6TabAdjustment — L6-3 调整分录（借贷平衡）
 * Requirements: 5.1
 *
 * 功能：
 * - AJE/RJE 切换（el-segmented）
 * - 分录行：调整事项说明 | 类别(dropdown) | 报表项目 | 科目名称 | 附注项目 | 借方金额 | 贷方金额 | 索引 | 备注
 * - 借贷平衡校验：Σ借方 vs Σ贷方, 差额显示, 不平衡时红色警告
 * - 保存+发布 EventBus 'adjustment:created'（only when balanced）
 * - 动态行：新增/删除
 * - Uses: useL6Adjustment + useL6FormData
 */
import { computed, inject, onMounted } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { useL6FormData } from '../../composables/useL6FormData'
import { useL6Adjustment, type L6AdjustmentEntry } from '../../composables/useL6Adjustment'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

// ─── FormData + Composable ──────────────────────────────────────────────────

const formData = useL6FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const {
  entries,
  activeType,
  filteredEntries,
  ajeBalance,
  rjeBalance,
  currentBalance,
  ajeNet2601,
  rjeNet2601,
  addEntry,
  removeEntry,
  updateEntry,
  switchType,
  saveAndPublish,
} = useL6Adjustment(formData)

const typeOptions = [
  { label: 'AJE 审计调整', value: 'AJE' },
  { label: 'RJE 重分类', value: 'RJE' },
]

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAddEntry() { addEntry() }
function handleRemoveEntry(index: number) { removeEntry(index) }
function handleUpdateEntry(index: number, field: keyof L6AdjustmentEntry, value: string | number) {
  updateEntry(index, field, value)
}
async function handleSaveAndPublish() { await saveAndPublish() }
function handleAI(_section: string) {}
function handleReview() { openReviewDialog?.() }

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(async () => {
  await formData.loadData()
})
</script>

<style scoped>
.l6-tab-adjustment { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
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
.l6-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.l6-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l6-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
