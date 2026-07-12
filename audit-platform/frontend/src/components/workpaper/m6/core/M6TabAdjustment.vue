<template>
  <div class="m6-tab-adjustment">
    <!-- ═══ 标题 + AJE/RJE切换 + 按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M6-3 未分配利润调整分录汇总</h3>
        <el-tag type="success" effect="dark" size="small" class="equity-badge">
          科目4104·贷方增加=调增
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-segmented
          v-model="adjustment.activeType.value"
          :options="typeOptions"
          size="small"
          @change="(val: any) => adjustment.switchType(val)"
        />
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
          :disabled="!adjustment.currentBalance.value.isBalanced"
          @click="handleSave"
        >
          保存并发布
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>未分配利润（4104）调整分录方向说明：</strong>
        未分配利润为权益类贷方科目 —
        <strong>贷方增加 = 调增未分配利润</strong>（如前期差错追溯调增净利润），
        <strong>借方减少 = 调减未分配利润</strong>（如补提盈余公积、冲回多计利润）。
        借贷必须平衡后方可保存发布。保存后自动通知M6-1审定表刷新AJE/RJE列。
      </div>
    </div>

    <!-- ═══ 借贷平衡状态指示器 ═══ -->
    <div class="balance-indicator" :class="{ balanced: adjustment.currentBalance.value.isBalanced, unbalanced: !adjustment.currentBalance.value.isBalanced }">
      <div class="balance-amounts">
        <span class="balance-label">Σ借方:</span>
        <span class="balance-value">{{ fmtAmount(adjustment.currentBalance.value.totalDebit) }}</span>
        <span class="balance-separator">|</span>
        <span class="balance-label">Σ贷方:</span>
        <span class="balance-value">{{ fmtAmount(adjustment.currentBalance.value.totalCredit) }}</span>
      </div>
      <div class="balance-status">
        <el-tag
          :type="adjustment.currentBalance.value.isBalanced ? 'success' : 'danger'"
          size="small"
          effect="dark"
        >
          {{ adjustment.currentBalance.value.isBalanced ? '✓ 借贷平衡' : `✗ 不平衡 差额: ${fmtAmount(adjustment.currentBalance.value.diff)}` }}
        </el-tag>
      </div>
    </div>

    <!-- ═══ 调整分录表格 ═══ -->
    <el-table
      :data="adjustment.filteredEntries.value"
      border
      size="small"
      style="width: 100%"
      :empty-text="`暂无${adjustment.activeType.value}调整分录`"
    >
      <el-table-column type="index" label="序号" width="60" align="center" />

      <el-table-column label="调整事项说明" min-width="180">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.description"
            size="small"
            placeholder="调整事项说明"
            @change="(val: string) => handleUpdateEntry($index, 'description', val)"
          />
          <span v-else>{{ row.description || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="类别" width="110">
        <template #default="{ row, $index }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.category"
            size="small"
            placeholder="类别"
            clearable
            @change="(val: string) => handleUpdateEntry($index, 'category', val)"
          >
            <el-option label="报表调整" value="报表调整" />
            <el-option label="账项调整" value="账项调整" />
            <el-option label="重分类" value="重分类" />
            <el-option label="前期差错" value="前期差错" />
            <el-option label="其他" value="其他" />
          </el-select>
          <span v-else>{{ row.category || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="报表项目" width="130">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.reportItem"
            size="small"
            placeholder="报表项目"
            @change="(val: string) => handleUpdateEntry($index, 'reportItem', val)"
          />
          <span v-else>{{ row.reportItem || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目" width="150">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.accountName"
            size="small"
            placeholder="如：未分配利润"
            @change="(val: string) => handleUpdateEntry($index, 'accountName', val)"
          />
          <span v-else>{{ row.accountName || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="附注项目" width="120">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.noteItem"
            size="small"
            placeholder="附注项目"
            @change="(val: string) => handleUpdateEntry($index, 'noteItem', val)"
          />
          <span v-else>{{ row.noteItem || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方金额" width="130" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            :controls="false"
            size="small"
            :min="0"
            style="width: 100%"
            @change="(val: number | undefined) => handleUpdateEntry($index, 'debitAmount', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方金额" width="130" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            :controls="false"
            size="small"
            :min="0"
            style="width: 100%"
            @change="(val: number | undefined) => handleUpdateEntry($index, 'creditAmount', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="索引号" width="100">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.refIndex"
            size="small"
            placeholder="索引"
            @change="(val: string) => handleUpdateEntry($index, 'refIndex', val)"
          />
          <span v-else>{{ row.refIndex || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="备注" width="120">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            placeholder="备注"
            @change="(val: string) => handleUpdateEntry($index, 'remark', val)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="" width="60" align="center" fixed="right">
        <template #default="{ $index }">
          <el-button type="danger" size="small" link @click="handleRemoveEntry($index)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 新增按钮 ═══ -->
    <div v-if="!isReadonly" class="add-row-bar">
      <el-button size="small" type="primary" plain @click="handleAddEntry">
        + 新增{{ adjustment.activeType.value }}分录
      </el-button>
    </div>

    <!-- ═══ 4104净影响汇总 ═══ -->
    <div class="net-impact-section">
      <el-tag type="info" size="small" effect="plain">
        AJE对4104净影响: {{ fmtAmount(adjustment.ajeNet4104.value) }}（正=调增未分配利润，负=调减）
      </el-tag>
      <el-tag type="info" size="small" effect="plain">
        RJE对4104净影响: {{ fmtAmount(adjustment.rjeNet4104.value) }}（正=调增未分配利润，负=调减）
      </el-tag>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>科目4104利润分配-未分配利润：<strong>贷方增加=调增</strong>（前期差错追溯调增净利润），<strong>借方减少=调减</strong>（补提盈余公积/冲回多计利润）</li>
        <li>借贷必须平衡（Σ借方 === Σ贷方）后方可保存发布</li>
        <li>保存后发布 'adjustment:created' 事件通知M6-1审定表刷新AJE/RJE列</li>
        <li>补提盈余公积：借:利润分配-未分配利润 贷:盈余公积</li>
        <li>前期差错追溯：借:利润分配-未分配利润 贷:以前年度损益调整（或相关科目）</li>
        <li>AJE = 账项调整分录；RJE = 重分类调整分录</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M6TabAdjustment — M6-3 未分配利润调整分录汇总（借贷平衡）
 *
 * Spec: .kiro/specs/m6-retained-earnings/
 * Task: 4.5
 * Requirements: 5.3
 *
 * 功能：
 * - AJE/RJE 切换（el-segmented）
 * - 动态分录表（序号|调整事项说明|类别|报表项目|科目|附注项目|借方|贷方|索引号|备注）
 * - 借贷平衡校验（Σ借方===Σ贷方）
 * - 平衡状态指示：绿色=平衡, 红色=不平衡+差额
 * - EventBus publish 'adjustment:created' on save
 * - 双向同步M6-1审定表
 * - 科目4104 未分配利润: 贷方增加=调增, 借方减少=调减
 * - inject openReviewDialog
 */
import { computed, inject, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useM6FormData } from '../../composables/useM6FormData'
import { useM6Adjustment } from '../../composables/useM6Adjustment'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
  (e: 'save'): void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useM6FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Adjustment composable ───────────────────────────────────────────────────

const adjustment = useM6Adjustment(formData)

// ─── el-segmented options ────────────────────────────────────────────────────

const typeOptions = [
  { label: 'AJE 审计调整', value: 'AJE' },
  { label: 'RJE 重分类', value: 'RJE' },
]

// ─── UI State ────────────────────────────────────────────────────────────────

const isSaving = ref(false)

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleUpdateEntry(filteredIndex: number, field: string, value: string | number): void {
  const entry = adjustment.filteredEntries.value[filteredIndex]
  if (!entry) return
  const rawIndex = adjustment.entries.value.indexOf(entry)
  if (rawIndex < 0) return
  adjustment.updateEntry(rawIndex, field as any, value)
}

function handleRemoveEntry(filteredIndex: number): void {
  const entry = adjustment.filteredEntries.value[filteredIndex]
  if (!entry) return
  const rawIndex = adjustment.entries.value.indexOf(entry)
  if (rawIndex < 0) return
  adjustment.removeEntry(rawIndex)
}

function handleAddEntry(): void {
  adjustment.addEntry()
}

async function handleSave(): Promise<void> {
  if (!adjustment.currentBalance.value.isBalanced) {
    ElMessage.warning('借贷不平衡，无法保存')
    return
  }
  isSaving.value = true
  try {
    await adjustment.saveAndPublish()
    ElMessage.success('调整分录已保存并发布')
    emit('save')
  } finally {
    isSaving.value = false
  }
}

function handleAI(_section: string) {
  // AI辅助钩子（后续集成）
}

function handleReview() {
  openReviewDialog?.('M6-3-adjustment', '未分配利润调整分录汇总')
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 恢复已保存分录 ─────────────────────────────────────────────────────────

function restoreEntries(): void {
  adjustment.loadFromResponses(formData.allResponses.value)
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  restoreEntries()
})
</script>

<style scoped>
.m6-tab-adjustment {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.section-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.equity-badge {
  font-weight: 600;
}

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}

.methodology-text {
  font-size: var(--wp-font-size, 13px);
  color: #6b5900;
  line-height: 1.6;
}

.balance-indicator {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-radius: 6px;
  margin-bottom: 12px;
  transition: all 0.3s;
}

.balance-indicator.balanced {
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
}

.balance-indicator.unbalanced {
  background: #fef0f0;
  border: 1px solid #fde2e2;
}

.balance-amounts {
  display: flex;
  align-items: center;
  gap: 8px;
}

.balance-label {
  font-weight: 500;
  color: #606266;
}

.balance-value {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.balance-separator {
  color: #c0c4cc;
  margin: 0 4px;
}

.balance-status {
  display: flex;
  align-items: center;
}

:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

.add-row-bar {
  margin-top: 12px;
  margin-bottom: 16px;
}

.net-impact-section {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.m6-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.m6-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.m6-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
