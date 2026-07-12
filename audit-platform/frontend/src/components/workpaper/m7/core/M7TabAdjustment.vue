<template>
  <div class="m7-tab-adjustment">
    <!-- ═══ 标题 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3 class="section-title">M7-3 调整分录汇总</h3>
        <el-tag type="success" effect="dark" size="small">科目4201·专项储备</el-tag>
      </div>
      <div class="section-header-right">
        <el-segmented
          v-model="activeType"
          :options="typeOptions"
          size="small"
          @change="handleTypeSwitch"
        />
        <el-button size="small" @click="handleAI('adjustment')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>专项储备调整分录（4201 贷方/权益类）：</strong>
        调增专项储备 → 贷方增加（贷记4201）；调减专项储备 → 借方减少（借记4201）。
        典型场景：补提安全生产费（借:成本/费用 贷:专项储备）、冲回多计提、资本化支出调整。
        借贷必须平衡后方可保存发布。保存后通知M7-1审定表刷新AJE/RJE列。
      </div>
    </div>

    <!-- ═══ 借贷平衡状态 ═══ -->
    <div class="balance-status" :class="{ balanced: currentBalance.isBalanced, unbalanced: !currentBalance.isBalanced }">
      <span>借方合计: {{ fmtAmount(currentBalance.totalDebit) }}</span>
      <span>贷方合计: {{ fmtAmount(currentBalance.totalCredit) }}</span>
      <el-tag :type="currentBalance.isBalanced ? 'success' : 'danger'" size="small" effect="dark">
        {{ currentBalance.isBalanced ? '已平衡' : `差额: ${fmtAmount(currentBalance.diff)}` }}
      </el-tag>
    </div>

    <!-- ═══ 分录表格 ═══ -->
    <el-table :data="filteredEntries" border size="small" style="width: 100%">
      <el-table-column type="index" label="序号" width="60" align="center" />
      <el-table-column prop="description" label="调整事项说明" min-width="180">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model="row.description" size="small" placeholder="说明" @change="handleUpdate($index, 'description', row.description)" />
          <span v-else>{{ row.description || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="类别" width="110">
        <template #default="{ row, $index }">
          <el-select v-if="!isReadonly" v-model="row.category" size="small" placeholder="选择" @change="handleUpdate($index, 'category', row.category)">
            <el-option label="报表调整" value="报表调整" />
            <el-option label="账项调整" value="账项调整" />
            <el-option label="重分类" value="重分类" />
            <el-option label="其他" value="其他" />
          </el-select>
          <span v-else>{{ row.category || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="accountName" label="科目名称" width="150">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model="row.accountName" size="small" placeholder="科目" @change="handleUpdate($index, 'accountName', row.accountName)" />
          <span v-else>{{ row.accountName || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="debitAmount" label="借方金额" width="130" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'debitAmount', val ?? 0)" />
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="creditAmount" label="贷方金额" width="130" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'creditAmount', val ?? 0)" />
          <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="refIndex" label="索引" width="90">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model="row.refIndex" size="small" @change="handleUpdate($index, 'refIndex', row.refIndex)" />
          <span v-else>{{ row.refIndex || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="60" align="center">
        <template #default="{ $index }">
          <el-button type="danger" size="small" link @click="handleRemove($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 操作按钮 ═══ -->
    <div class="action-bar">
      <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleAddEntry">+ 新增分录</el-button>
      <el-button
        v-if="!isReadonly"
        type="primary"
        size="small"
        :disabled="!currentBalance.isBalanced"
        :loading="isSaving"
        @click="handleSaveAndPublish"
      >
        保存并发布
      </el-button>
      <span v-if="!currentBalance.isBalanced" class="balance-warning">借贷不平衡，无法发布</span>
    </div>

    <!-- ═══ 4201净影响 ═══ -->
    <div class="net-impact">
      <el-tag type="info" size="small" effect="plain">
        AJE对4201净影响: {{ fmtAmount(ajeNet4201) }}（{{ ajeNet4201 >= 0 ? '净增' : '净减' }}）
      </el-tag>
      <el-tag type="info" size="small" effect="plain">
        RJE对4201净影响: {{ fmtAmount(rjeNet4201) }}（{{ rjeNet4201 >= 0 ? '净增' : '净减' }}）
      </el-tag>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>专项储备（4201）为<strong>权益类贷方科目</strong></li>
        <li>调增=贷方增加（贷记4201）；调减=借方减少（借记4201）</li>
        <li>补提安全生产费：借:生产成本/管理费用 贷:专项储备</li>
        <li>冲回多计提：借:专项储备 贷:生产成本/管理费用</li>
        <li>资本化支出调整：借:专项储备 贷:累计折旧—专项储备折旧</li>
        <li>借贷平衡后才能保存发布，保存后通知M7-1审定表刷新AJE/RJE列</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M7TabAdjustment.vue — M7-3 调整分录汇总（借贷平衡 + EventBus publish）
 *
 * Spec: .kiro/specs/m7-special-reserve/
 * Task: 6.1
 * Requirements: 6.1
 *
 * EventBus集成：
 * - saveAndPublish() → publish 'adjustment:created' (借贷平衡后)
 * - subscribe 'substantive:adjudicated' → 双向同步M7-1审定表
 * - 组件卸载时 off 清理
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useM7FormData } from '../../composables/useM7FormData'
import { useM7Adjustment, type M7AdjustmentType } from '../../composables/useM7Adjustment'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()

// ─── Inject复核对话 ──────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Composables ─────────────────────────────────────────────────────────────
const formData = useM7FormData({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
const {
  entries,
  activeType,
  filteredEntries,
  ajeBalance,
  rjeBalance,
  currentBalance,
  ajeNet4201,
  rjeNet4201,
  addEntry,
  removeEntry,
  updateEntry,
  switchType,
  saveAndPublish,
  subscribeAdjudicated,
} = useM7Adjustment(formData)

// ─── State ───────────────────────────────────────────────────────────────────
const isSaving = ref(false)
const typeOptions = [
  { label: 'AJE 审计调整', value: 'AJE' },
  { label: 'RJE 重分类', value: 'RJE' },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────
function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 行操作 ──────────────────────────────────────────────────────────────────
function handleAddEntry(): void {
  addEntry()
}

function handleRemove(index: number): void {
  // 找到 filteredEntries 中的对应项在 entries 中的真实索引
  const entry = filteredEntries.value[index]
  if (!entry) return
  const realIndex = entries.value.indexOf(entry)
  if (realIndex >= 0) removeEntry(realIndex)
}

function handleUpdate(filteredIndex: number, field: string, value: string | number): void {
  const entry = filteredEntries.value[filteredIndex]
  if (!entry) return
  const realIndex = entries.value.indexOf(entry)
  if (realIndex >= 0) updateEntry(realIndex, field as any, value)
}

function handleTypeSwitch(val: any): void {
  switchType(val as M7AdjustmentType)
}

// ─── 保存并发布 ──────────────────────────────────────────────────────────────
async function handleSaveAndPublish(): Promise<void> {
  isSaving.value = true
  try {
    await saveAndPublish()
  } finally {
    isSaving.value = false
  }
}

// ─── UI handlers ─────────────────────────────────────────────────────────────
function handleAI(_section: string): void { /* AI辅助钩子 */ }
function handleReview(): void { openReviewDialog?.('M7-3-adjustment', '调整分录') }

// ─── EventBus: subscribe 'substantive:adjudicated' → 双向同步 ────────────────
let unsubAdjudicated: (() => void) | null = null

onMounted(async () => {
  await formData.loadData()

  // 恢复分录行数据
  _restoreEntries()

  // EventBus双向同步：订阅M7-1审定事件
  unsubAdjudicated = subscribeAdjudicated((_payload: any) => {
    // M7-1审定数变化时，可做UI刷新提示等
  })
})

onUnmounted(() => {
  if (unsubAdjudicated) { unsubAdjudicated(); unsubAdjudicated = null }
})

// ─── 恢复分录数据 ───────────────────────────────────────────────────────────
function _restoreEntries(): void {
  for (const [key, resp] of formData.allResponses.value.entries()) {
    if (key.startsWith('M7-3-entry-') && key.endsWith('-data') && resp.remark) {
      try {
        const d = JSON.parse(resp.remark)
        entries.value.push({
          index: d.index || entries.value.length + 1,
          description: d.description || '',
          category: d.category || '',
          reportItem: d.reportItem || '',
          accountName: d.accountName || '',
          noteItem: d.noteItem || '',
          type: d.type || 'AJE',
          debitAmount: Number(d.debitAmount) || 0,
          creditAmount: Number(d.creditAmount) || 0,
          refIndex: d.refIndex || '',
          remark: d.remark || '',
        })
      } catch { /* skip corrupt */ }
    }
  }
}
</script>

<style scoped>
.m7-tab-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }

.balance-status {
  display: flex; align-items: center; gap: 16px;
  padding: 8px 16px; border-radius: 6px; margin-bottom: 12px;
}
.balance-status.balanced { background: #f0f9eb; }
.balance-status.unbalanced { background: #fef0f0; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }

.action-bar { display: flex; align-items: center; gap: 12px; margin-top: 12px; }
.balance-warning { color: #f56c6c; font-size: 12px; }

.net-impact { display: flex; gap: 12px; margin-top: 12px; flex-wrap: wrap; }

.m7-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.m7-details-tip summary { cursor: pointer; font-weight: 600; color: #303133; }
.m7-details-tip ul { margin: 8px 0 0; padding-left: 20px; }
.m7-details-tip li { margin-bottom: 4px; line-height: 1.5; }
</style>
