<template>
  <div class="k13-tab-adjustment">
    <!-- ═══ 标题 + AJE/RJE切换 + 按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="emit('navigate-sheet', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">K13-3 调整分录汇总</h3>
        <el-tag type="warning" effect="dark" size="small" class="account-badge">
          科目6711·借方增加=调增支出
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-segmented
          v-model="adjustment.activeType.value"
          :options="typeOptions"
          size="small"
          @change="(val: any) => adjustment.switchType(val)"
        />
        <el-dropdown v-if="!props.isReadonly" trigger="click" @command="handleIECommand">
          <el-button size="small" plain>导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" :loading="isAiLoading" @click="handleAI">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <GtReviewTrigger section-id="K13-3-adjustment" label="💬 复核" />
        <el-button
          type="primary"
          size="small"
          :loading="isSaving"
          :disabled="!adjustment.currentBalance.value.isBalanced"
          @click="handleSave"
        >
          保存并发布
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="centralSyncing"
          :disabled="props.isReadonly || !adjustment.currentBalance.value.isBalanced || adjustment.filteredEntries.value.length === 0"
          @click="syncToCentral"
          title="把本页调整分录汇聚到集中调整登记，供合伙人跨循环审阅"
        >
          同步到集中登记
        </el-button>
        <el-tag
          v-if="centralStatus?.review_status"
          size="small"
          :type="centralStatus.review_status === 'approved' ? 'success' : (centralStatus.review_status === 'rejected' ? 'danger' : 'info')"
          :title="centralStatus.rejection_reason || ''"
        >
          集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status] || centralStatus.review_status }}
        </el-tag>
      </div>
    </div>

    <!-- ═══ 跨底稿引用（GtIndexChip：K13-3 → A13） ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联底稿：</span>
      <GtIndexChip value="K13-1" :context-project-id="props.projectId" />
      <GtIndexChip value="A13" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>营业外支出（6711）调整分录方向说明：</strong>
        营业外支出为损益类借方科目 —
        <strong>借方增加 = 调增营业外支出</strong>（如确认非流动资产处置损失/捐赠支出/罚款滞纳金/债务重组损失/资产盘亏损失），
        <strong>贷方减少 = 冲减营业外支出</strong>（如冲回多计支出）。
        借贷必须平衡后方可保存发布。保存后自动通知K13-1审定表刷新AJE/RJE列，并同步A13错报汇总表。
      </div>
    </div>

    <!-- ═══ 借贷不平衡红色警告 ═══ -->
    <el-alert
      v-if="!adjustment.currentBalance.value.isBalanced"
      type="error"
      :closable="false"
      show-icon
      class="balance-alert"
    >
      <template #title>
        借贷不平衡！差额: {{ fmtAmount(adjustment.currentBalance.value.diff) }}
        （Σ借方: {{ fmtAmount(adjustment.currentBalance.value.totalDebit) }} | Σ贷方: {{ fmtAmount(adjustment.currentBalance.value.totalCredit) }}）
      </template>
    </el-alert>

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
      <el-table-column type="index" label="序号" width="55" align="center" />

      <el-table-column label="调整事项说明" min-width="160">
        <template #default="{ row, $index }">
          <el-input
            v-if="!props.isReadonly"
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
            v-if="!props.isReadonly"
            :model-value="row.category"
            size="small"
            placeholder="类别"
            clearable
            @change="(val: string) => handleUpdateEntry($index, 'category', val)"
          >
            <el-option v-for="opt in categoryOptions" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <span v-else>{{ row.category || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="报表项目" width="120">
        <template #default="{ row, $index }">
          <el-input
            v-if="!props.isReadonly"
            :model-value="row.reportItem"
            size="small"
            placeholder="报表项目"
            @change="(val: string) => handleUpdateEntry($index, 'reportItem', val)"
          />
          <span v-else>{{ row.reportItem || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目名称" width="120">
        <template #default="{ row, $index }">
          <el-input
            v-if="!props.isReadonly"
            :model-value="row.accountName"
            size="small"
            placeholder="如：营业外支出"
            @change="(val: string) => handleUpdateEntry($index, 'accountName', val)"
          />
          <span v-else>{{ row.accountName || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="附注项目" width="110">
        <template #default="{ row, $index }">
          <el-input
            v-if="!props.isReadonly"
            :model-value="row.noteItem"
            size="small"
            placeholder="附注项目"
            @change="(val: string) => handleUpdateEntry($index, 'noteItem', val)"
          />
          <span v-else>{{ row.noteItem || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方金额" width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!props.isReadonly"
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

      <el-table-column label="贷方金额" width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!props.isReadonly"
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

      <el-table-column label="索引" width="90">
        <template #default="{ row, $index }">
          <el-input
            v-if="!props.isReadonly"
            :model-value="row.refIndex"
            size="small"
            placeholder="索引"
            @change="(val: string) => handleUpdateEntry($index, 'refIndex', val)"
          />
          <span v-else>{{ row.refIndex || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="备注" width="110">
        <template #default="{ row, $index }">
          <el-input
            v-if="!props.isReadonly"
            :model-value="row.remark"
            size="small"
            placeholder="备注"
            @change="(val: string) => handleUpdateEntry($index, 'remark', val)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!props.isReadonly" label="" width="55" align="center" fixed="right">
        <template #default="{ $index }">
          <el-button type="danger" size="small" link @click="handleRemoveEntry($index)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 新增按钮 ═══ -->
    <div v-if="!props.isReadonly" class="add-row-bar">
      <el-button size="small" type="primary" plain @click="handleAddEntry">
        + 新增{{ adjustment.activeType.value }}分录
      </el-button>
    </div>

    <!-- ═══ 6711净影响汇总 ═══ -->
    <div class="net-impact-section">
      <el-tag type="info" size="small" effect="plain">
        AJE对6711净影响: {{ fmtAmount(adjustment.ajeNet6711.value) }}（正=调增支出，负=冲减支出）
      </el-tag>
      <el-tag type="info" size="small" effect="plain">
        RJE对6711净影响: {{ fmtAmount(adjustment.rjeNet6711.value) }}（正=调增支出，负=冲减支出）
      </el-tag>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="k13-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>科目6711营业外支出：<strong>借方增加=调增支出</strong>（非流动资产处置损失/捐赠/罚款滞纳金/债务重组损失/资产盘亏损失），<strong>贷方减少=冲减支出</strong></li>
        <li>类别下拉：报表调整（影响审定表金额）/账项调整（不影响报表但修正账面）/其他</li>
        <li>借贷必须平衡（Σ借方 === Σ贷方）后方可保存发布</li>
        <li>保存后发布 'adjustment:created' 事件：①通知K13-1审定表刷新AJE/RJE列 ②A13错报汇总表拾取</li>
        <li>间接触发附注刷新链路：K13-3→K13-1 recalc→writebackTB→substantive:adjudicated→附注</li>
        <li>AJE = 审计调整分录；RJE = 重分类调整分录</li>
        <li>⚠️ 与K12(6301贷方)方向相反！K13净影响=借方-贷方</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K13TabAdjustment — K13-3 营业外支出调整分录汇总（借贷平衡+EventBus）
 *
 * Spec: .kiro/specs/k13-non-operating-expense/
 * Task: 4.5
 * Requirements: 6.2
 *
 * 功能：
 * - AJE/RJE 切换（el-segmented）
 * - 动态分录表（9列：调整事项说明|类别|报表项目|科目名称|附注项目|借方金额|贷方金额|索引|备注）
 * - 类别下拉：报表调整/账项调整/其他（el-select 点选）
 * - 借贷平衡校验（Σ借方===Σ贷方），不平衡时 el-alert 红色警告
 * - EventBus publish 'adjustment:created' on save → A13 + K13-1
 * - 科目6711 营业外支出: 借方增加=调增支出, 贷方减少=冲减支出
 * - 导入导出支持（exportEntries/importEntries）
 * - 双向同步K13-1：保存后 K13-1 订阅 adjustment:created 刷新 AJE/RJE 列
 *
 * 事件流：
 *   K13-3 save → emit 'adjustment:created' {entryType, accountCode:'6711', amount, wpCode:'K13'}
 *   Backend: _on_adjustment_created handler picks up K13-3 entries (regex ^[D-N]\d+-3$ matches K13-3)
 *   Disclosure refresh: INDIRECT via K13-1 recalc → writebackTB → substantive:adjudicated
 */
import { computed, onMounted, ref, defineAsyncComponent } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK13FormData } from '../../composables/useK13FormData'
import { useK13Adjustment } from '../../composables/useK13Adjustment'
import { useK13ImportExport } from '../../composables/useK13ImportExport'
import { generateK13AiText } from '../../composables/useK13AiText'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Composables ─────────────────────────────────────────────────────────────

const formData = useK13FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  sheetName: ref('调整分录汇总K13-3'),
})

const adjustment = useK13Adjustment(formData)

const importExport = useK13ImportExport({
  wpId: computed(() => props.wpId) as any,
  projectId: computed(() => props.projectId) as any,
  sheetCode: 'K13-3',
})

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ──────────
const { year: auditYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: () => props.projectId,
  year: auditYear,
  wpId: () => props.wpId,
  wpCode: 'K13',
  itemId: () => `K13-adj-${adjustment.activeType.value}`,
  buildLineItems: () => adjustment.filteredEntries.value.map(e => ({
    account_name: e.accountName,
    report_line_code: e.reportItem || undefined,
    debit_amount: e.debitAmount,
    credit_amount: e.creditAmount,
  })),
  buildMeta: () => ({
    description: adjustment.filteredEntries.value.find(e => e.description)?.description || 'K13 营业外支出调整',
    adjustmentType: adjustment.activeType.value === 'RJE' ? 'rje' : 'aje',
  }),
})

// ─── UI State ────────────────────────────────────────────────────────────────

const isSaving = ref(false)
const isAiLoading = ref(false)

const typeOptions = [
  { label: 'AJE 审计调整', value: 'AJE' },
  { label: 'RJE 重分类', value: 'RJE' },
]

/** 类别下拉选项（el-select 点选） */
const categoryOptions = ['报表调整', '账项调整', '其他']

// ─── Handlers ────────────────────────────────────────────────────────────────

function fmtAmount(val: number | undefined | null): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

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

/** 新增分录（ElMessageBox.prompt输入名称） */
async function handleAddEntry(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入调整事项说明',
      '新增调整分录',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPlaceholder: '如：确认非流动资产处置损失...',
        inputValidator: (val: string) => {
          if (!val || !val.trim()) return '请输入调整事项说明'
          return true
        },
      },
    )
    adjustment.addEntry()
    // 设置描述到最后一条
    const entries = adjustment.entries.value
    if (entries.length > 0) {
      adjustment.updateEntry(entries.length - 1, 'description', value.trim())
    }
  } catch {
    // 用户取消
  }
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
    emit('save', 'K13-3-published', { timestamp: Date.now() })
  } finally {
    isSaving.value = false
  }
}

/** AI 辅助：基于当前分录汇总，生成调整事项分析/复核意见（顾问式弹窗，不覆盖表格） */
async function handleAI(): Promise<void> {
  const entries = adjustment.entries.value
  if (entries.length === 0) {
    ElMessage.info('暂无调整分录，请先录入后再生成 AI 分析')
    return
  }
  isAiLoading.value = true
  try {
    const bal = adjustment.currentBalance.value
    const lines = entries
      .filter(e => e.debitAmount || e.creditAmount)
      .map(e => `[${e.type}] ${e.description || '(未填说明)'}｜借${e.debitAmount || 0}｜贷${e.creditAmount || 0}｜${e.category || '未分类'}`)
      .join('\n')
    const content = await generateK13AiText(props.wpId, {
      section: 'k13-3-adjustment-analysis',
      prompt: '你是审计师，请针对以下营业外支出（科目6711，借方增加=调增支出）调整分录汇总，简要分析调整事项的合理性、方向是否正确、是否影响税前扣除，并给出复核意见。',
      context: {
        科目: '6711 营业外支出（损益类借方）',
        当前类型: adjustment.activeType.value,
        分录明细: lines || '（无金额分录）',
        借方合计: bal.totalDebit,
        贷方合计: bal.totalCredit,
        是否平衡: bal.isBalanced ? '是' : `否，差额${bal.diff}`,
        AJE净影响6711: adjustment.ajeNet6711.value,
        RJE净影响6711: adjustment.rjeNet6711.value,
      },
    })
    if (content) {
      await ElMessageBox.alert(content, 'AI 调整分录分析（仅供参考）', {
        confirmButtonText: '知道了',
        customClass: 'k13-ai-alert',
      })
    }
  } finally {
    isAiLoading.value = false
  }
}

/** 导入导出（K13-3 调整分录，单一 JSON 数组 round-trip） */
function handleIECommand(cmd: string): void {
  if (cmd === 'template') {
    void importExport.exportTemplate()
  } else if (cmd === 'export') {
    void importExport.exportData()
  } else if (cmd === 'import') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls'
    input.onchange = async (event: Event) => {
      const file = (event.target as HTMLInputElement).files?.[0]
      if (!file) return
      const result = await importExport.importData(file)
      if (result) {
        // 重新加载 checklist_responses 后恢复分录（导入后刷新）
        await formData.selfLoad()
        adjustment.restoreEntries()
      }
    }
    input.click()
  }
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.selfLoad()
  adjustment.restoreEntries()
  refreshStatus()
})
</script>

