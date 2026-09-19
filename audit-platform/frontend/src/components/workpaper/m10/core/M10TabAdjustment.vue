<template>
  <div class="m10-tab-adjustment">
    <!-- ═══ 标题 + AJE/RJE切换 + 按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M10-3 其他权益工具调整分录汇总</h3>
        <el-tag type="success" effect="dark" size="small" class="equity-badge">
          科目4003·贷方增加=调增
        </el-tag>
      </div>
      <div class="section-header-right">
        <CycleImportExportDropdown
          :wp-id="props.wpId"
          api-prefix="m10"
          sheet="M10-3"
          :disabled="isReadonly"
          @imported="handleImported"
        />
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
        <el-button size="small" type="primary" plain :loading="centralSyncing" :disabled="!adjustment.currentBalance.value.isBalanced || adjustment.filteredEntries.value.length === 0" @click="syncToCentral" title="把当前类型调整分录汇聚到集中调整登记，供合伙人跨循环审阅">同步到集中登记</el-button>
        <el-tag v-if="centralStatus?.review_status" size="small" :type="centralStatus.review_status==='approved'?'success':(centralStatus.review_status==='rejected'?'danger':'info')" :title="centralStatus.rejection_reason||''">集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status]||centralStatus.review_status }}</el-tag>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>其他权益工具（4003）调整分录方向说明：</strong>
        其他权益工具为权益类贷方科目 —
        <strong>贷方增加 = 调增其他权益工具</strong>（如补确认永续债发行、CAS37重分类负债→权益），
        <strong>借方减少 = 调减其他权益工具</strong>（如补确认赎回、CAS37重分类权益→负债）。
        借贷必须平衡后方可保存发布。保存后自动通知M10-1审定表刷新AJE/RJE列。
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

      <el-table-column label="类别" width="130">
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
            <el-option label="CAS37重分类" value="CAS37重分类" />
            <el-option label="其他" value="其他" />
          </el-select>
          <span v-else>{{ row.category || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目名称" width="150">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.accountName"
            size="small"
            placeholder="如：其他权益工具"
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

    <!-- ═══ 4003净影响汇总 ═══ -->
    <div class="net-impact-section">
      <el-tag type="info" size="small" effect="plain">
        AJE对4003净影响: {{ fmtAmount(adjustment.ajeNet4003.value) }}（正=调增，负=调减）
      </el-tag>
      <el-tag type="info" size="small" effect="plain">
        RJE对4003净影响: {{ fmtAmount(adjustment.rjeNet4003.value) }}（正=调增，负=调减）
      </el-tag>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m10-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>科目4003其他权益工具：<strong>贷方增加=调增</strong>（补确认发行/CAS37负债→权益重分类），<strong>借方减少=调减</strong>（补确认赎回/CAS37权益→负债重分类）</li>
        <li>借贷必须平衡（Σ借方 === Σ贷方）后方可保存发布</li>
        <li>保存后发布 'adjustment:created' 事件通知M10-1审定表刷新AJE/RJE列</li>
        <li>永续债发行：借:银行存款 贷:其他权益工具</li>
        <li>永续债赎回：借:其他权益工具 贷:银行存款</li>
        <li>CAS37重分类（负债→权益）：借:应付债券 贷:其他权益工具</li>
        <li>CAS37重分类（权益→负债）：借:其他权益工具 贷:应付债券</li>
        <li>AJE = 账项调整分录；RJE = 重分类调整分录</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M10TabAdjustment — M10-3 其他权益工具调整分录汇总（借贷平衡）
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/
 * Task: 4.6
 * Requirements: 5.3
 *
 * 功能：
 * - AJE/RJE 切换（el-segmented）
 * - 动态分录表（借/贷金额 + 科目 + 报表项目 + 类别含CAS37重分类）
 * - 借贷平衡校验（Σ借方===Σ贷方）
 * - 平衡状态指示：绿色=平衡, 红色=不平衡+差额
 * - EventBus publish 'adjustment:created' on save
 * - 双向同步M10-1审定表
 * - 科目4003 其他权益工具: 贷方增加=调增, 借方减少=调减
 */
import { computed, inject, onMounted, ref, toRef, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useM10FormData } from '../../composables/useM10FormData'
import { useM10Adjustment } from '../../composables/useM10Adjustment'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '@/components/workpaper/composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'

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

const formData = useM10FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Adjustment composable ───────────────────────────────────────────────────

const adjustment = useM10Adjustment(formData)

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ─────────────────
const { year: auditYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: toRef(props, 'projectId') as Ref<string>,
  year: auditYear,
  wpId: toRef(props, 'wpId') as Ref<string>,
  wpCode: 'M10',
  itemId: () => `M10-adj-${adjustment.activeType.value}`,
  buildLineItems: () => adjustment.filteredEntries.value.map(e => ({
    account_name: e.accountName,
    report_line_code: e.reportItem || undefined,
    debit_amount: e.debitAmount,
    credit_amount: e.creditAmount,
  })),
  buildMeta: () => ({
    description: adjustment.filteredEntries.value.find(e => e.description)?.description || 'M10 调整（' + adjustment.activeType.value + '）',
    adjustmentType: adjustment.activeType.value === 'RJE' ? 'rje' : 'aje',
  }),
})
watch(adjustment.activeType, () => refreshStatus())

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

const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  let text = ''
  try {
    const bal = adjustment.currentBalance.value
    const entriesCtx = adjustment.filteredEntries.value
      .map(e => `${e.description || '调整'}: ${e.accountName} 借${fmtAmount(e.debitAmount)}/贷${fmtAmount(e.creditAmount)} [${e.category || ''}]`)
      .join('；') || '（暂无调整分录）'
    const context: Record<string, string> = {
      科目: '4003 其他权益工具 / 调整分录汇总（M10-3）',
      调整类型: adjustment.activeType.value,
      调整分录: entriesCtx,
      借方合计: fmtAmount(bal.totalDebit),
      贷方合计: fmtAmount(bal.totalCredit),
      借贷平衡: bal.isBalanced ? '平衡' : `不平衡差异${fmtAmount(bal.diff)}`,
    }
    text = await generateAiText({ section: `m10-adjustment-${section}`, context })
  } catch {
    ElMessage.warning('AI 生成失败，请稍后重试'); aiLoading.value = ''; return
  }
  aiLoading.value = ''
  if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
  ElMessageBox.alert(text, 'AI 辅助 — 调整分录分析建议', { confirmButtonText: '知道了' }).catch(() => { /* 用户关闭 */ })
}

function handleReview() {
  openReviewDialog?.('M10-3-adjustment', '其他权益工具调整分录汇总')
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 恢复已保存分录 ─────────────────────────────────────────────────────────

function restoreEntries(): void {
  const prefix = 'M10-3-entry-'
  let maxIdx = 0
  for (const [key] of formData.allResponses.value.entries()) {
    if (key.startsWith(prefix) && key.endsWith('-data')) {
      const match = key.match(/M10-3-entry-(\d+)-data/)
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

// ─── 导入完成 → 读回宿主（x3-adjustment-entry-import-export 任务 11.1）───

/**
 * 导入 xlsx 成功后重跑本底稿读回路径：M10-3 读回 = 本 Tab restoreEntries（-data 族，push 语义 ⇒ 必须先清空）。
 *
 * 判据（R6.5 / R6.7）：接口返 200 不算通过，界面必须读得到导入的行，
 * 故这里重载 responses 后**必须**重跑读回，而不是只弹一个成功提示。
 */
async function handleImported(): Promise<void> {
  adjustment.entries.value = []
  await formData.loadData()
  restoreEntries()
}
</script>

<style scoped>
.m10-tab-adjustment {
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

.m10-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.m10-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.m10-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
