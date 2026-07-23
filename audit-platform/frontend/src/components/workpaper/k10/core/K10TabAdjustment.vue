<template>
  <div class="k10-tab-adjustment">
    <!-- ═══ 标题 + AJE/RJE切换 + 按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="emit('navigate-sheet', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">K10-3 调整分录汇总</h3>
        <el-tag type="success" effect="dark" size="small" class="account-badge">
          科目6117·贷方增加=调增
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-segmented
          v-model="activeType"
          :options="typeOptions"
          size="small"
        />
        <el-button size="small" @click="handleAI">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <GtReviewTrigger section-id="K10-3-adjustment" label="💬 复核" />
        <el-button
          type="primary"
          size="small"
          :loading="isSaving"
          :disabled="!currentBalance.isBalanced"
          @click="handleSave"
        >
          保存并发布
        </el-button>
      </div>
    </div>

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联底稿：</span>
      <GtIndexChip value="wp:K10-1" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:K10-6" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:K12" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:A13" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>其他收益（6117）调整分录方向说明：</strong>
        其他收益为损益类贷方科目 —
        <strong>贷方增加 = 调增其他收益</strong>（如确认政府补助/即征即退/财政贴息），
        <strong>借方减少 = 冲减其他收益</strong>（如冲回多确认收入）。
        借贷必须平衡后方可保存发布。保存后自动通知K10-1审定表刷新AJE/RJE列，并同步A13错报汇总表。
      </div>
    </div>

    <!-- ═══ 借贷平衡状态指示器 ═══ -->
    <div class="balance-indicator" :class="{ balanced: currentBalance.isBalanced, unbalanced: !currentBalance.isBalanced }">
      <div class="balance-amounts">
        <span class="balance-label">Σ借方:</span>
        <span class="balance-value">{{ fmtAmount(currentBalance.totalDebit) }}</span>
        <span class="balance-separator">|</span>
        <span class="balance-label">Σ贷方:</span>
        <span class="balance-value">{{ fmtAmount(currentBalance.totalCredit) }}</span>
      </div>
      <div class="balance-status">
        <el-tag
          :type="currentBalance.isBalanced ? 'success' : 'danger'"
          size="small"
          effect="dark"
        >
          {{ currentBalance.isBalanced ? '✓ 借贷平衡' : `✗ 不平衡 差额: ${fmtAmount(currentBalance.diff)}` }}
        </el-tag>
      </div>
    </div>

    <!-- ═══ 调整分录表格 ═══ -->
    <el-table
      :data="filteredEntries"
      border
      size="small"
      style="width: 100%"
      :empty-text="`暂无${activeType}调整分录`"
      class="adjustment-table"
    >
      <el-table-column type="index" label="序号" width="60" align="center" />

      <el-table-column label="调整事项" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="!props.isReadonly"
            :model-value="row.description"
            size="small"
            placeholder="调整事项说明"
            @change="(val: string) => handleUpdate(row, 'description', val)"
          />
          <span v-else>{{ row.description || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="类别" width="130">
        <template #default="{ row }">
          <el-select
            v-if="!props.isReadonly"
            :model-value="row.category"
            size="small"
            style="width: 100%"
            @change="(val: string) => handleUpdate(row, 'category', val)"
          >
            <el-option label="报表调整" value="报表调整" />
            <el-option label="账项调整" value="账项调整" />
            <el-option label="其他" value="其他" />
          </el-select>
          <span v-else>{{ row.category || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="报表项目" width="120">
        <template #default="{ row }">
          <el-input
            v-if="!props.isReadonly"
            :model-value="row.reportItem"
            size="small"
            placeholder="报表项目"
            @change="(val: string) => handleUpdate(row, 'reportItem', val)"
          />
          <span v-else>{{ row.reportItem || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目名称" width="130">
        <template #default="{ row }">
          <el-input
            v-if="!props.isReadonly"
            :model-value="row.accountName"
            size="small"
            placeholder="如：其他收益"
            @change="(val: string) => handleUpdate(row, 'accountName', val)"
          />
          <span v-else>{{ row.accountName || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="附注项目" width="110">
        <template #default="{ row }">
          <el-input
            v-if="!props.isReadonly"
            :model-value="row.noteItem"
            size="small"
            placeholder="附注项目"
            @change="(val: string) => handleUpdate(row, 'noteItem', val)"
          />
          <span v-else>{{ row.noteItem || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly"
            :model-value="row.debitAmount"
            :controls="false"
            size="small"
            :min="0"
            style="width: 100%"
            @change="(val: number | undefined) => handleUpdate(row, 'debitAmount', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly"
            :model-value="row.creditAmount"
            :controls="false"
            size="small"
            :min="0"
            style="width: 100%"
            @change="(val: number | undefined) => handleUpdate(row, 'creditAmount', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="索引" width="90">
        <template #default="{ row }">
          <el-input
            v-if="!props.isReadonly"
            :model-value="row.refIndex"
            size="small"
            placeholder="索引"
            @change="(val: string) => handleUpdate(row, 'refIndex', val)"
          />
          <span v-else>{{ row.refIndex || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="备注" width="110">
        <template #default="{ row }">
          <el-input
            v-if="!props.isReadonly"
            :model-value="row.remark"
            size="small"
            placeholder="备注"
            @change="(val: string) => handleUpdate(row, 'remark', val)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!props.isReadonly" label="" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="danger" size="small" link @click="handleRemoveEntry(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 新增按钮 ═══ -->
    <div v-if="!props.isReadonly" class="add-row-bar">
      <el-button size="small" type="primary" plain @click="handleAddEntry">
        + 新增{{ activeType }}分录
      </el-button>
    </div>

    <!-- ═══ 6117净影响汇总 ═══ -->
    <div class="net-impact-section">
      <el-tag type="info" size="small" effect="plain">
        AJE对6117净影响: {{ fmtAmount(ajeNet6117) }}（正=调增收入，负=冲减收入）
      </el-tag>
      <el-tag type="info" size="small" effect="plain">
        RJE对6117净影响: {{ fmtAmount(rjeNet6117) }}（正=调增收入，负=冲减收入）
      </el-tag>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="k10-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>科目6117其他收益：<strong>贷方增加=调增</strong>（确认政府补助/即征即退/财政贴息/稳岗补贴），<strong>借方减少=冲减收入</strong></li>
        <li>借贷必须平衡（Σ借方 === Σ贷方）后方可保存发布</li>
        <li>保存后发布 'adjustment:created' 事件：①通知K10-1审定表刷新AJE/RJE列 ②A13错报汇总表拾取</li>
        <li>间接触发附注刷新链路：K10-3→K10-1 recalc→writebackTB→substantive:adjudicated→附注</li>
        <li>AJE = 审计调整分录；RJE = 重分类调整分录</li>
        <li>与日常活动相关的政府补助计入6117其他收益；与日常活动无关计入6301营业外收入(K12)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K10TabAdjustment — K10-3 其他收益调整分录汇总（借贷平衡+EventBus）
 *
 * Spec: .kiro/specs/k10-other-income/
 * Task: 4.6
 * Requirements: 7.2
 *
 * 功能：
 * - AJE/RJE 切换（el-segmented）
 * - 调整事项/类别(报表调整/账项调整/其他)/报表项目/科目名称/附注项目/借方金额/贷方金额/索引/备注
 * - 借贷平衡校验（Σ借方===Σ贷方, |diff|<=0.01）
 * - EventBus publish 'adjustment:created' on save → A13
 * - 双向同步K10-1审定表
 * - 导入导出
 * - 科目6117 其他收益: 贷方增加=调增, 借方减少=冲减
 */
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

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

// ─── Types ───────────────────────────────────────────────────────────────────

interface AdjustmentEntry {
  id: string
  type: 'AJE' | 'RJE'
  description: string
  category: string
  reportItem: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  refIndex: string
  remark: string
}

// ─── State ───────────────────────────────────────────────────────────────────

const entries = ref<AdjustmentEntry[]>([])
const activeType = ref<'AJE' | 'RJE'>('AJE')
const isSaving = ref(false)

const typeOptions = [
  { label: 'AJE 审计调整', value: 'AJE' },
  { label: 'RJE 重分类', value: 'RJE' },
]

// ─── Computed ────────────────────────────────────────────────────────────────

const filteredEntries = computed(() =>
  entries.value.filter(e => e.type === activeType.value)
)

const ajeEntries = computed(() => entries.value.filter(e => e.type === 'AJE'))
const rjeEntries = computed(() => entries.value.filter(e => e.type === 'RJE'))

const currentBalance = computed(() => {
  const list = filteredEntries.value
  const totalDebit = list.reduce((s, e) => s + (e.debitAmount || 0), 0)
  const totalCredit = list.reduce((s, e) => s + (e.creditAmount || 0), 0)
  const diff = totalDebit - totalCredit
  return { totalDebit, totalCredit, diff, isBalanced: Math.abs(diff) <= 0.01 }
})

/** AJE对6117净影响（贷方-借方，贷方科目） */
const ajeNet6117 = computed(() => {
  const list = ajeEntries.value
  return list.reduce((s, e) => s + (e.creditAmount || 0) - (e.debitAmount || 0), 0)
})

/** RJE对6117净影响 */
const rjeNet6117 = computed(() => {
  const list = rjeEntries.value
  return list.reduce((s, e) => s + (e.creditAmount || 0) - (e.debitAmount || 0), 0)
})

// ─── Load/Save ───────────────────────────────────────────────────────────────

function loadEntries(): void {
  const raw = props.allResponses.get('K10-3-entries')
  if (!raw) return
  try {
    const parsed = typeof raw.remark === 'string' ? JSON.parse(raw.remark) : raw.remark
    if (Array.isArray(parsed)) {
      entries.value = parsed.map((e: any) => ({
        id: e.id ?? `entry-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        type: e.type === 'RJE' ? 'RJE' : 'AJE',
        description: e.description ?? '',
        category: e.category ?? '',
        reportItem: e.reportItem ?? '',
        accountName: e.accountName ?? '',
        noteItem: e.noteItem ?? '',
        debitAmount: Number(e.debitAmount || 0),
        creditAmount: Number(e.creditAmount || 0),
        refIndex: e.refIndex ?? '',
        remark: e.remark ?? '',
      }))
    }
  } catch { /* ignore */ }
}

function persistEntries(): void {
  emit('save', 'K10-3-entries', entries.value)
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function fmtAmount(val: number | undefined | null): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleUpdate(row: AdjustmentEntry, field: string, value: string | number): void {
  const entry = entries.value.find(e => e.id === row.id)
  if (!entry) return
  ;(entry as any)[field] = value
  persistEntries()
}

function handleRemoveEntry(row: AdjustmentEntry): void {
  const idx = entries.value.findIndex(e => e.id === row.id)
  if (idx >= 0) {
    entries.value.splice(idx, 1)
    persistEntries()
  }
}

/** 新增分录 */
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
    entries.value.push({
      id: `entry-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      type: activeType.value,
      description: value.trim(),
      category: '',
      reportItem: '',
      accountName: '其他收益',
      noteItem: '',
      debitAmount: 0,
      creditAmount: 0,
      refIndex: '',
      remark: '',
    })
    persistEntries()
  } catch {
    // 用户取消
  }
}

/** 保存并发布（EventBus） */
async function handleSave(): Promise<void> {
  if (!currentBalance.value.isBalanced) {
    ElMessage.warning('借贷不平衡，无法保存')
    return
  }
  isSaving.value = true
  try {
    persistEntries()
    // Publish adjustment:created → A13 + K10-1
    eventBus.emit('adjustment:created' as any, {
      entryType: activeType.value,
      accountCode: '6117',
      wpCode: 'K10',
      ajeAmount: ajeNet6117.value,
      rjeAmount: rjeNet6117.value,
      timestamp: Date.now(),
    })
    // 显式推送错报至 A13（对齐平台 a13:push-misstatement 约定事件，crossWpEventBridge 白名单）
    eventBus.emit('a13:push-misstatement' as any, {
      wpCode: 'K10',
      accountCode: '6117',
      accountName: '其他收益',
      entryType: activeType.value,
      entries: filteredEntries.value.map(e => ({
        description: e.description,
        reportItem: e.reportItem,
        accountName: e.accountName,
        debitAmount: e.debitAmount,
        creditAmount: e.creditAmount,
        refIndex: e.refIndex,
      })),
      ajeAmount: ajeNet6117.value,
      rjeAmount: rjeNet6117.value,
      timestamp: Date.now(),
    })
    ElMessage.success('调整分录已保存并发布')
    emit('save', 'K10-3-published', { timestamp: Date.now() })
  } finally {
    isSaving.value = false
  }
}

/** AI 辅助：基于当前分录给出调整分录建议（顾问式，弹窗展示供参考） */
async function handleAI(): Promise<void> {
  if (!props.wpId) return
  try {
    const ctx = {
      科目: '6117 其他收益（损益类·贷方增加=调增）',
      当前类型: activeType.value,
      借方合计: String(currentBalance.value.totalDebit),
      贷方合计: String(currentBalance.value.totalCredit),
      分录: entries.value.map(e => `${e.type} ${e.description} 借${e.debitAmount}/贷${e.creditAmount}`).join('；') || '（暂无）',
    }
    const res = await api.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'K10-3-adjustment',
      prompt: '为K10其他收益(6117)调整分录提供审计建议：常见调整场景（政府补助分类纠正6117↔6301、递延分摊转入、多确认冲回）、借贷方向与平衡校验要点。',
      context: ctx,
    })
    const content = (res?.data?.content ?? res?.content ?? '') as string
    if (content) {
      await ElMessageBox.alert(content, 'AI 调整分录建议', { confirmButtonText: '知道了', dangerouslyUseHTMLString: false })
    } else {
      ElMessage.warning('AI未返回内容')
    }
  } catch { ElMessage.warning('AI生成失败，请稍后重试') }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────
// 数据来源 props.allResponses（父 GtK10OtherIncome 已 selfLoad populate）；
// 组件随 sheet 切换 v-if 重新挂载 → onMounted 载入；父级 reload 时 watch 兜底刷新。
onMounted(() => { loadEntries() })
watch(() => props.allResponses, () => loadEntries())
</script>

<style scoped>
.k10-tab-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; }
.account-badge { font-size: 11px; }

.cross-ref-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-bottom: 12px; padding: 6px 12px;
  background: #f5f7fa; border-radius: 6px;
}
.cross-refs-label { color: #909399; font-size: 12px; white-space: nowrap; }

.methodology-context {
  background: linear-gradient(135deg, #fffbe6 0%, #fff8e1 100%);
  border-left: 3px solid #e6a23c;
  padding: 8px 12px; margin-bottom: 12px;
  border-radius: 0 4px 4px 0; font-size: 12px; color: #8b6914;
}
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

.adjustment-table { font-size: var(--wp-font-size, 13px); }

.add-row-bar { margin-top: 12px; }

.net-impact-section {
  display: flex; gap: 12px; margin-top: 12px; flex-wrap: wrap;
}

.k10-details-tip {
  margin-top: 16px; padding: 8px 12px;
  background: #f5f7fa; border-radius: 4px;
  font-size: 12px; color: #606266;
}
.k10-details-tip summary { cursor: pointer; font-weight: 500; color: #409eff; }
.k10-details-tip ul { margin: 8px 0 0 0; padding-left: 20px; }
.k10-details-tip li { margin-bottom: 4px; }
</style>
