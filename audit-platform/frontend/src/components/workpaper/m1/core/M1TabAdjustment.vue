<template>
  <div class="m1-tab-adjustment">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M1-3 调整分录汇总</h3>
        <el-tag :type="currentBalance.isBalanced ? 'success' : 'danger'" size="small">
          {{ currentBalance.isBalanced ? '借贷平衡 ✓' : '借贷不平衡' }}
        </el-tag>
      </div>
      <div class="section-header-right">
        <CycleImportExportDropdown
          :wp-id="props.wpId"
          api-prefix="m1"
          sheet="M1-3"
          :disabled="isReadonly"
          @imported="handleImported"
        />
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
        <el-button size="small" type="primary" plain :loading="centralSyncing" :disabled="isReadonly || !currentBalance.isBalanced || filteredEntries.length === 0" @click="syncToCentral" title="把当前类型调整分录汇聚到集中调整登记，供合伙人跨循环审阅">同步到集中登记</el-button>
        <el-tag v-if="centralStatus?.review_status" size="small" :type="centralStatus.review_status==='approved'?'success':(centralStatus.review_status==='rejected'?'danger':'info')" :title="centralStatus.rejection_reason||''">集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status]||centralStatus.review_status }}</el-tag>
        <el-button size="small" :loading="aiLoading === 'adjustment'" :disabled="isReadonly" @click="handleAI('adjustment')">
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
        涉及科目2232应付股利（贷方/负债类）。宣告分配在贷方增加，实际支付在借方减少。
        借贷必须平衡（∑借方 = ∑贷方）。保存后通过EventBus双向同步M1-1审定表和通知A13。
      </div>
    </div>

    <!-- ═══ AJE/RJE 切换 ═══ -->
    <el-segmented v-model="activeType" :options="typeOptions" size="default" class="type-switcher" />

    <!-- ═══ 分录表格 ═══ -->
    <el-table :data="filteredEntries" border size="small" style="width: 100%">
      <el-table-column type="index" label="#" width="50" align="center" />
      <el-table-column label="调整事项说明" min-width="160">
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
      <el-table-column label="报表项目" min-width="120">
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
      <el-table-column label="科目名称" min-width="120">
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
      <el-table-column label="附注项目" min-width="100">
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
      <el-table-column label="索引" min-width="80">
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
      <el-table-column label="备注" min-width="120">
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
        <el-descriptions-item label="AJE对应付股利(2232)净影响">{{ fmtAmount(ajeNet2232) }}</el-descriptions-item>
        <el-descriptions-item label="RJE对应付股利(2232)净影响">{{ fmtAmount(rjeNet2232) }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>借贷必须平衡（∑借方 = ∑贷方）才能保存发布</li>
        <li>发布后自动同步M1-1审定表AJE/RJE列</li>
        <li>通知A13审计调整汇总</li>
        <li>涉及科目：2232应付股利（贷方/负债类）</li>
        <li>宣告分配在贷方增加，实际支付在借方减少</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M1TabAdjustment — M1-3 调整分录汇总（借贷平衡+EventBus双向同步M1-1）
 *
 * Spec: .kiro/specs/m1-dividends-payable/
 * Task: 4.6
 * Requirements: 6.3
 *
 * 功能：
 * - AJE/RJE tab切换 (el-segmented)
 * - 调整分录行表格：调整事项说明/类别/报表项目/科目名称/附注项目/借方金额/贷方金额/索引/备注
 * - 借贷平衡校验indicator（红=不平衡/绿=平衡）
 * - "保存并发布" button (triggers EventBus 'adjustment:created')
 * - 双向同步M1-1审定表
 * - Uses useM1Adjustment composable
 */
import { computed, inject, onMounted, ref, toRef, watch, type Ref } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useM1FormData } from '../../composables/useM1FormData'
import { useM1Adjustment, type M1AdjustmentEntry } from '../../composables/useM1Adjustment'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '@/components/workpaper/composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── FormData + Composable ──────────────────────────────────────────────────

