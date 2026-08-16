<template>
  <div class="m9-tab-adjustment">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M9-3 其他综合收益调整分录汇总</h3>
        <el-tag :type="currentBalance.isBalanced ? 'success' : 'danger'" size="small">
          {{ currentBalance.isBalanced ? '借贷平衡 ✓' : '借贷不平衡' }}
        </el-tag>
      </div>
      <div class="section-header-right">
        <CycleImportExportDropdown
          :wp-id="props.wpId"
          api-prefix="m9"
          sheet="M9-3"
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
        涉及科目4103其他综合收益（贷方/权益类！）。OCI增加在贷方增加（公允变动/重计量），
        OCI减少/重分类进损益在借方减少。借贷必须平衡（∑借方 = ∑贷方）。
        保存后通过EventBus双向同步M9-1审定表和通知A13。
      </div>
    </div>

    <!-- ═══ AJE/RJE 切换 ═══ -->
    <el-segmented v-model="activeType" :options="typeOptions" size="default" class="type-switcher" />

    <!-- ═══ 分录表格 ═══ -->
    <el-table :data="filteredEntries" border size="small" style="width: 100%">
      <el-table-column type="index" label="序号" width="55" align="center" />
      <el-table-column label="事项说明" min-width="150">
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
            <el-option label="重分类" value="重分类" />
            <el-option label="其他" value="其他" />
          </el-select>
          <span v-else>{{ row.category || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="报表项目" min-width="110">
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
      <el-table-column label="科目" min-width="120">
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
      <el-table-column label="OCI分类" min-width="110">
        <template #default="{ row, $index }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.ociBlock"
            size="small"
            placeholder="OCI分类"
            clearable
            @change="(val: string) => handleUpdateEntry($index, 'ociBlock', val)"
          >
            <el-option label="不可重分类" value="nonReclass" />
            <el-option label="可重分类" value="reclass" />
          </el-select>
          <span v-else>{{ row.ociBlock === 'nonReclass' ? '不可重分类' : row.ociBlock === 'reclass' ? '可重分类' : '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方" min-width="120" align="right">
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
      <el-table-column label="贷方" min-width="120" align="right">
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
      <el-table-column label="索引号" min-width="80">
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
      <el-table-column label="备注" min-width="100">
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
        <el-descriptions-item label="AJE对其他综合收益(4103)净影响">{{ fmtAmount(ajeNet4103) }}</el-descriptions-item>
        <el-descriptions-item label="RJE对其他综合收益(4103)净影响">{{ fmtAmount(rjeNet4103) }}</el-descriptions-item>
        <el-descriptions-item label="AJE不可重分类净影响">{{ fmtAmount(ajeNetByBlock.nonReclass) }}</el-descriptions-item>
        <el-descriptions-item label="AJE可重分类净影响">{{ fmtAmount(ajeNetByBlock.reclass) }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m9-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>借贷必须平衡（∑借方 = ∑贷方）才能保存发布</li>
        <li>发布后自动同步M9-1审定表AJE/RJE列</li>
        <li>通知A13审计调整汇总</li>
        <li>涉及科目：4103其他综合收益（贷方/权益类）</li>
        <li>OCI增加在贷方（公允变动/重计量），OCI减少/重分类进损益在借方</li>
        <li>OCI分类选择：不可重分类（G8公允变动/J2重计量）/ 可重分类（债权/套期/外币折算）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M9TabAdjustment — M9-3 其他综合收益调整分录汇总（借贷平衡+EventBus双向同步M9-1）
 *
 * Spec: .kiro/specs/m9-other-comprehensive-income/
 * Task: 4.5
 * Requirements: 5.1
 *
 * 功能：
 * - AJE/RJE tab切换 (el-segmented)
 * - 调整分录行表格：序号|事项说明|类别|报表项目|科目|OCI分类|借方|贷方|索引号|备注
 * - 借贷平衡状态显示（绿色平衡/红色不平衡）
 * - 新增行+删除行
 * - "保存并发布" button (triggers EventBus 'adjustment:created')
 * - 双向同步M9-1审定表
 * - Uses useM9Adjustment composable
 */
import { computed, inject, onMounted, ref, toRef, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { useM9FormData } from '../../composables/useM9FormData'
import { useM9Adjustment, type M9AdjustmentEntry } from '../../composables/useM9Adjustment'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '@/components/workpaper/composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
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

const formData = useM9FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const {
  activeType,
  filteredEntries,
  currentBalance,
  ajeNet4103,
  rjeNet4103,
  ajeNetByBlock,
  addEntry,
  removeEntry,
  updateEntry,
  saveAndPublish,
  loadFromResponses,
} = useM9Adjustment(formData)

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ─────────────────
const { year: auditYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: toRef(props, 'projectId') as Ref<string>,
  year: auditYear,
  wpId: toRef(props, 'wpId') as Ref<string>,
  wpCode: 'M9',
  itemId: () => `M9-adj-${activeType.value}`,
  buildLineItems: () => filteredEntries.value.map(e => ({
    account_name: e.accountName,
    report_line_code: e.reportItem || undefined,
    debit_amount: e.debitAmount,
    credit_amount: e.creditAmount,
  })),
  buildMeta: () => ({
    description: filteredEntries.value.find(e => e.description)?.description || 'M9 调整（' + activeType.value + '）',
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
function handleUpdateEntry(index: number, field: keyof M9AdjustmentEntry, value: string | number) {
  updateEntry(index, field, value)
}
async function handleSaveAndPublish() { await saveAndPublish() }
async function handleAI(section: string): Promise<void> {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const context: Record<string, string> = {
      科目: '4103 其他综合收益 / 调整分录汇总（M9-3 权益类贷方）',
      当前类型: activeType.value,
      借方合计: fmtAmount(currentBalance.value.totalDebit),
      贷方合计: fmtAmount(currentBalance.value.totalCredit),
      是否平衡: currentBalance.value.isBalanced ? '平衡' : '不平衡',
      'AJE对4103净影响': fmtAmount(ajeNet4103.value),
      'RJE对4103净影响': fmtAmount(rjeNet4103.value),
      'AJE不可重分类净影响': fmtAmount(ajeNetByBlock.value.nonReclass),
      'AJE可重分类净影响': fmtAmount(ajeNetByBlock.value.reclass),
    }
    const text = await generateAiText({ section: `m9-adjustment-${section}`, context, existingContent: '' })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    ElMessageBox.alert(text, 'AI 辅助建议', { confirmButtonText: '知道了' }).catch(() => {})
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}
function handleReview() { openReviewDialog?.('M9-3-adjustment', '调整分录') }

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
 * 导入 xlsx 成功后重跑本底稿读回路径：M9-3 读回 = useM9Adjustment.loadFromResponses（任务 4.2 新增，-data 族）。
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
.m9-tab-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }
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
.m9-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m9-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m9-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
