<template>
  <div class="m4-tab-adjustment">
    <!-- ═══ 标题 + AJE/RJE切换 + 按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M4-3 调整分录汇总</h3>
        <el-tag type="success" effect="dark" size="small" class="equity-badge">
          科目4002·贷方增加=调增
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-segmented
          v-model="adjustment.activeType.value"
          :options="typeOptions"
          size="small"
          @change="(val: any) => adjustment.switchType(val)"
        />
        <el-button size="small" :loading="aiLoading === 'adjustment'" @click="handleAI('adjustment')">
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
        <el-button size="small" type="primary" plain :loading="centralSyncing" :disabled="!adjustment.currentBalance.value.isBalanced || adjustment.filteredEntries.value.length === 0" @click="syncToCentral" title="把当前类型调整分录汇聚到集中调整登记，供合伙人跨循环审阅">同步到集中登记</el-button>
        <el-tag v-if="centralStatus?.review_status" size="small" :type="centralStatus.review_status==='approved'?'success':(centralStatus.review_status==='rejected'?'danger':'info')" :title="centralStatus.rejection_reason||''">集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status]||centralStatus.review_status }}</el-tag>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>资本公积（4002）调整分录方向说明：</strong>
        资本公积为权益类贷方科目 —
        <strong>贷方增加 = 调增资本公积</strong>（如确认股份支付、接收外币折算差异），
        <strong>借方减少 = 调减资本公积</strong>（如转增资本、弥补亏损）。
        借贷必须平衡后方可保存发布。保存后自动通知M4-1审定表刷新AJE/RJE列。
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

      <el-table-column label="科目名称" width="150">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.accountName"
            size="small"
            placeholder="如：资本公积"
            @change="(val: string) => handleUpdateEntry($index, 'accountName', val)"
          />
          <span v-else>{{ row.accountName || '—' }}</span>
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

    <!-- ═══ 4002净影响汇总 ═══ -->
    <div class="net-impact-section">
      <el-tag type="info" size="small" effect="plain">
        AJE对4002净影响: {{ fmtAmount(adjustment.ajeNet4002.value) }}（正=调增，负=调减）
      </el-tag>
      <el-tag type="info" size="small" effect="plain">
        RJE对4002净影响: {{ fmtAmount(adjustment.rjeNet4002.value) }}（正=调增，负=调减）
      </el-tag>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>科目4002资本公积：<strong>贷方增加=调增</strong>（确认股份支付/接收M2外币折算差异），<strong>借方减少=调减</strong>（转增资本/弥补亏损）</li>
        <li>借贷必须平衡（Σ借方 === Σ贷方）后方可保存发布</li>
        <li>保存后发布 'adjustment:created' 事件通知M4-1审定表刷新AJE/RJE列</li>
        <li>方向与M3库存股<strong>完全相反</strong>：M3借方增加=调增，M4贷方增加=调增</li>
        <li>AJE = 账项调整分录；RJE = 重分类调整分录</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M4TabAdjustment — M4-3 调整分录汇总（借贷平衡）
 *
 * Spec: .kiro/specs/m4-capital-reserve/
 * Task: 4.5
 * Requirements: 5.3
 *
 * 功能：
 * - AJE/RJE 切换（el-segmented）
 * - 动态分录表（借/贷金额 + 科目 + 报表项目 + 附注）
 * - 借贷平衡校验（Σ借方===Σ贷方）
 * - 平衡状态指示：绿色=平衡, 红色=不平衡+差额
 * - EventBus publish 'adjustment:created' on save
 * - 科目4002 资本公积: 贷方增加=调增, 借方减少=调减
 */
import { computed, inject, onMounted, onUnmounted, ref, toRef, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useM4FormData } from '../../composables/useM4FormData'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import { useM4Adjustment, type M4AdjustmentType } from '../../composables/useM4Adjustment'
import { eventBus } from '@/utils/eventBus'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '@/components/workpaper/composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'

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
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useM4FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Adjustment composable ───────────────────────────────────────────────────

