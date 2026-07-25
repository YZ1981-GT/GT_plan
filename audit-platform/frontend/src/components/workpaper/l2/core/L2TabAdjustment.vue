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
        <el-button size="small" type="primary" plain :loading="centralSyncing" :disabled="isReadonly || !currentBalanceCheck.isBalanced || currentEntries.length === 0" @click="syncToCentral" title="把本页调整分录汇聚到集中调整登记，供合伙人跨循环审阅">同步到集中登记</el-button>
        <el-tag v-if="centralStatus?.review_status" size="small" :type="centralStatus.review_status==='approved'?'success':(centralStatus.review_status==='rejected'?'danger':'info')" :title="centralStatus.rejection_reason||''">集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status]||centralStatus.review_status }}</el-tag>
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
        <el-table-column label="序号" width="52" align="center">
          <template #default="{ row }">
            {{ row.seqNo }}
          </template>
        </el-table-column>

        <!-- 调整事项说明 -->
        <el-table-column label="调整事项说明" min-width="160">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input
                :model-value="row.description"
                size="small"
                placeholder="调整事项..."
                @input="(val: string) => updateEntry(row.entryId, 'description', val)"
              />
            </template>
            <span v-else>{{ row.description || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 类别 -->
        <el-table-column label="类别" width="110">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.category"
              size="small"
              style="width: 100%"
              @change="(val: string) => updateEntry(row.entryId, 'category', val)"
            >
              <el-option v-for="opt in ADJ_CATEGORY_OPTIONS" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <span v-else>{{ row.category || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 报表项目 -->
        <el-table-column label="报表项目" min-width="120">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input
                :model-value="row.reportItem"
                size="small"
                placeholder="报表项目"
                @input="(val: string) => updateEntry(row.entryId, 'reportItem', val)"
              />
            </template>
            <span v-else>{{ row.reportItem || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 科目名称 -->
        <el-table-column label="科目名称" min-width="130">
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

        <!-- 附注项目 -->
        <el-table-column label="附注项目" min-width="120">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input
                :model-value="row.noteItem"
                size="small"
                placeholder="附注项目"
                @input="(val: string) => updateEntry(row.entryId, 'noteItem', val)"
              />
            </template>
            <span v-else>{{ row.noteItem || '-' }}</span>
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

        <!-- 索引 -->
        <el-table-column label="索引" min-width="100">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input
                :model-value="row.indexRef"
                size="small"
                placeholder="索引号"
                @input="(val: string) => updateEntry(row.entryId, 'indexRef', val)"
              />
            </template>
            <span v-else>{{ row.indexRef || '-' }}</span>
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

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="note-card-header">
          <span class="note-card-title">1、审计说明</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="warning"
            plain
            :loading="aiNoteLoading"
            @click="handleAiNote"
          >
            🤖 AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :readonly="isReadonly"
        placeholder="概述：程序测试情况/结果；拟调整事项及调整分录、未调整事项及其影响..."
        @input="(v: string) => updateNote('note', v)"
      />
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="note-card-header">
          <span class="note-card-title">2、审计结论</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="warning"
            plain
            :loading="aiConclusionLoading"
            @click="handleAiConclusion"
          >
            🤖 AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :readonly="isReadonly"
        placeholder="根据本表调整分录情况，形成审计结论..."
        @input="(v: string) => updateNote('conclusion', v)"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>调整事项/类别</strong>：填调整事项说明，类别选报表调整/账项调整/其他</li>
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
import { computed, ref, inject, toRef, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useL2FormData } from '../../composables/useL2FormData'
import { useL2Adjustment } from '../../composables/useL2Adjustment'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '@/components/workpaper/composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'

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
  auditNote,
  auditConclusion,
  updateNote,
  addEntry,
  removeEntry,
  updateEntry,
  submitAdjustment,
  ADJ_CATEGORY_OPTIONS,
} = useL2Adjustment({
  allResponses,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  saveField,
  debouncedSave,
})

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
  wpCode: 'L2',
  itemId: () => `L2-adj-${activeEntryType.value}`,
  buildLineItems: () =>
    currentEntries.value.map((e: any) => ({
      account_name: e.accountName,
      report_line_code: e.reportItem || undefined,
      debit_amount: e.debitAmount,
      credit_amount: e.creditAmount,
    })),
  buildMeta: () => ({
    description:
      currentEntries.value.find((e: any) => e.description)?.description ||
      `L2 应付利息调整（${activeEntryType.value}）`,
    adjustmentType: activeEntryType.value === 'RJE' ? 'rje' : 'aje',
  }),
})
watch(activeEntryType, () => refreshStatus())
refreshStatus()

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

// ─── AI辅助（审计说明/结论，context 值全部转字符串避 422） ────────────────────

const aiNoteLoading = ref(false)
const aiConclusionLoading = ref(false)

function buildAiContext(): Record<string, string> {
  const aje = entries.value.filter(e => e.entryType === 'AJE')
  const rje = entries.value.filter(e => e.entryType === 'RJE')
  return {
    调整分录笔数: String(entries.value.length),
    AJE笔数: String(aje.length),
    RJE笔数: String(rje.length),
    借贷平衡: currentBalanceCheck.value.isBalanced ? '平衡' : '不平衡',
    借方合计: String(currentBalanceCheck.value.totalDebit),
    贷方合计: String(currentBalanceCheck.value.totalCredit),
  }
}

async function generateAi(section: string, prompt: string, existing: string): Promise<string> {
  const res = await (await import('@/utils/http')).default.post(
    `/api/workpapers/${props.wpId}/ai/generate-text`,
    { section, prompt, context: buildAiContext(), existingContent: existing },
  )
  const content = res.data?.data?.content || res.data?.content
  if (content) {
    ElMessage.success('AI建议已生成')
    return content
  }
  ElMessage.info('AI辅助暂不可用')
  return ''
}

async function handleAiNote(): Promise<void> {
  aiNoteLoading.value = true
  try {
    const content = await generateAi(
      'l2-adjustment-note',
      '请根据应付利息调整分录情况，撰写审计说明（程序测试情况/结果、拟调整及未调整事项及其影响）',
      auditNote.value,
    )
    if (content) updateNote('note', content)
  } catch {
    ElMessage.info('AI辅助暂不可用')
  } finally {
    aiNoteLoading.value = false
  }
}

async function handleAiConclusion(): Promise<void> {
  aiConclusionLoading.value = true
  try {
    const content = await generateAi(
      'l2-adjustment-conclusion',
      '请根据应付利息调整分录情况，撰写审计结论',
      auditConclusion.value,
    )
    if (content) updateNote('conclusion', content)
  } catch {
    ElMessage.info('AI辅助暂不可用')
  } finally {
    aiConclusionLoading.value = false
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

/* ─── 审计说明/结论卡片 ─── */
.note-card {
  margin-bottom: 16px;
}

.note-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.note-card-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
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