<style scoped>
.k13-tab-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; }
.account-badge { font-size: 11px; }

/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context {
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  padding: 10px 14px; margin-bottom: 12px;
  border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6;
}

/* 跨底稿引用 */
.cross-ref-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-bottom: 12px; padding: 6px 12px;
  background: #f5f7fa; border-radius: 6px;
}
.cross-refs-label { color: #909399; font-size: 12px; white-space: nowrap; }
.methodology-text strong { color: #c77d00; }

/* 借贷不平衡 el-alert 红色警告 */
.balance-alert { margin-bottom: 12px; }

/* 借贷平衡指示器 */
.balance-indicator {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 12px; border-radius: 4px; margin-bottom: 12px;
  transition: background-color 0.3s;
}
.balance-indicator.balanced { background: #f0f9eb; border: 1px solid #c2e7b0; }
.balance-indicator.unbalanced { background: #fef0f0; border: 1px solid #f5c4c4; }
.balance-amounts { display: flex; align-items: center; gap: 8px; }
.balance-label { color: #606266; font-size: 12px; }
.balance-value { font-weight: 600; font-size: var(--wp-font-size, 13px); color: #303133; }
.balance-separator { color: #dcdfe6; }

/* 新增按钮 */
.add-row-bar { margin-top: 12px; }

/* 净影响汇总 */
.net-impact-section {
  display: flex; gap: 12px; margin-top: 12px; flex-wrap: wrap;
}

/* 编制提示 */
.k13-details-tip {
  margin-top: 16px; padding: 8px 12px;
  background: #f5f7fa; border-radius: 4px;
  font-size: 12px; color: #606266;
}
.k13-details-tip summary {
  cursor: pointer; font-weight: 500; color: #409eff;
}
.k13-details-tip ul { margin: 8px 0 0 0; padding-left: 20px; }
.k13-details-tip li { margin-bottom: 4px; }
</style>