const adjustment = useM4Adjustment(formData)

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ─────────────────
const { year: auditYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: toRef(props, 'projectId') as Ref<string>,
  year: auditYear,
  wpId: toRef(props, 'wpId') as Ref<string>,
  wpCode: 'M4',
  itemId: () => `M4-adj-${adjustment.activeType.value}`,
  buildLineItems: () => adjustment.filteredEntries.value.map(e => ({
    account_name: e.accountName,
    report_line_code: e.reportItem || undefined,
    debit_amount: e.debitAmount,
    credit_amount: e.creditAmount,
  })),
  buildMeta: () => ({
    description: adjustment.filteredEntries.value.find(e => e.description)?.description || 'M4 调整（' + adjustment.activeType.value + '）',
    adjustmentType: adjustment.activeType.value === 'RJE' ? 'rje' : 'aje',
  }),
})
watch(adjustment.activeType, () => refreshStatus())

// ─── el-segmented options ────────────────────────────────────────────────────

const typeOptions = [
  { label: 'AJE 账项调整', value: 'AJE' },
  { label: 'RJE 重分类', value: 'RJE' },
]

// ─── UI State ────────────────────────────────────────────────────────────────

const isSaving = ref(false)

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleUpdateEntry(filteredIndex: number, field: string, value: string | number): void {
  // filteredEntries 里的 index 需要映射到 entries 全量数组
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

async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const context: Record<string, string> = {
      科目: '4002 资本公积（权益类贷方，贷方增加=调增）',
      调整类型: adjustment.activeType.value,
      借方合计: fmtAmount(adjustment.currentBalance.value.totalDebit),
      贷方合计: fmtAmount(adjustment.currentBalance.value.totalCredit),
      借贷平衡: adjustment.currentBalance.value.isBalanced
        ? '平衡'
        : `不平衡，差额 ${fmtAmount(adjustment.currentBalance.value.diff)}`,
      AJE对4002净影响: fmtAmount(adjustment.ajeNet4002.value),
      RJE对4002净影响: fmtAmount(adjustment.rjeNet4002.value),
    }
    // 调整分录为纯表格（无 textarea）→ 建议弹窗
    const text = await generateAiText({ section: `m4-adjustment-${section}`, context })
    if (!text) {
      ElMessage.warning('AI 未生成内容，请稍后重试')
      return
    }
    ElMessageBox.alert(text, 'AI 辅助建议', { confirmButtonText: '知道了' }).catch(() => {})
  } catch {
    ElMessage.warning('AI 生成失败，请稍后重试')
  } finally {
    aiLoading.value = ''
  }
}

function handleReview() {
  openReviewDialog?.('M4-3-adjustment', '调整分录汇总')
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── EventBus: 恢复已保存分录 ───────────────────────────────────────────────

function restoreEntries(): void {
  const prefix = 'M4-3-entry-'
  let maxIdx = 0
  for (const [key] of formData.allResponses.value.entries()) {
    if (key.startsWith(prefix) && key.endsWith('-data')) {
      const match = key.match(/M4-3-entry-(\d+)-data/)
      if (match) {
        const n = parseInt(match[1])
        if (n > maxIdx) maxIdx = n
      }
    }
  }
  if (maxIdx === 0) return

  for (let i = 1; i <= maxIdx; i++) {
    const resp = formData.allResponses.value.get(`${prefix}${i}-data`)
    if (resp?.remark) {
      try {
        const data = JSON.parse(resp.remark)
        adjustment.entries.value.push({
          index: data.index || i,
          description: data.description || '',
          category: data.category || '',
          reportItem: data.reportItem || '',
          accountName: data.accountName || '',
          noteItem: data.noteItem || '',
          type: data.type || 'AJE',
          debitAmount: Number(data.debitAmount) || 0,
          creditAmount: Number(data.creditAmount) || 0,
          refIndex: data.refIndex || '',
          remark: data.remark || '',
        })
      } catch {
        // skip invalid
      }
    }
  }
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  restoreEntries()
  refreshStatus()
})
</script>

<style scoped>
.m4-tab-adjustment {
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

.m4-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.m4-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.m4-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