const formData = useM1FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const {
  activeType,
  filteredEntries,
  currentBalance,
  ajeNet2232,
  rjeNet2232,
  addEntry,
  removeEntry,
  updateEntry,
  saveAndPublish,
  loadFromResponses,
} = useM1Adjustment(formData)

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ─────────────────
const { year: auditYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: toRef(props, 'projectId') as Ref<string>,
  year: auditYear,
  wpId: toRef(props, 'wpId') as Ref<string>,
  wpCode: 'M1',
  itemId: () => `M1-adj-${activeType.value}`,
  buildLineItems: () => filteredEntries.value.map(e => ({
    account_name: e.accountName,
    report_line_code: e.reportItem || undefined,
    debit_amount: e.debitAmount,
    credit_amount: e.creditAmount,
  })),
  buildMeta: () => ({
    description: filteredEntries.value.find(e => e.description)?.description || 'M1 调整（' + activeType.value + '）',
    adjustmentType: activeType.value === 'RJE' ? 'rje' : 'aje',
  }),
})
watch(activeType, () => refreshStatus())

const typeOptions = [
  { label: 'AJE 审计调整', value: 'AJE' },
  { label: 'RJE 重分类', value: 'RJE' },
]

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAddEntry() { addEntry() }
function handleRemoveEntry(index: number) { removeEntry(index) }
function handleUpdateEntry(index: number, field: keyof M1AdjustmentEntry, value: string | number) {
  updateEntry(index, field, value)
}
async function handleSaveAndPublish() { await saveAndPublish() }
async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  let text = ''
  try {
    const entriesCtx = filteredEntries.value
      .map(e => `${e.description || '调整'}: ${e.accountName} 借${fmtAmount(e.debitAmount)}/贷${fmtAmount(e.creditAmount)} [${e.category}]`)
      .join('；') || '（暂无调整分录）'
    const context: Record<string, string> = {
      科目: '2232 应付股利 / 调整分录汇总（M1-3）',
      调整类型: activeType.value,
      调整分录: entriesCtx,
      借方合计: fmtAmount(currentBalance.value.totalDebit),
      贷方合计: fmtAmount(currentBalance.value.totalCredit),
      借贷平衡: currentBalance.value.isBalanced ? '平衡' : `不平衡差异${fmtAmount(currentBalance.value.diff)}`,
    }
    text = await generateAiText({ section: `m1-adjustment-${section}`, context })
  } catch {
    ElMessage.warning('AI 生成失败，请稍后重试')
    aiLoading.value = ''
    return
  }
  aiLoading.value = ''
  if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
  // 本表无审计说明文本框，AI 建议以对话框形式呈现供审计师参考
  ElMessageBox.alert(text, 'AI 辅助 — 调整分录分析建议', { confirmButtonText: '知道了' }).catch(() => { /* 用户关闭 */ })
}
function handleReview() { openReviewDialog?.('M1-3-adjustment', '调整分录') }

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Init ────────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  loadFromResponses(formData.allResponses.value)
  refreshStatus()
})

// ─── 导入完成 → 读回宿主（x3-adjustment-entry-import-export 任务 11.1）───

/**
 * 导入 xlsx 成功后重跑本底稿读回路径：M1-3 读回 = useM1Adjustment.loadFromResponses（任务 4.2 新增，per-field 族）。
 *
 * 判据（R6.5 / R6.7）：接口返 200 不算通过，界面必须读得到导入的行，
 * 故这里重载 responses 后**必须**重跑读回，而不是只弹一个成功提示。
 */
async function handleImported(): Promise<void> {
  await formData.loadData()
  loadFromResponses(formData.allResponses.value)
}
</script>

<style scoped>
.m1-tab-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.type-switcher { margin-bottom: 12px; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.balance-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; border-radius: 6px; font-size: var(--wp-font-size, 13px); align-items: center; }
.balance-bar.balanced { background: #f0f9eb; color: #67c23a; }
.balance-bar.unbalanced { background: #fef0f0; color: #f56c6c; }
.diff-warning { font-weight: 600; }
.balanced-text { font-weight: 600; }
.impact-area { margin-top: 12px; }
.m1-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m1-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m1-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
