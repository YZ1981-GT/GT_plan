<template>
  <div class="n2-tab-adjustment">
    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>调整分录汇总 N2-3</span>
      </div>
      <div class="section-actions">
        <el-button
          size="small"
          type="primary"
          :disabled="isReadonly || !currentBalance.isBalanced"
          @click="handleSaveAndPublish"
        >
          保存并发布
        </el-button>
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>调整分录规则：</strong>
        AJE（审计调整分录）/RJE（重分类调整分录）需分别保持借贷平衡（∑借方 === ∑贷方）。
        不平衡时无法保存。保存后自动同步至 N2-1 审定表的 AJE/RJE 列，并通知 A13 审计调整汇总。
      </div>
    </div>

    <!-- ═══ AJE / RJE Tab切换 ═══ -->
    <div class="type-switch-bar">
      <el-segmented v-model="activeType" :options="typeOptions" />
    </div>

    <!-- ═══ 借贷平衡状态 ═══ -->
    <div class="balance-status" :class="balanceStatusClass">
      <div class="balance-row">
        <span class="balance-label">借方合计：</span>
        <span class="balance-value">{{ fmtAmount(currentBalance.totalDebit) }}</span>
      </div>
      <div class="balance-row">
        <span class="balance-label">贷方合计：</span>
        <span class="balance-value">{{ fmtAmount(currentBalance.totalCredit) }}</span>
      </div>
      <div class="balance-row balance-diff">
        <span class="balance-label">差额：</span>
        <span class="balance-value">{{ fmtAmount(currentBalance.diff) }}</span>
        <el-tag v-if="currentBalance.isBalanced" type="success" size="small" effect="plain">
          ✓ 借贷平衡
        </el-tag>
        <el-tag v-else type="danger" size="small" effect="plain">
          ✗ 借贷不平衡，禁止提交
        </el-tag>
      </div>
    </div>

    <!-- ═══ 调整分录表格 ═══ -->
    <el-table
      :data="filteredEntries"
      border
      size="small"
      style="width: 100%"
      empty-text="暂无调整分录，点击下方按钮新增"
    >
      <el-table-column label="序号" width="55" align="center">
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>
      <el-table-column label="类型" width="75" align="center">
        <template #default="{ row }">
          <el-tag :type="row.type === 'AJE' ? 'primary' : 'warning'" size="small">
            {{ row.type }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="摘要" min-width="180">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input :model-value="row.description" size="small" placeholder="输入摘要"
              @input="(val: string) => handleFieldChange($index, 'description', val)" />
          </template>
          <span v-else>{{ row.description || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目编码" width="105">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input :model-value="row.accountCode" size="small" placeholder="编码"
              @input="(val: string) => handleFieldChange($index, 'accountCode', val)" />
          </template>
          <span v-else>{{ row.accountCode || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" width="135">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input :model-value="row.accountName" size="small" placeholder="科目名称"
              @input="(val: string) => handleFieldChange($index, 'accountName', val)" />
          </template>
          <span v-else>{{ row.accountName || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方金额" width="125" align="right">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input-number :model-value="row.debitAmount" :controls="false" :min="0" size="small"
              style="width:100%"
              @change="(val: number | undefined) => handleFieldChange($index, 'debitAmount', val ?? 0)" />
          </template>
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方金额" width="125" align="right">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input-number :model-value="row.creditAmount" :controls="false" :min="0" size="small"
              style="width:100%"
              @change="(val: number | undefined) => handleFieldChange($index, 'creditAmount', val ?? 0)" />
          </template>
          <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="65" align="center">
        <template #default="{ $index }">
          <el-button text type="danger" size="small" @click="handleRemoveEntry($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 新增分录按钮 ═══ -->
    <div v-if="!isReadonly" class="add-entry-bar">
      <el-button size="small" @click="handleAddEntry">+ 新增{{ activeType }}分录</el-button>
    </div>

    <!-- ═══ AJE/RJE 净影响 ═══ -->
    <div class="net-impact-section">
      <div class="net-impact-row">
        <span class="net-impact-label">AJE 净影响（科目2221应交税费）：</span>
        <span class="net-impact-value">{{ fmtAmount(ajeNetAmount) }}</span>
      </div>
      <div class="net-impact-row">
        <span class="net-impact-label">RJE 净影响（科目2221应交税费）：</span>
        <span class="net-impact-value">{{ fmtAmount(rjeNetAmount) }}</span>
      </div>
      <div class="net-impact-hint">
        * 净影响自动同步至 N2-1 审定表对应 AJE/RJE 列
      </div>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>借贷平衡</strong>：每笔调整分录必须保持借方合计 = 贷方合计，差额≤0.01元视为平衡</li>
        <li><strong>AJE</strong>：审计调整分录，影响审定数（改变报表金额）</li>
        <li><strong>RJE</strong>：重分类调整分录，不改变损益合计，仅调整列报位置</li>
        <li><strong>负债类特点</strong>：贷方增加（计提增加应交税费），借方减少（缴纳减少应交税费）</li>
        <li><strong>净影响</strong>：仅统计科目编码为"2221"的分录行的净增减（贷方-借方）</li>
        <li><strong>A13联动</strong>：保存并发布后通知 A13 审计调整汇总底稿更新</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabAdjustment — N2-3 调整分录汇总
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 4.4
 * Requirements: 10.3
 *
 * 核心职责：
 * - AJE/RJE 分类分录动态行
 * - 借贷平衡校验（∑借方===∑贷方，不平衡禁止提交）
 * - EventBus publish 'adjustment:created' 通知 A13
 * - 双向同步 N2-1 审定表（AJE/RJE 净影响回写）
 * - 跟随 L3TabAdjustment / M5TabAdjustment 标准 AJE/RJE 表格模式
 *
 * 科目：2221 应交税费（贷方/负债类！）
 */
import { ref, computed, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
import { useN2FormData } from '../../composables/useN2FormData'
import { eventBus } from '@/utils/eventBus'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((section: string) => void) | undefined>(
  'openReviewDialog',
  undefined,
)

// ─── FormData ────────────────────────────────────────────────────────────────

const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)

const formData = useN2FormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

// ─── Types ───────────────────────────────────────────────────────────────────

type AdjustmentType = 'AJE' | 'RJE'

interface AdjustmentEntry {
  id: string
  type: AdjustmentType
  description: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
}

interface BalanceState {
  totalDebit: number
  totalCredit: number
  diff: number
  isBalanced: boolean
}

// ─── State ───────────────────────────────────────────────────────────────────

const activeType = ref<AdjustmentType>('AJE')
const entries = ref<AdjustmentEntry[]>([])
const isReadonly = computed(() => props.isReadonly ?? false)

// 从 allResponses 恢复
;(function restoreEntries() {
  const resp = props.allResponses.get('N2-3-entries')
  if (resp?.conclusion) {
    try {
      entries.value = JSON.parse(resp.conclusion)
    } catch { /* 空 */ }
  }
})()

// ─── Tab选项 ─────────────────────────────────────────────────────────────────

const typeOptions = [
  { label: 'AJE 审计调整', value: 'AJE' },
  { label: 'RJE 重分类调整', value: 'RJE' },
]

// ─── Filtered entries ────────────────────────────────────────────────────────

const filteredEntries = computed(() =>
  entries.value.filter(e => e.type === activeType.value),
)

// ─── 借贷平衡 ────────────────────────────────────────────────────────────────

const currentBalance = computed<BalanceState>(() => {
  const items = filteredEntries.value
  const totalDebit = items.reduce((s, e) => s + (e.debitAmount || 0), 0)
  const totalCredit = items.reduce((s, e) => s + (e.creditAmount || 0), 0)
  const diff = Math.abs(totalDebit - totalCredit)
  return {
    totalDebit,
    totalCredit,
    diff,
    isBalanced: diff <= 0.01,
  }
})

const balanceStatusClass = computed(() => ({
  'balance-ok': currentBalance.value.isBalanced,
  'balance-error': !currentBalance.value.isBalanced,
}))

// ─── 净影响计算（科目2221行的净增减） ────────────────────────────────────────

const ajeNetAmount = computed(() => {
  const ajeItems = entries.value.filter(e => e.type === 'AJE' && e.accountCode === '2221')
  return ajeItems.reduce((s, e) => s + (e.creditAmount || 0) - (e.debitAmount || 0), 0)
})

const rjeNetAmount = computed(() => {
  const rjeItems = entries.value.filter(e => e.type === 'RJE' && e.accountCode === '2221')
  return rjeItems.reduce((s, e) => s + (e.creditAmount || 0) - (e.debitAmount || 0), 0)
})

// ─── 新增分录 ────────────────────────────────────────────────────────────────

function handleAddEntry() {
  entries.value.push({
    id: `adj-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    type: activeType.value,
    description: '',
    accountCode: '',
    accountName: '',
    debitAmount: 0,
    creditAmount: 0,
  })
}

// ─── 删除分录 ────────────────────────────────────────────────────────────────

async function handleRemoveEntry(filteredIndex: number) {
  const entry = filteredEntries.value[filteredIndex]
  if (!entry) return
  const realIndex = entries.value.findIndex(e => e.id === entry.id)
  if (realIndex === -1) return

  try {
    await ElMessageBox.confirm(
      `确定删除第 ${filteredIndex + 1} 行分录？`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    entries.value.splice(realIndex, 1)
  } catch {
    // 用户取消
  }
}

// ─── 字段更新 ────────────────────────────────────────────────────────────────

function handleFieldChange(filteredIndex: number, field: string, value: string | number) {
  const entry = filteredEntries.value[filteredIndex]
  if (!entry) return
  const realIndex = entries.value.findIndex(e => e.id === entry.id)
  if (realIndex === -1) return
  ;(entries.value[realIndex] as any)[field] = value
}

// ─── 保存并发布 ──────────────────────────────────────────────────────────────

async function handleSaveAndPublish() {
  if (!currentBalance.value.isBalanced) {
    ElMessage.error('借贷不平衡，无法提交')
    return
  }
  // 持久化
  await formData.setField('3', 'entries', entries.value)
  // 回写 AJE/RJE 净影响到 N2-1
  await formData.setField('1', 'aje-net', ajeNetAmount.value)
  await formData.setField('1', 'rje-net', rjeNetAmount.value)
  // EventBus 通知 A13
  eventBus.emit('adjustment:created' as any, {
    wpCode: 'N2',
    accountCode: '2221',
    ajeAmount: ajeNetAmount.value,
    rjeAmount: rjeNetAmount.value,
    timestamp: Date.now(),
  })
  ElMessage.success('调整分录已保存并发布')
}

// ─── AI辅助 / 复核 ──────────────────────────────────────────────────────────

function handleAiAssist() {
  ElMessage.info('AI辅助分析调整分录...')
}

function handleReview() {
  if (openReviewDialog) {
    openReviewDialog('N2-3-调整分录')
  } else {
    ElMessage.info('复核对话未配置')
  }
}

// ─── 格式化金额 ──────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.n2-tab-adjustment {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── Header ─── */
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
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 方法论上下文 ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── 类型切换 ─── */
.type-switch-bar {
  margin-bottom: 14px;
}

/* ─── 平衡状态 ─── */
.balance-status {
  padding: 10px 14px;
  border-radius: 6px;
  margin-bottom: 14px;
  display: flex;
  gap: 24px;
  align-items: center;
  flex-wrap: wrap;
}

.balance-status.balance-ok {
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
}

.balance-status.balance-error {
  background: #fef0f0;
  border: 1px solid #fde2e2;
}

.balance-row {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--wp-font-size, 13px);
}

.balance-label {
  color: #606266;
}

.balance-value {
  font-weight: 600;
  color: #303133;
}

.balance-diff {
  gap: 8px;
}

/* ─── 新增按钮 ─── */
.add-entry-bar {
  margin-top: 12px;
  text-align: center;
}

/* ─── 净影响 ─── */
.net-impact-section {
  margin-top: 16px;
  padding: 10px 14px;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}

.net-impact-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
  line-height: 2;
}

.net-impact-label {
  color: #606266;
}

.net-impact-value {
  font-weight: 600;
  color: #303133;
}

.net-impact-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
}

/* ─── 表格 ─── */
:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

/* ─── 编制提示 ─── */
.n2-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.n2-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n2-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
