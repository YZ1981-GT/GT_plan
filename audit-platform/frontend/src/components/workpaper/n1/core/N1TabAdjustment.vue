<template>
  <div class="n1-tab-adjustment">
    <!-- ═══ 双模式切换 ═══ -->
    <div class="n1-mode-bar">
      <el-segmented v-model="dualMode.mode.value" :options="dualMode.modeOptions.value" @change="dualMode.switchMode" />
    </div>

    <template v-if="dualMode.isOnlyOffice.value">
      <GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="调整分录汇总N1-3" style="height: 100%; min-height: 600px" />
    </template>

    <template v-else>
      <!-- ═══ Section Header ═══ -->
      <div class="section-header">
        <div class="section-title">
          <span>调整分录汇总 N1-3</span>
          <el-tag type="success" size="small" class="asset-tag">资产类·借方·1811</el-tag>
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
          <el-button size="small" @click="handleAI('adjustment')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
          <el-button size="small" @click="openReview?.('N1-3-调整分录')">
            <el-icon><ChatDotSquare /></el-icon> 复核
          </el-button>
        </div>
      </div>

      <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
      <div class="n1-methodology-ctx">
        <div class="methodology-text">
          <strong>调整分录规则：</strong>
          AJE（审计调整分录）/RJE（重分类调整分录）需保持借贷平衡（∑借方 === ∑贷方）。
          不平衡时无法保存。保存后自动同步至 N1-1 审定表的 AJE/RJE 列，并通知 A13 审计调整汇总。
          科目1811递延所得税资产为借方/资产类科目：借方增加（确认递延税资产），贷方减少（转回递延税资产）。
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
          <span class="balance-value">{{ fmtAmt(currentBalance.totalDebit) }}</span>
        </div>
        <div class="balance-row">
          <span class="balance-label">贷方合计：</span>
          <span class="balance-value">{{ fmtAmt(currentBalance.totalCredit) }}</span>
        </div>
        <div class="balance-row balance-diff">
          <span class="balance-label">差额：</span>
          <span class="balance-value">{{ fmtAmt(currentBalance.diff) }}</span>
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
        max-height="500"
        empty-text="暂无调整分录，点击下方按钮新增"
      >
        <!-- 序号 -->
        <el-table-column label="序号" width="55" align="center">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>

        <!-- 调整事项说明 -->
        <el-table-column label="调整事项说明" min-width="160">
          <template #default="{ $index }">
            <template v-if="!isReadonly">
              <el-input
                :model-value="filteredEntries[$index].description"
                size="small"
                placeholder="输入调整事项"
                @input="(val: string) => handleFieldChange($index, 'description', val)"
              />
            </template>
            <span v-else>{{ filteredEntries[$index].description || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 类别 -->
        <el-table-column label="类别" width="120">
          <template #default="{ $index }">
            <template v-if="!isReadonly">
              <el-select
                :model-value="filteredEntries[$index].category"
                size="small"
                placeholder="选择"
                @change="(val: string) => handleFieldChange($index, 'category', val)"
              >
                <el-option value="报表调整" label="报表调整" />
                <el-option value="账项调整" label="账项调整" />
                <el-option value="其他" label="其他" />
              </el-select>
            </template>
            <span v-else>{{ filteredEntries[$index].category || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 报表项目 -->
        <el-table-column label="报表项目" width="120">
          <template #default="{ $index }">
            <template v-if="!isReadonly">
              <el-input
                :model-value="filteredEntries[$index].reportItem"
                size="small"
                placeholder="报表项目"
                @input="(val: string) => handleFieldChange($index, 'reportItem', val)"
              />
            </template>
            <span v-else>{{ filteredEntries[$index].reportItem || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 科目名称 -->
        <el-table-column label="科目名称" width="140">
          <template #default="{ $index }">
            <template v-if="!isReadonly">
              <el-input
                :model-value="filteredEntries[$index].accountName"
                size="small"
                placeholder="科目名称"
                @input="(val: string) => handleFieldChange($index, 'accountName', val)"
              />
            </template>
            <span v-else>{{ filteredEntries[$index].accountName || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 附注项目 -->
        <el-table-column label="附注项目" width="110">
          <template #default="{ $index }">
            <template v-if="!isReadonly">
              <el-input
                :model-value="filteredEntries[$index].noteItem"
                size="small"
                placeholder="附注项目"
                @input="(val: string) => handleFieldChange($index, 'noteItem', val)"
              />
            </template>
            <span v-else>{{ filteredEntries[$index].noteItem || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 借方调整金额 -->
        <el-table-column label="借方调整金额" width="130" align="right">
          <template #default="{ $index }">
            <template v-if="!isReadonly">
              <el-input-number
                :model-value="filteredEntries[$index].debitAmount"
                :controls="false"
                :min="0"
                :precision="2"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => handleFieldChange($index, 'debitAmount', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmt(filteredEntries[$index].debitAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 贷方调整金额 -->
        <el-table-column label="贷方调整金额" width="130" align="right">
          <template #default="{ $index }">
            <template v-if="!isReadonly">
              <el-input-number
                :model-value="filteredEntries[$index].creditAmount"
                :controls="false"
                :min="0"
                :precision="2"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => handleFieldChange($index, 'creditAmount', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmt(filteredEntries[$index].creditAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 索引 -->
        <el-table-column label="索引" width="90">
          <template #default="{ $index }">
            <template v-if="!isReadonly">
              <el-input
                :model-value="filteredEntries[$index].refIndex"
                size="small"
                placeholder="索引"
                @input="(val: string) => handleFieldChange($index, 'refIndex', val)"
              />
            </template>
            <span v-else>{{ filteredEntries[$index].refIndex || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 备注 -->
        <el-table-column label="备注" width="110">
          <template #default="{ $index }">
            <template v-if="!isReadonly">
              <el-input
                :model-value="filteredEntries[$index].remark"
                size="small"
                placeholder="备注"
                @input="(val: string) => handleFieldChange($index, 'remark', val)"
              />
            </template>
            <span v-else>{{ filteredEntries[$index].remark || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="操作" width="65" align="center" fixed="right">
          <template #default="{ $index }">
            <el-button text type="danger" size="small" @click="handleRemoveEntry($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- ═══ 新增分录按钮 ═══ -->
      <div v-if="!isReadonly" class="add-entry-bar">
        <el-button size="small" @click="handleAddEntry">+ 新增{{ activeType }}分录</el-button>
      </div>

      <!-- ═══ AJE/RJE 净影响（科目1811递延所得税资产） ═══ -->
      <div class="net-impact-section">
        <div class="net-impact-row">
          <span class="net-impact-label">AJE 净影响（科目1811递延所得税资产）：</span>
          <span class="net-impact-value">{{ fmtAmt(ajeNetAmount) }}</span>
        </div>
        <div class="net-impact-row">
          <span class="net-impact-label">RJE 净影响（科目1811递延所得税资产）：</span>
          <span class="net-impact-value">{{ fmtAmt(rjeNetAmount) }}</span>
        </div>
        <div class="net-impact-hint">
          * 净影响自动同步至 N1-1 审定表对应 AJE/RJE 列（借方-贷方，资产类借增贷减）
        </div>
      </div>

      <!-- ═══ 编制提示（折叠） ═══ -->
      <details class="n1-details-tip">
        <summary>编制提示</summary>
        <ul>
          <li><strong>借贷平衡</strong>：每笔调整分录必须保持借方合计 = 贷方合计，差额≤0.01元视为平衡</li>
          <li><strong>AJE</strong>：审计调整分录，影响审定数（改变报表金额）</li>
          <li><strong>RJE</strong>：重分类调整分录，不改变损益合计，仅调整列报位置</li>
          <li><strong>资产类特点</strong>：借方增加（确认递延所得税资产），贷方减少（转回递延所得税资产）</li>
          <li><strong>科目1811</strong>：递延所得税资产——可抵扣暂时性差异×适用税率</li>
          <li><strong>净影响</strong>：统计科目名称含"递延所得税资产"的分录行的净增减（借方-贷方）</li>
          <li><strong>A13联动</strong>：保存并发布后通知 A13 审计调整汇总底稿更新</li>
          <li><strong>N1-1同步</strong>：AJE/RJE净影响自动回写N1-1审定表</li>
        </ul>
      </details>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * N1TabAdjustment — N1-3 递延所得税资产调整分录汇总
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/
 * Task: 4.6
 * Requirements: 6.1
 *
 * 核心职责：
 * - 10列（A~J from xlsx）：调整事项说明/类别/报表项目/科目名称/附注项目/借方/贷方/索引/备注
 * - 借贷平衡校验（∑借方===∑贷方，差额≤0.01元视为平衡，不平衡禁止提交+红色高亮）
 * - EventBus publish 'adjustment:created' 通知 A13
 * - 双向同步 N1-1 审定表（AJE/RJE 净影响回写）
 * - 类别下拉选择（报表调整/账项调整/其他）
 * - 科目名称默认预填"递延所得税资产"
 * - AJE/RJE 分Tab切换（el-segmented）
 * - 动态行新增（ElMessageBox.prompt输入名称确认）
 * - 双模式（HTML / OnlyOffice）
 *
 * 科目：1811 递延所得税资产（借方/资产类！）
 * 净影响计算：借方-贷方（资产类借增贷减，与N3负债类相反！）
 */
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare, WarningFilled } from '@element-plus/icons-vue'
import { useN1FormData } from '../../composables/useN1FormData'
import { useN1DualMode } from '../../composables/useN1DualMode'
import { eventBus } from '@/utils/eventBus'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly?: boolean
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReview = inject<((section: string) => void) | undefined>(
  'openReviewDialog',
  undefined,
)

// ─── Composables ─────────────────────────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')

const dualMode = useN1DualMode({ wpId: wpIdRef })
const formData = useN1FormData({ wpId: wpIdRef, projectId: projectIdRef })

// ─── Types ───────────────────────────────────────────────────────────────────

type AdjustmentType = 'AJE' | 'RJE'

interface AdjustmentEntry {
  id: string
  type: AdjustmentType
  description: string      // A: 调整事项说明
  category: string         // B: 类别（报表调整/账项调整/其他）
  reportItem: string       // C: 报表项目
  accountName: string      // D: 科目名称
  noteItem: string         // E: 附注项目
  debitAmount: number      // G: 借方调整金额
  creditAmount: number     // H: 贷方调整金额
  refIndex: string         // I: 索引
  remark: string           // J: 备注
}

interface BalanceState {
  totalDebit: number
  totalCredit: number
  diff: number
  isBalanced: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ACCOUNT_CODE = '1811'
const DEFAULT_ACCOUNT_NAME = '递延所得税资产'

// ─── State ───────────────────────────────────────────────────────────────────

const activeType = ref<AdjustmentType>('AJE')
const entries = ref<AdjustmentEntry[]>([])
const isReadonly = computed(() => props.isReadonly ?? false)

// ─── Tab选项 ─────────────────────────────────────────────────────────────────

const typeOptions = [
  { label: 'AJE 审计调整', value: 'AJE' },
  { label: 'RJE 重分类调整', value: 'RJE' },
]

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreEntries()
})

function _restoreEntries() {
  const stored = formData.allResponses.value.get('N1-3-entries')
  if (stored?.conclusion) {
    try {
      const parsed = JSON.parse(stored.conclusion)
      if (Array.isArray(parsed)) {
        entries.value = parsed
      }
    } catch { /* 空 */ }
  }
}

// ─── Filtered entries ────────────────────────────────────────────────────────

const filteredEntries = computed(() =>
  entries.value.filter(e => e.type === activeType.value),
)

// ─── 借贷平衡校验（∑借方===∑贷方，差额≤0.01元视为平衡） ─────────────────────

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

// ─── 净影响计算（科目名称含"递延所得税资产"行的净增减：借方-贷方，资产类借增贷减） ──

const ajeNetAmount = computed(() => {
  const ajeItems = entries.value.filter(
    e => e.type === 'AJE' && e.accountName.includes('递延所得税资产'),
  )
  // 资产类：借方增加，贷方减少 → 净影响 = 借方 - 贷方
  return ajeItems.reduce((s, e) => s + (e.debitAmount || 0) - (e.creditAmount || 0), 0)
})

const rjeNetAmount = computed(() => {
  const rjeItems = entries.value.filter(
    e => e.type === 'RJE' && e.accountName.includes('递延所得税资产'),
  )
  return rjeItems.reduce((s, e) => s + (e.debitAmount || 0) - (e.creditAmount || 0), 0)
})

// ─── 新增分录（ElMessageBox.prompt输入名称确认） ─────────────────────────────

async function handleAddEntry() {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入调整事项说明',
      `新增${activeType.value}分录`,
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '说明不能为空',
      },
    )
    if (value) {
      entries.value.push({
        id: `adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        type: activeType.value,
        description: value.trim(),
        category: '',
        reportItem: '',
        accountName: DEFAULT_ACCOUNT_NAME,
        noteItem: '',
        debitAmount: 0,
        creditAmount: 0,
        refIndex: '',
        remark: '',
      })
      _autoPersist()
    }
  } catch {
    // 用户取消
  }
}

// ─── 删除分录 ────────────────────────────────────────────────────────────────

async function handleRemoveEntry(filteredIndex: number) {
  const entry = filteredEntries.value[filteredIndex]
  if (!entry) return
  const realIndex = entries.value.findIndex(e => e.id === entry.id)
  if (realIndex === -1) return

  try {
    await ElMessageBox.confirm(
      `确定删除第 ${filteredIndex + 1} 行调整分录？`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    entries.value.splice(realIndex, 1)
    _autoPersist()
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
  _autoPersist()
}

// ─── 自动保存（debounce） ────────────────────────────────────────────────────

function _autoPersist() {
  formData.debouncedSave('N1-3-entries', { conclusion: JSON.stringify(entries.value) })
}

// ─── 保存并发布（核心：借贷平衡校验+EventBus+双向同步N1-1） ─────────────────

async function handleSaveAndPublish() {
  if (!currentBalance.value.isBalanced) {
    ElMessage.error('借贷不平衡，无法提交')
    return
  }

  // 1. 持久化分录数据到 checklist_responses
  await formData.setField('3', 'entries', entries.value)

  // 2. 回写 AJE/RJE 净影响到 N1-1 审定表（双向同步）
  await formData.setField('1', 'aje-net', ajeNetAmount.value)
  await formData.setField('1', 'rje-net', rjeNetAmount.value)

  // 3. EventBus 通知 A13（adjustment:created）
  eventBus.emit('adjustment:created', {
    wpCode: 'N1',
    accountCode: ACCOUNT_CODE,
    ajeAmount: ajeNetAmount.value,
    rjeAmount: rjeNetAmount.value,
    entries: entries.value,
    timestamp: Date.now(),
  })

  ElMessage.success('调整分录已保存并发布')
}

// ─── AI辅助 / 复核 ──────────────────────────────────────────────────────────

function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `n1-adjustment-${section}`,
      prompt: `请基于递延所得税资产底稿"${section}"区段数据，给出审计分析建议`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}

// ─── 格式化金额 ──────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.n1-tab-adjustment {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 双模式切换 ─── */
.n1-mode-bar {
  margin-bottom: 12px;
}

/* ─── Header ─── */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.asset-tag {
  font-size: 11px;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 方法论上下文 ─── */
.n1-methodology-ctx {
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

:deep(.el-input-number) {
  width: 100%;
}

:deep(.el-input-number .el-input__inner) {
  text-align: right;
}

/* ─── 编制提示 ─── */
.n1-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.n1-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n1-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
