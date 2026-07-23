<template>
  <div class="k12-tab-adjustment">
    <!-- ═══ 标题 + AJE/RJE切换 + 按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="emit('navigate-sheet', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">K12-3 调整分录汇总</h3>
        <el-tag type="success" effect="dark" size="small" class="account-badge">
          科目6301·贷方增加=调增
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-segmented
          v-model="adjustment.activeType.value"
          :options="typeOptions"
          size="small"
          @change="(val: any) => adjustment.switchType(val)"
        />
        <el-button size="small" :loading="aiLoading" @click="handleAI('adjustment')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <GtReviewTrigger section-id="K12-3-adjustment" label="💬 复核" />
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

    <!-- ═══ 跨底稿引用（GtIndexChip：K12-3 → A13） ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联底稿：</span>
      <GtIndexChip value="K12-1" :context-project-id="props.projectId" />
      <GtIndexChip value="A13" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>营业外收入（6301）调整分录方向说明：</strong>
        营业外收入为损益类贷方科目 —
        <strong>贷方增加 = 调增营业外收入</strong>（如确认政府补助/债务重组利得/资产盘盈利得/罚款收入/捐赠利得），
        <strong>借方减少 = 冲减营业外收入</strong>（如冲回多确认收入）。
        借贷必须平衡后方可保存发布。保存后自动通知K12-1审定表刷新AJE/RJE列，并同步A13错报汇总表。
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
            v-if="!props.isReadonly"
            :model-value="row.description"
            size="small"
            placeholder="调整事项说明"
            @change="(val: string) => handleUpdateEntry($index, 'description', val)"
          />
          <span v-else>{{ row.description || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目编码" width="110">
        <template #default="{ row, $index }">
          <el-input
            v-if="!props.isReadonly"
            :model-value="row.accountCode"
            size="small"
            placeholder="如6301"
            @change="(val: string) => handleUpdateEntry($index, 'accountCode', val)"
          />
          <span v-else>{{ row.accountCode || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目名称" width="140">
        <template #default="{ row, $index }">
          <el-input
            v-if="!props.isReadonly"
            :model-value="row.accountName"
            size="small"
            placeholder="如：营业外收入"
            @change="(val: string) => handleUpdateEntry($index, 'accountName', val)"
          />
          <span v-else>{{ row.accountName || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方金额" width="130" align="right">
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

      <el-table-column label="贷方金额" width="130" align="right">
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

      <el-table-column label="索引号" width="100">
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

      <el-table-column label="备注" width="120">
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
      <el-table-column v-if="!props.isReadonly" label="" width="60" align="center" fixed="right">
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

    <!-- ═══ 6301净影响汇总 ═══ -->
    <div class="net-impact-section">
      <el-tag type="info" size="small" effect="plain">
        AJE对6301净影响: {{ fmtAmount(adjustment.ajeNet6301.value) }}（正=调增收入，负=冲减收入）
      </el-tag>
      <el-tag type="info" size="small" effect="plain">
        RJE对6301净影响: {{ fmtAmount(adjustment.rjeNet6301.value) }}（正=调增收入，负=冲减收入）
      </el-tag>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="k12-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>科目6301营业外收入：<strong>贷方增加=调增</strong>（确认政府补助/债务重组利得/资产盘盈/罚款/捐赠），<strong>借方减少=冲减收入</strong></li>
        <li>借贷必须平衡（Σ借方 === Σ贷方）后方可保存发布</li>
        <li>保存后发布 'adjustment:created' 事件：①通知K12-1审定表刷新AJE/RJE列 ②A13错报汇总表拾取</li>
        <li>间接触发附注刷新链路：K12-3→K12-1 recalc→writebackTB→substantive:adjudicated→附注</li>
        <li>AJE = 审计调整分录；RJE = 重分类调整分录</li>
        <li>与日常活动无关的利得计入6301营业外收入；与日常活动相关的利得计入6117其他收益(K10)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K12TabAdjustment — K12-3 营业外收入调整分录汇总（借贷平衡+EventBus）
 *
 * Spec: .kiro/specs/k12-non-operating-income/
 * Task: 6.2
 * Requirements: 6.2
 *
 * 功能：
 * - AJE/RJE 切换（el-segmented）
 * - 动态分录表（借/贷金额 + 科目 + 调整事项）
 * - 借贷平衡校验（Σ借方===Σ贷方）
 * - 平衡状态指示器：绿色=平衡, 红色=不平衡+差额
 * - EventBus publish 'adjustment:created' on save → A13 + K12-1
 * - 科目6301 营业外收入: 贷方增加=调增, 借方减少=冲减
 *
 * 事件流：
 *   K12-3 save → emit 'adjustment:created' {entryType, accountCode:'6301', amount, wpCode:'K12'}
 *   Backend: _on_adjustment_created handler picks up K12-3 entries (regex ^[D-N]\d+-3$ matches K12-3)
 *   Disclosure refresh: INDIRECT via K12-1 recalc → writebackTB → substantive:adjudicated
 */
import { computed, onMounted, ref, defineAsyncComponent } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK12FormData } from '../../composables/useK12FormData'
import { useK12Adjustment } from '../../composables/useK12Adjustment'
import { generateK12AiText } from '../../composables/useK12AiText'
import { eventBus } from '@/utils/eventBus'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))
const GtReviewTrigger = defineAsyncComponent(() => import('../../GtReviewTrigger.vue'))

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

const formData = useK12FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  sheetName: ref('调整分录汇总K12-3'),
})

const adjustment = useK12Adjustment(formData)

// ─── UI State ────────────────────────────────────────────────────────────────

const isSaving = ref(false)

const typeOptions = [
  { label: 'AJE 审计调整', value: 'AJE' },
  { label: 'RJE 重分类', value: 'RJE' },
]

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
        inputPlaceholder: '如：确认政府补助收入...',
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
    emit('save', 'K12-3-published', { timestamp: Date.now() })
  } finally {
    isSaving.value = false
  }
}

