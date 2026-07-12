<template>
  <div class="l8-tab-adjustment">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L8-3 调整分录</h3>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddEntry">
          <el-icon><Plus /></el-icon> 新增分录
        </el-button>
        <el-button size="small" @click="handleAI('adjustment')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
        <el-button
          type="primary"
          size="small"
          :loading="isSaving"
          :disabled="!currentBalance.isBalanced"
          @click="handleSaveAndPublish"
        >
          保存并提交
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>调整分录规则：</strong>
        AJE（审计调整分录）影响审定数；RJE（重分类调整分录）仅改变列报位置。
        每组分录必须借贷平衡（∑借方 = ∑贷方）。
        保存后通过EventBus通知L8-1审定表刷新AJE/RJE列，同时通知A13审计调整汇总。
      </div>
    </div>

    <!-- ═══ AJE / RJE Tab切换 ═══ -->
    <el-segmented v-model="activeType" :options="typeOptions" size="default" class="type-switcher" />

    <!-- ═══ 借贷平衡状态 ═══ -->
    <div class="balance-status" :class="{ 'balanced': currentBalance.isBalanced, 'unbalanced': !currentBalance.isBalanced }">
      <span>借方合计：<strong>{{ fmtAmount(currentBalance.totalDebit) }}</strong></span>
      <span>贷方合计：<strong>{{ fmtAmount(currentBalance.totalCredit) }}</strong></span>
      <span>差额：<strong :class="{ 'negative-value': currentBalance.diff !== 0 }">{{ fmtAmount(currentBalance.diff) }}</strong></span>
      <el-tag :type="currentBalance.isBalanced ? 'success' : 'danger'" size="small">
        {{ currentBalance.isBalanced ? '✓ 借贷平衡' : '✗ 不平衡' }}
      </el-tag>
    </div>

    <!-- ═══ 分录表 ═══ -->
    <el-table :data="filteredEntries" border size="small" style="width: 100%" highlight-current-row>
      <el-table-column type="index" label="#" width="50" align="center" />

      <el-table-column label="调整事项说明" min-width="180">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.description" size="small" placeholder="说明" @change="(val: string) => handleUpdate($index, 'description', val)" />
          <span v-else>{{ row.description || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="类别" width="120">
        <template #default="{ row, $index }">
          <el-select v-if="!isReadonly" :model-value="row.category" size="small" placeholder="选择" @change="(val: string) => handleUpdate($index, 'category', val)">
            <el-option label="报表调整" value="报表调整" />
            <el-option label="账项调整" value="账项调整" />
            <el-option label="其他" value="其他" />
          </el-select>
          <span v-else>{{ row.category || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目名称" min-width="150">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.accountName" size="small" placeholder="如: 财务费用" @change="(val: string) => handleUpdate($index, 'accountName', val)" />
          <span v-else>{{ row.accountName || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="报表项目" width="130">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.reportItem" size="small" @change="(val: string) => handleUpdate($index, 'reportItem', val)" />
          <span v-else>{{ row.reportItem || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方金额" width="130" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'debitAmount', val ?? 0)" />
          <span v-else class="debit-amount">{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方金额" width="130" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'creditAmount', val ?? 0)" />
          <span v-else class="credit-amount">{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="索引" width="80">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.refIndex" size="small" @change="(val: string) => handleUpdate($index, 'refIndex', val)" />
          <span v-else>{{ row.refIndex || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="备注" min-width="120">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(val: string) => handleUpdate($index, 'remark', val)" />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center" fixed="right">
        <template #default="{ $index }">
          <el-popconfirm title="确认删除？" @confirm="handleRemoveEntry($index)">
            <template #reference>
              <el-button type="danger" text size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 对6603净影响 ═══ -->
    <div class="net-impact-bar">
      <span>{{ activeType }} 对科目6603财务费用净影响：</span>
      <strong :class="{ 'positive-impact': netImpact > 0, 'negative-impact': netImpact < 0 }">
        {{ fmtAmount(netImpact) }}
      </strong>
      <span class="impact-hint">（借方增加费用，贷方减少费用）</span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l8-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>AJE（审计调整）：影响审定数，本期实际调整</li>
        <li>RJE（重分类调整）：不影响利润总额，仅改变列报位置</li>
        <li>每组分录必须借贷平衡才能提交</li>
        <li>提交后自动通知L8-1审定表刷新 + A13审计调整汇总</li>
        <li>费用为借方科目：借方增加费用（费用↑），贷方减少费用（费用↓）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L8TabAdjustment — L8-3 调整分录（AJE/RJE + 借贷平衡校验 + EventBus）
 *
 * Requirements: 7.3
 * - AJE/RJE Tab 切换（el-segmented）
 * - 借贷平衡校验（不平衡禁止提交）
 * - 保存后 EventBus publish 'adjustment:created'
 * - 双向同步L8-1审定表
 */
import { computed, inject, onMounted, ref } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { useL8FormData } from '../../composables/useL8FormData'
import {
  useL8Adjustment,
  type L8AdjustmentType,
  type L8AdjustmentEntry,
} from '../../composables/useL8Adjustment'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── FormData + Composable ───────────────────────────────────────────────────

const formData = useL8FormData({
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
  ajeNet6603,
  rjeNet6603,
  addEntry,
  removeEntry,
  updateEntry,
  switchType,
  saveAndPublish,
} = useL8Adjustment(formData)

// ─── State ───────────────────────────────────────────────────────────────────

const isSaving = ref(false)

// ─── Computed ────────────────────────────────────────────────────────────────

const typeOptions = [
  { label: 'AJE 审计调整', value: 'AJE' },
  { label: 'RJE 重分类调整', value: 'RJE' },
]

const netImpact = computed(() => {
  return activeType.value === 'AJE' ? ajeNet6603.value : rjeNet6603.value
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAddEntry() { addEntry() }

function handleRemoveEntry(index: number) {
  // index 是 filteredEntries 的索引，需转换为 entries 全局索引
  const entry = filteredEntries.value[index]
  if (!entry) return
  const globalIdx = entries.value.indexOf(entry)
  if (globalIdx >= 0) removeEntry(globalIdx)
}

function handleUpdate(index: number, field: keyof L8AdjustmentEntry, value: any) {
  const entry = filteredEntries.value[index]
  if (!entry) return
  const globalIdx = entries.value.indexOf(entry)
  if (globalIdx >= 0) updateEntry(globalIdx, field, value)
}

async function handleSaveAndPublish() {
  isSaving.value = true
  try {
    await saveAndPublish()
  } finally {
    isSaving.value = false
  }
}

function handleAI(_section: string) { /* AI辅助待集成 */ }
function handleReview() { openReviewDialog?.('L8-3-adjustment', '调整分录') }

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreEntries()
})

function _restoreEntries() {
  const data = formData.allResponses.value.get('L8-3-entries-data')
  if (data?.remark) {
    try {
      const parsed = JSON.parse(data.remark)
      if (Array.isArray(parsed)) entries.value = parsed
    } catch { /* keep empty */ }
  }
}
</script>

<style scoped>
.l8-tab-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.type-switcher { margin-bottom: 12px; }
.balance-status { display: flex; align-items: center; gap: 16px; padding: 8px 16px; border-radius: 6px; margin-bottom: 12px; font-size: var(--wp-font-size, 13px); flex-wrap: wrap; }
.balance-status.balanced { background: #f0f9eb; border: 1px solid #e1f3d8; }
.balance-status.unbalanced { background: #fef0f0; border: 1px solid #fde2e2; }
.negative-value { color: #f56c6c; font-weight: 700; }
.debit-amount { color: #409eff; font-weight: 500; }
.credit-amount { color: #67c23a; font-weight: 500; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.net-impact-bar { display: flex; align-items: center; gap: 8px; padding: 10px 16px; margin-top: 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); }
.positive-impact { color: #f56c6c; font-weight: 600; }
.negative-impact { color: #67c23a; font-weight: 600; }
.impact-hint { color: #909399; font-size: 12px; }
.l8-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.l8-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l8-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
