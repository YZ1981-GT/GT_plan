<template>
  <div class="l3-tab-adjustment">
    <!-- ═══ 返回目录 + 标题 ═══ -->
    <div class="adj-header">
      <div class="adj-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">
          ← 返回目录
        </el-button>
        <h3 class="adj-title">L3-3 调整分录汇总</h3>
      </div>
      <div class="adj-header-right">
        <el-button
          v-if="activeType === 'RJE'"
          size="small"
          type="warning"
          :disabled="isReadonly"
          @click="handleGenerateReclass"
        >
          生成一年内到期重分类
        </el-button>
        <el-button
          size="small"
          type="primary"
          :disabled="isReadonly || !currentBalance.isBalanced"
          @click="handleSaveAndPublish"
        >
          保存并发布
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>调整分录规则：</strong>
        AJE（审计调整分录）/RJE（重分类调整分录）需分别保持借贷平衡（∑借方 === ∑贷方）。
        不平衡时无法保存。保存后自动同步至 L3-1 审定表的 AJE/RJE 列，并通知 A13 审计调整汇总。
        <br />
        <strong>重分类RJE：</strong>一年内到期的长期借款需重分类至流动负债（一年内到期的非流动负债），
        点击"生成一年内到期重分类"按钮自动生成：借 长期借款(2501) / 贷 一年内到期的非流动负债(2801)。
      </div>
    </div>

    <!-- ═══ AJE / RJE Tab 切换（el-segmented） ═══ -->
    <div class="type-switch-bar">
      <el-segmented
        :model-value="activeType"
        :options="typeOptions"
        @change="handleTypeSwitch"
      />
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
        <el-tag
          v-if="currentBalance.isBalanced"
          type="success"
          size="small"
          effect="plain"
        >
          ✓ 借贷平衡
        </el-tag>
        <el-tag
          v-else
          type="danger"
          size="small"
          effect="plain"
        >
          ✗ 借贷不平衡，禁止提交
        </el-tag>
      </div>
    </div>

    <!-- ═══ 调整分录动态行表格 ═══ -->
    <el-table
      :data="filteredEntries"
      border
      size="small"
      style="width: 100%"
      empty-text="暂无调整分录，点击下方按钮新增"
    >
      <!-- 序号 -->
      <el-table-column label="序号" width="60" align="center">
        <template #default="{ $index }">
          {{ $index + 1 }}
        </template>
      </el-table-column>

      <!-- 类型 -->
      <el-table-column label="类型" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.type === 'AJE' ? 'primary' : 'warning'" size="small">
            {{ row.type }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 摘要 -->
      <el-table-column label="摘要" min-width="180">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input
              :model-value="row.description"
              size="small"
              placeholder="输入摘要"
              @input="(val: string) => handleFieldChange($index, 'description', val)"
            />
          </template>
          <span v-else>{{ row.description || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 科目编码 -->
      <el-table-column label="科目编码" width="110">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input
              :model-value="row.accountCode"
              size="small"
              placeholder="编码"
              @input="(val: string) => handleFieldChange($index, 'accountCode', val)"
            />
          </template>
          <span v-else>{{ row.accountCode || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 科目名称 -->
      <el-table-column label="科目名称" width="140">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input
              :model-value="row.accountName"
              size="small"
              placeholder="科目名称"
              @input="(val: string) => handleFieldChange($index, 'accountName', val)"
            />
          </template>
          <span v-else>{{ row.accountName || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 借方金额 -->
      <el-table-column label="借方金额" width="130" align="right">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input-number
              :model-value="row.debitAmount"
              :controls="false"
              :min="0"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleFieldChange($index, 'debitAmount', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 贷方金额 -->
      <el-table-column label="贷方金额" width="130" align="right">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input-number
              :model-value="row.creditAmount"
              :controls="false"
              :min="0"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleFieldChange($index, 'creditAmount', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center">
        <template #default="{ $index }">
          <el-button
            text
            type="danger"
            size="small"
            @click="handleRemoveEntry($index)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 新增行按钮 ═══ -->
    <div v-if="!isReadonly" class="add-entry-bar">
      <el-button size="small" @click="handleAddEntry">
        + 新增{{ activeType }}分录
      </el-button>
    </div>

    <!-- ═══ AJE/RJE 净影响回写说明 ═══ -->
    <div class="net-impact-section">
      <div class="net-impact-row">
        <span class="net-impact-label">AJE 净影响（科目2501长期借款）：</span>
        <span class="net-impact-value">{{ fmtAmount(ajeNetAmount) }}</span>
      </div>
      <div class="net-impact-row">
        <span class="net-impact-label">RJE 净影响（科目2501长期借款）：</span>
        <span class="net-impact-value">{{ fmtAmount(rjeNetAmount) }}</span>
      </div>
      <div class="net-impact-hint">
        * 净影响自动同步至 L3-1 审定表对应 AJE/RJE 列
      </div>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>借贷平衡</strong>：每笔调整分录必须保持借方合计 = 贷方合计，差额≤0.01元视为平衡</li>
        <li><strong>AJE</strong>：审计调整分录，影响审定数（改变报表金额）</li>
        <li><strong>RJE</strong>：重分类调整分录，不改变损益合计，仅调整列报位置</li>
        <li><strong>重分类RJE</strong>：一年内到期的长期借款重分类至流动负债——借：长期借款(2501) / 贷：一年内到期的非流动负债(2801)</li>
        <li><strong>净影响</strong>：仅统计科目编码为"2501"的分录行的净增减</li>
        <li><strong>A13联动</strong>：保存并发布后通知 A13 审计调整汇总底稿更新</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L3TabAdjustment — L3-3 调整分录汇总（含重分类RJE）
 *
 * 功能：
 * - AJE/RJE Tab切换（el-segmented）
 * - 调整分录动态行（序号/类型/摘要/科目/借方/贷方）
 * - 借贷平衡校验（∑借方===∑贷方，不平衡时红色警告+禁止提交）
 * - 重分类RJE生成按钮：借 长期借款(2501) / 贷 一年内到期的非流动负债(2801)
 * - EventBus publish 'adjustment:created'
 * - 双向同步 L3-1 审定表（AJE/RJE净影响回写）
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 4.7
 * Requirements: 5.2, 9.1
 */
import { computed, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { useL3FormData } from '@/components/workpaper/composables/useL3FormData'
import { useL3Adjustment, type L3AdjustmentType } from '@/composables/useL3Adjustment'

// ─── Props / Emits ───────────────────────────────────────────────────────────

defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject formData ─────────────────────────────────────────────────────────

const formData = inject<ReturnType<typeof useL3FormData>>('l3FormData')!

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  entries,
  activeType,
  filteredEntries,
  currentBalance,
  ajeNetAmount,
  rjeNetAmount,
  addEntry,
  removeEntry,
  updateEntry,
  switchType,
  generateReclassRJE,
  saveAndPublish,
} = useL3Adjustment(formData)

// ─── Tab 切换选项 ────────────────────────────────────────────────────────────

const typeOptions = [
  { label: 'AJE 审计调整', value: 'AJE' },
  { label: 'RJE 重分类调整', value: 'RJE' },
]

// ─── 平衡状态样式 ────────────────────────────────────────────────────────────

const balanceStatusClass = computed(() => ({
  'balance-ok': currentBalance.value.isBalanced,
  'balance-error': !currentBalance.value.isBalanced,
}))

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function handleTypeSwitch(val: string | number) {
  switchType(val as L3AdjustmentType)
}

function handleFieldChange(index: number, field: string, value: string | number) {
  // 从 filteredEntries 中找到真实 entries 索引
  const entry = filteredEntries.value[index]
  if (!entry) return
  const realIndex = entries.value.findIndex(e => e === entry)
  if (realIndex === -1) return
  updateEntry(realIndex, field as any, value)
}

function handleAddEntry() {
  addEntry()
}

async function handleRemoveEntry(filteredIndex: number) {
  const entry = filteredEntries.value[filteredIndex]
  if (!entry) return
  const realIndex = entries.value.findIndex(e => e === entry)
  if (realIndex === -1) return

  try {
    await ElMessageBox.confirm(
      `确定删除第 ${filteredIndex + 1} 行分录？`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    removeEntry(realIndex)
  } catch {
    // 用户取消
  }
}

async function handleSaveAndPublish() {
  if (!currentBalance.value.isBalanced) {
    ElMessage.error('借贷不平衡，无法提交')
    return
  }
  await saveAndPublish()
  ElMessage.success('调整分录已保存并发布')
}

/**
 * 生成一年内到期重分类RJE
 * 借：长期借款(2501) / 贷：一年内到期的非流动负债(2801)
 */
async function handleGenerateReclass() {
  try {
    const { value: amountStr } = await ElMessageBox.prompt(
      '请输入一年内到期的长期借款金额（元）：',
      '生成一年内到期重分类',
      {
        confirmButtonText: '生成',
        cancelButtonText: '取消',
        inputPattern: /^[0-9]+(\.[0-9]{1,2})?$/,
        inputErrorMessage: '请输入有效金额（最多两位小数）',
        inputPlaceholder: '一年内到期金额',
      },
    )
    const amount = parseFloat(amountStr)
    if (amount <= 0) {
      ElMessage.warning('金额必须大于0')
      return
    }
    generateReclassRJE(amount)
    ElMessage.success(`已生成重分类RJE：借 长期借款 ${fmtAmount(amount)} / 贷 一年内到期的非流动负债 ${fmtAmount(amount)}`)
  } catch {
    // 用户取消
  }
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
.l3-tab-adjustment {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 头部 ─── */
.adj-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.adj-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.adj-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.adj-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
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

/* ─── 类型切换栏 ─── */
.type-switch-bar {
  margin-bottom: 14px;
}

/* ─── 借贷平衡状态区 ─── */
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

/* ─── 新增行按钮 ─── */
.add-entry-bar {
  margin-top: 12px;
  text-align: center;
}

/* ─── 净影响区 ─── */
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

/* ─── 表格统一13px字体 ─── */
:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

/* ─── 编制提示折叠 ─── */
.l3-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l3-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l3-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