const aiLoading = ref(false)

async function handleAI(_section: string): Promise<void> {
  if (aiLoading.value) return
  aiLoading.value = true
  try {
    const entries = adjustment.filteredEntries.value
    const context: Record<string, unknown> = {
      科目: '6301 营业外收入（贷方增加=调增，借方减少=冲减）',
      调整类别: adjustment.activeType.value,
      分录数: entries.length,
      借方合计: fmtAmount(adjustment.currentBalance.value.totalDebit),
      贷方合计: fmtAmount(adjustment.currentBalance.value.totalCredit),
      是否平衡: adjustment.currentBalance.value.isBalanced ? '平衡' : '不平衡',
      分录明细: entries
        .map(e => `${e.description || '—'}: 借${fmtAmount(e.debitAmount)}/贷${fmtAmount(e.creditAmount)}`)
        .slice(0, 20)
        .join('；'),
    }
    const content = await generateK12AiText(props.wpId, {
      prompt: '你是资深审计师。请基于营业外收入调整分录，评价调整事项的合理性与借贷平衡，并就是否影响非经常性损益列报给出复核意见，供人工确认。',
      section: 'K12-3-adjustment',
      context,
    })
    if (!content) return
    await ElMessageBox.alert(content, 'AI 调整分录复核建议', { confirmButtonText: '知道了' })
  } catch { /* cancelled */ } finally {
    aiLoading.value = false
  }
}


// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.selfLoad()
  adjustment.restoreEntries()
})
</script>

<style scoped>
.k12-tab-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }

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
  background: linear-gradient(135deg, #fffbe6 0%, #fff8e1 100%);
  border-left: 3px solid #e6a23c;
  padding: 8px 12px; margin-bottom: 12px;
  border-radius: 0 4px 4px 0; font-size: 12px; color: #8b6914;
}

/* 跨底稿引用 */
.cross-ref-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-bottom: 12px; padding: 6px 12px;
  background: #f5f7fa; border-radius: 6px;
}
.cross-refs-label { color: #909399; font-size: 12px; white-space: nowrap; }
.methodology-text strong { color: #c77d00; }

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
.k12-details-tip {
  margin-top: 16px; padding: 8px 12px;
  background: #f5f7fa; border-radius: 4px;
  font-size: 12px; color: #606266;
}
.k12-details-tip summary {
  cursor: pointer; font-weight: 500; color: #409eff;
}
.k12-details-tip ul { margin: 8px 0 0 0; padding-left: 20px; }
.k12-details-tip li { margin-bottom: 4px; }
</style>
