<script setup lang="ts">
/**
 * SamplingPreviewDialog — 抽样结果预览编辑弹窗
 *
 * Spec: .kiro/specs/voucher-sampling-engine/
 * Task: 8.1
 *
 * 功能：
 * - el-dialog（width=80vw，max-height=80vh）
 * - 统计卡片（表头上方）：总体笔数/金额 | 已勾选样本笔数/金额 | 笔数覆盖率% | 金额覆盖率%
 * - el-table 列：勾选框 | 凭证号 | 日期 | 摘要 | 借方 | 贷方 | 科目 | 科目名称 | 对方科目 | 凭证类型 | 会计期间 | 核查结果(inline) | 备注(inline)
 * - 默认全部勾选
 * - 金额列格式化
 * - 超100行启用 max-height 虚拟滚动
 * - truncated 时顶部黄色 el-alert
 * - "追加"按钮（搜索框弹出，从序时账搜索追加）— placeholder UI
 * - 底部：填充策略「追加 / 替换本阶段抽凭行」（合并进底稿由宿主的共享回填函数做，ADR-VK-07）+ "确认填充"按钮
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 7.5
 */
import { computed, nextTick, ref, toRaw, watch } from 'vue'
import { Search, Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { amountString, normDate, normText, signedAmount } from '@/utils/voucherIdentity'
import type { SampledVoucher, CoverageStats, FillMode, CheckResult, Phase } from '../composables/useSamplingAlgorithms'

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  visible: boolean
  vouchers: SampledVoucher[]
  coverageStats: CoverageStats | null
  fillMode: FillMode
  selectedCount: number
  selectedDebitTotal: number
  selectedCreditTotal: number
  /** 当前审计阶段，用于手工新增行标注 phase */
  phase?: Phase
  /**
   * 「确认填充」被上游门控阻断的原因（非空 ⇒ 按钮 disabled + tooltip 显示该原因）。
   *
   * 🔴 门控必须**前置**为 disabled，不能等用户勾完样本、点了按钮才弹 warning ——
   * 本弹窗带遮罩，提示里指向的「错报推断与总体结论」区在弹窗背后既看不到也点不到，
   * 那条提示等于死信（2026-08-04 浏览器实测：点确认填充后弹窗不关、四张表全 0 行、
   * 用户无从下手）。缺省 null = 无门控，行为与引入前逐字等价。
   */
  confirmBlockedReason?: string | null
  /**
   * 总体完整性核对未通过的原因（非空 ⇒ 显示就地放行入口）。
   * 缺省 null = 无核对问题 / 旧调用点未传，不显示放行块。
   */
  reconcileIssue?: string | null
  /** 放行说明（双向绑定，与引擎主界面卡片同一份状态） */
  reconcileOverrideReason?: string
  /** 预置放行理由列表 */
  reconcilePresets?: string[]
}

const props = withDefaults(defineProps<Props>(), {
  phase: 'final',
  confirmBlockedReason: null,
  reconcileIssue: null,
  reconcileOverrideReason: '',
  reconcilePresets: () => [],
})

// ─── Emits ────────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'update:fill-mode', v: FillMode): void
  (e: 'update:reconcile-override-reason', v: string): void
  (e: 'confirm'): void
  (e: 'toggle-select-all', v: boolean): void
}>()

// ─── Dialog visibility ────────────────────────────────────────────────────────

const dialogVisible = computed({
  get: () => props.visible,
  set: (v: boolean) => emit('update:visible', v),
})

// ─── Truncated 检测（>=500条） ────────────────────────────────────────────────

const isTruncated = computed(() => props.vouchers.length >= 500)

// ─── 超100行启用虚拟滚动（设置固定高度） ──────────────────────────────────────

const tableHeight = computed(() => {
  return props.vouchers.length > 100 ? 500 : undefined
})

// ─── 凭证分录明细弹窗 ────────────────────────────────────────────────────────
const entryDialogVisible = ref(false)
const entryDialogRow = ref<any>(null)
function showVoucherEntries(row: any) {
  entryDialogRow.value = row
  entryDialogVisible.value = true
}
/** 凭证分录合计行 */
function voucherEntrySummary({ columns, data }: { columns: any[]; data: any[] }) {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    if (col.property === 'debit_amount') {
      const total = data.reduce((s, e) => s + (Number(e.debit_amount) || 0), 0)
      return total > 0 ? total.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) : ''
    }
    if (col.property === 'credit_amount') {
      const total = data.reduce((s, e) => s + (Number(e.credit_amount) || 0), 0)
      return total > 0 ? total.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) : ''
    }
    return ''
  })
}

// ─── 批量填充：核查结果 & 特定选取原因 ────────────────────────────────────────
const batchCheckResult = ref('')
const batchReasonMode = ref<'preset' | 'custom'>('preset')
const batchReasonPreset = ref('')
const batchReasonCustom = ref('')
const REASON_PRESETS = [
  { value: '大额交易', label: '大额交易' },
  { value: '关联方交易', label: '关联方交易' },
  { value: '异常交易', label: '异常交易' },
  { value: '期末突增', label: '期末突增' },
  { value: '跨期交易', label: '跨期交易' },
  { value: '非常规业务', label: '非常规业务' },
  { value: '高值必选', label: '高值必选(MUS)' },
  { value: '随机抽样', label: '随机抽样' },
]

function applyBatchCheckResult() {
  if (!batchCheckResult.value) return
  let count = 0
  for (const v of props.vouchers) {
    if (v.selected && !v.checkResult) {
      v.checkResult = batchCheckResult.value
      count++
    }
  }
  if (count > 0) ElMessage.success(`已为 ${count} 条勾选凭证填入核查结果`)
  else ElMessage.info('所有勾选凭证已有核查结果，未覆盖')
}

function applyBatchReason() {
  const reason = batchReasonMode.value === 'preset' ? batchReasonPreset.value : batchReasonCustom.value.trim()
  if (!reason) {
    ElMessage.warning('请选择或输入选取原因')
    return
  }
  let count = 0
  for (const v of props.vouchers) {
    if (v.selected && !v.selectionReason) {
      v.selectionReason = reason
      count++
    }
  }
  if (count > 0) ElMessage.success(`已为 ${count} 条勾选凭证填入选取原因`)
  else ElMessage.info('所有勾选凭证已有选取原因，未覆盖')
}

// ─── 核查结果选项 ─────────────────────────────────────────────────────────────

const checkResultOptions: { value: CheckResult; label: string }[] = [
  { value: '', label: '（空）' },
  { value: 'Y', label: 'Y' },
  { value: 'N', label: 'N' },
  { value: '异常', label: '异常' },
]

// ─── 追加按钮：人工增补凭证（凭证号 + 日期 + 金额认同一笔）──────────────────────

const appendSearchVisible = ref(false)
const appendForm = ref<{ voucherNo: string; voucherDate: string; debitAmount: string; creditAmount: string; summary: string }>(
  { voucherNo: '', voucherDate: '', debitAmount: '', creditAmount: '', summary: '' },
)

function handleOpenAppendSearch() {
  appendForm.value = { voucherNo: '', voucherDate: '', debitAmount: '', creditAmount: '', summary: '' }
  appendSearchVisible.value = true
}

/**
 * 人工新增勾选一条系统抽样未选中的凭证（R6.2）。
 *
 * 同一笔的认法（任务 9 修正）：凭证号相同，且填了日期 / 金额时日期 / 金额也相同。凭证号单独不唯一
 * （同号别日、同日别凭证字的是别的凭证），以前只按凭证号认，会把别的凭证当成已有行只勾选、不添加。
 * 命中唯一一行 → 只勾选；命中多行 → 请补日期或金额区分；没命中 → 新增。
 */
function handleAppendSearch() {
  const no = appendForm.value.voucherNo.trim()
  if (!no) {
    ElMessage.warning('请填写凭证号')
    return
  }
  const date = normDate(appendForm.value.voucherDate)
  const amount = appendForm.value.debitAmount || appendForm.value.creditAmount
    ? amountString(signedAmount(appendForm.value.debitAmount || 0, appendForm.value.creditAmount || 0).abs())
    : null
  const hits = props.vouchers.filter(v => normText(v.voucherNo) === no
    && (!date || normDate(v.voucherDate) === date)
    && (amount === null || amountString(signedAmount(v.debitAmount, v.creditAmount).abs()) === amount))
  if (hits.length > 1) {
    ElMessage.warning(`凭证号 ${no} 在列表里有 ${hits.length} 笔，请补填日期或金额区分`)
    return
  }
  if (hits.length === 1) {
    hits[0].selected = true
    void syncTableSelection()
    ElMessage.info(`凭证 ${no}（${hits[0].voucherDate || '无日期'}）已在列表里，已为其勾选`)
    appendSearchVisible.value = false
    return
  }
  props.vouchers.push({
    voucherNo: no,
    voucherDate: appendForm.value.voucherDate || '',
    summary: appendForm.value.summary || null,
    debitAmount: appendForm.value.debitAmount ? String(appendForm.value.debitAmount) : null,
    creditAmount: appendForm.value.creditAmount ? String(appendForm.value.creditAmount) : null,
    accountCode: '',
    accountName: null,
    counterpartAccount: null,
    counterpartAccountName: null,
    isMultiAccount: false,
    voucherEntries: [],
    voucherType: null,
    accountingPeriod: null,
    checkResult: '',
    abnormal: false,
    remark: '',
    selected: true,
    phase: props.phase,
    editTrail: [],
  })
  ElMessage.success(`已新增凭证 ${no}`)
  void syncTableSelection()
  appendSearchVisible.value = false
}

/**
 * 人工删除（移出已勾选样本集合）某条凭证（R6.3）。
 */
function handleRemoveRow(row: SampledVoucher) {
  const idx = props.vouchers.indexOf(row)
  if (idx >= 0) props.vouchers.splice(idx, 1)
}

// ─── Methods ──────────────────────────────────────────────────────────────────

// ─── 表格勾选与样本 selected 同步 ─────────────────────────────────────────────
// 样本默认全选（selected = true），但 el-table 的勾选框不读 selected：以前打开时勾选框全空、统计却是全选，
// 不点就确认会填入全部，点一下又只剩这一行。打开 / 增补后按 selected 把表格勾上，同步期间不回写。
const tableRef = ref<{ clearSelection: () => void; toggleRowSelection: (row: unknown, selected?: boolean) => void } | null>(null)
let syncingSelection = false
async function syncTableSelection() {
  await nextTick()
  const table = tableRef.value
  if (!table) return
  const wanted = props.vouchers.filter(v => v.selected)
  syncingSelection = true
  try {
    table.clearSelection()
    for (const v of wanted) table.toggleRowSelection(v, true)
  } finally {
    syncingSelection = false
  }
}
// 表格在 el-dialog 的内容里，弹窗打开后才渲染：等表格实例就位再勾（挂载时它还不在）
watch(tableRef, (table) => { if (table) void syncTableSelection() })
watch(() => props.vouchers, syncTableSelection)

function handleSelectionChange(selection: SampledVoucher[]) {
  if (syncingSelection) return
  // 按行本身认勾选（以前按凭证号：勾一笔会把同号的别的分录、别的凭证一起勾上）；比原始对象，不比响应式代理
  const chosen = new Set(selection.map(v => toRaw(v)))
  props.vouchers.forEach(v => {
    v.selected = chosen.has(toRaw(v))
  })
}

function handleSelectAll(selection: SampledVoucher[]) {
  const allSelected = selection.length === props.vouchers.length
  emit('toggle-select-all', allSelected)
}

/**
 * 金额格式化：千分位显示
 * - null/undefined → "-"
 * - "0" / "0.00" → "-"
 * - 其他 → 千分位格式，保留2位小数
 */
function formatAmount(value: string | null): string {
  if (value == null || value === '') return '-'
  const num = parseFloat(value)
  if (isNaN(num) || num === 0) return '-'
  return num.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

/** 统计金额格式化 */
function formatStatAmount(value: number | string): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(num) || num === 0) return '0.00'
  return num.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function handleFillModeChange(val: FillMode) {
  emit('update:fill-mode', val)
}

/** 确认填充是否被上游门控阻断 */
const isConfirmBlocked = computed(
  () => !!(props.confirmBlockedReason && props.confirmBlockedReason.trim()),
)

function handleConfirm() {
  // 双保险：即便调用方没传 confirmBlockedReason（旧调用点），命中门控也不 emit
  if (isConfirmBlocked.value) return
  emit('confirm')
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="抽样结果预览"
    width="80vw"
    :destroy-on-close="false"
    :close-on-click-modal="false"
    class="sampling-preview-dialog"
  >
    <!-- ═══ 截断警告提示 ═══ -->
    <el-alert
      v-if="isTruncated"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
    >
      <template #title>
        抽样结果已截断，仅显示前500条。建议缩小抽样条件范围或增加过滤约束。
      </template>
    </el-alert>

    <!-- ═══ 统计信息卡片 ═══ -->
    <div class="stats-card">
      <div class="stats-item">
        <span class="stats-label">总体笔数/金额</span>
        <span class="stats-value">
          <strong>{{ coverageStats?.populationCount ?? 0 }}</strong>
          <span class="stats-sub">/ {{ formatStatAmount(coverageStats?.populationAmount ?? '0') }}</span>
        </span>
      </div>
      <div class="stats-divider" />
      <div class="stats-item">
        <span class="stats-label">已勾选样本笔数/金额</span>
        <span class="stats-value">
          <strong>{{ selectedCount }}</strong>
          <span class="stats-sub">/ {{ formatStatAmount(selectedDebitTotal + selectedCreditTotal) }}</span>
        </span>
      </div>
      <div class="stats-divider" />
      <div class="stats-item">
        <span class="stats-label">笔数覆盖率</span>
        <span class="stats-value stats-rate">
          <strong>{{ coverageStats?.countCoverageRate ?? '0.00' }}%</strong>
        </span>
      </div>
      <div class="stats-divider" />
      <div class="stats-item">
        <span class="stats-label">金额覆盖率</span>
        <span class="stats-value stats-rate">
          <strong>{{ coverageStats?.amountCoverageRate ?? '0.00' }}%</strong>
        </span>
      </div>
    </div>

    <!-- ═══ 操作按钮区 ═══ -->
    <div class="action-bar">
      <el-button size="small" type="primary" plain @click="handleOpenAppendSearch">
        + 追加凭证
      </el-button>

      <!-- 批量核查结果 -->
      <div class="batch-group">
        <span class="batch-label">批量核查：</span>
        <el-select v-model="batchCheckResult" size="small" placeholder="选择" clearable style="width: 80px">
          <el-option v-for="opt in checkResultOptions.filter(o => o.value)" :key="opt.value" :value="opt.value" :label="opt.label" />
        </el-select>
        <el-button size="small" type="success" plain :disabled="!batchCheckResult" @click="applyBatchCheckResult">
          填入勾选行
        </el-button>
      </div>

      <!-- 批量选取原因 -->
      <div class="batch-group">
        <span class="batch-label">批量原因：</span>
        <el-radio-group v-model="batchReasonMode" size="small" style="margin-right: 4px">
          <el-radio-button value="preset">预设</el-radio-button>
          <el-radio-button value="custom">自定义</el-radio-button>
        </el-radio-group>
        <el-select v-if="batchReasonMode === 'preset'" v-model="batchReasonPreset" size="small" placeholder="选择原因" clearable style="width: 120px">
          <el-option v-for="opt in REASON_PRESETS" :key="opt.value" :value="opt.value" :label="opt.label" />
        </el-select>
        <el-input v-else v-model="batchReasonCustom" size="small" placeholder="输入原因" clearable style="width: 120px" />
        <el-button size="small" type="success" plain @click="applyBatchReason">
          填入勾选行
        </el-button>
      </div>
    </div>

    <!-- ═══ 凭证表格 ═══ -->
    <el-table
      :data="vouchers"
      :height="tableHeight"
      :max-height="500"
      border
      size="small"
      ref="tableRef"
      class="voucher-table"
      @selection-change="handleSelectionChange"
      @select-all="handleSelectAll"
    >
      <!-- 勾选框列 -->
      <el-table-column type="selection" width="45" align="center" />

      <!-- 凭证号 -->
      <el-table-column prop="voucherNo" label="凭证号" min-width="100" show-overflow-tooltip />

      <!-- 凭证日期 -->
      <el-table-column prop="voucherDate" label="日期" min-width="100" show-overflow-tooltip />

      <!-- 摘要 -->
      <el-table-column prop="summary" label="摘要" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.summary || '-' }}
        </template>
      </el-table-column>

      <!-- 借方金额 -->
      <el-table-column label="借方" min-width="110" align="right">
        <template #default="{ row }">
          {{ formatAmount(row.debitAmount) }}
        </template>
      </el-table-column>

      <!-- 贷方金额 -->
      <el-table-column label="贷方" min-width="110" align="right">
        <template #default="{ row }">
          {{ formatAmount(row.creditAmount) }}
        </template>
      </el-table-column>

      <!-- 科目编码 -->
      <el-table-column prop="accountCode" label="科目" min-width="90" show-overflow-tooltip />

      <!-- 科目名称 -->
      <el-table-column prop="accountName" label="科目名称" min-width="110" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.accountName || '-' }}
        </template>
      </el-table-column>

      <!-- 对方科目 -->
      <el-table-column label="对方科目" min-width="200">
        <template #default="{ row }">
          <template v-if="!row.counterpartAccount || row.counterpartAccount === '-'">-</template>
          <template v-else-if="!row.isMultiAccount">
            <span>{{ row.counterpartAccount }}</span>
            <span v-if="row.counterpartAccountName" style="color: var(--el-text-color-secondary); margin-left: 4px">{{ row.counterpartAccountName }}</span>
          </template>
          <span v-else-if="row.voucherEntriesOmitted" :title="`整张凭证 ${row.voucherLineCount ?? ''} 行分录，超过展示上限，请在序时账查看`">
            多科目（分录过多，请在序时账查看）
          </span>
          <template v-else>
            <el-button size="small" link type="primary" @click="showVoucherEntries(row)">多科目 (点击查看分录)</el-button>
          </template>
        </template>
      </el-table-column>

      <!-- 凭证类型 -->
      <el-table-column prop="voucherType" label="凭证类型" width="80" align="center">
        <template #default="{ row }">
          {{ row.voucherType || '-' }}
        </template>
      </el-table-column>

      <!-- 会计期间 -->
      <el-table-column prop="accountingPeriod" label="会计期间" width="80" align="center">
        <template #default="{ row }">
          {{ row.accountingPeriod != null ? `${row.accountingPeriod}月` : '-' }}
        </template>
      </el-table-column>

      <!-- 核查结果（inline 编辑） -->
      <el-table-column label="核查结果" width="100" align="center">
        <template #default="{ row }">
          <el-select
            v-model="row.checkResult"
            size="small"
            placeholder="选择"
            clearable
            style="width: 80px"
          >
            <el-option
              v-for="opt in checkResultOptions"
              :key="opt.value"
              :value="opt.value"
              :label="opt.label"
            />
          </el-select>
        </template>
      </el-table-column>

      <!-- 高值必选标识（MUS，R17.4） -->
      <el-table-column label="高值" width="70" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.isHighValue" size="small" type="danger" effect="plain">
            高值必选
          </el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>

      <!-- 特定选取原因（inline 编辑：下拉预设 + 自定义输入，R6.5） -->
      <el-table-column label="特定选取原因" min-width="160">
        <template #default="{ row }">
          <el-select
            v-model="row.selectionReason"
            size="small"
            placeholder="选择或输入"
            clearable
            filterable
            allow-create
            default-first-option
            style="width: 100%"
          >
            <el-option v-for="opt in REASON_PRESETS" :key="opt.value" :value="opt.value" :label="opt.label" />
          </el-select>
        </template>
      </el-table-column>

      <!-- 备注（inline 编辑） -->
      <el-table-column label="备注" min-width="140">
        <template #default="{ row }">
          <el-input
            v-model="row.remark"
            size="small"
            placeholder="输入备注"
            clearable
          />
        </template>
      </el-table-column>

      <!-- 操作：人工删除（移出样本，R6.3） -->
      <el-table-column label="操作" width="70" align="center">
        <template #default="{ row }">
          <el-button
            type="danger"
            :icon="Delete"
            circle
            size="small"
            plain
            @click="handleRemoveRow(row)"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 总体完整性校验——就地放行（R3.1）═══ -->
    <div v-if="reconcileIssue" class="reconcile-override-inline" data-testid="preview-reconcile-override">
      <div class="reconcile-override-head">
        <el-tag type="danger" size="small" effect="dark">总体完整性核对</el-tag>
        <span class="reconcile-override-text">{{ reconcileIssue }}</span>
      </div>
      <el-input
        :model-value="reconcileOverrideReason"
        type="textarea"
        :autosize="{ minRows: 2 }"
        maxlength="500"
        show-word-limit
        placeholder="如确有正当理由，请说明不少于 10 字后继续；该说明将随抽样评价留痕"
        data-testid="preview-reconcile-reason"
        @update:model-value="(v: string) => emit('update:reconcile-override-reason', v)"
      />
      <div v-if="reconcilePresets.length > 0 && !(reconcileOverrideReason || '').trim()" class="reconcile-presets">
        <el-button
          v-for="preset in reconcilePresets"
          :key="preset"
          size="small"
          text
          type="primary"
          @click="emit('update:reconcile-override-reason', preset)"
        >
          {{ preset }}
        </el-button>
      </div>
      <div class="reconcile-override-foot">
        <el-tag
          :type="(reconcileOverrideReason || '').trim().length >= 10 ? 'success' : 'info'"
          size="small"
          effect="plain"
        >
          {{
            (reconcileOverrideReason || '').trim().length >= 10
              ? '已填写放行理由，可继续确认填充'
              : `还需 ${10 - (reconcileOverrideReason || '').trim().length} 字`
          }}
        </el-tag>
      </div>
    </div>

    <!-- ═══ 底部操作区 ═══ -->
    <div class="dialog-footer">
      <div class="fill-mode-section">
        <span class="fill-mode-label">填充策略：</span>
        <el-radio-group :model-value="fillMode === 'replace' ? 'replace' : 'append'" @change="handleFillModeChange">
          <el-tooltip content="已在底稿里的分录不重复填入，保留原行的核对内容" placement="top">
            <el-radio value="append">追加</el-radio>
          </el-tooltip>
          <el-tooltip
            content="只删除本阶段由抽凭填入的行，预审阶段的行、手工行与挂凭行不动；已填核对内容的行删除前先确认"
            placement="top"
          >
            <el-radio value="replace" data-testid="fill-mode-replace">替换本阶段抽凭行</el-radio>
          </el-tooltip>
        </el-radio-group>
      </div>
      <el-tooltip
        :disabled="!isConfirmBlocked"
        :content="confirmBlockedReason || ''"
        placement="top"
      >
        <!-- disabled 按钮不触发鼠标事件 → 必须套一层 span 才有 tooltip 宿主 -->
        <span class="confirm-fill-wrap">
          <el-button
            type="primary"
            :disabled="isConfirmBlocked"
            data-testid="sampling-preview-confirm"
            @click="handleConfirm"
          >
            确认填充
          </el-button>
        </span>
      </el-tooltip>
    </div>

    <!-- ═══ 人工增补凭证弹窗 ═══ -->
    <el-dialog
      v-model="appendSearchVisible"
      title="人工增补凭证"
      width="500px"
      append-to-body
      :close-on-click-modal="false"
    >
      <div class="append-search-content">
        <el-form label-width="80px" size="small">
          <el-form-item label="凭证号" required>
            <el-input v-model="appendForm.voucherNo" placeholder="必填，如 记-0123" clearable>
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </el-form-item>
          <el-form-item label="日期">
            <el-input v-model="appendForm.voucherDate" placeholder="如 2025-12-31" clearable />
          </el-form-item>
          <el-form-item label="借方金额">
            <el-input v-model="appendForm.debitAmount" placeholder="选填（元）" clearable />
          </el-form-item>
          <el-form-item label="贷方金额">
            <el-input v-model="appendForm.creditAmount" placeholder="选填（元）" clearable />
          </el-form-item>
          <el-form-item label="摘要">
            <el-input v-model="appendForm.summary" placeholder="选填" clearable />
          </el-form-item>
        </el-form>
        <div class="append-hint">
          手工增补的凭证将默认勾选并纳入样本；凭证号、日期、金额都相同的视为同一笔，已在列表里的只勾选。
        </div>
      </div>
      <template #footer>
        <el-button @click="appendSearchVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAppendSearch">确认追加</el-button>
      </template>
    </el-dialog>

    <!-- ═══ 凭证完整分录明细弹窗（可拖拽）═══ -->
    <el-dialog
      v-model="entryDialogVisible"
      :title="`凭证 ${entryDialogRow?.voucherNo || ''} 完整分录`"
      width="680px"
      append-to-body
      draggable
      :close-on-click-modal="true"
      class="voucher-entry-dialog"
    >
      <div v-if="entryDialogRow" style="font-size: 13px">
        <div style="display: flex; gap: 24px; margin-bottom: 12px; color: var(--el-text-color-secondary); font-size: 12px">
          <span>日期：{{ entryDialogRow.voucherDate }}</span>
          <span>凭证号：{{ entryDialogRow.voucherNo }}</span>
          <span>摘要：{{ entryDialogRow.summary || '-' }}</span>
        </div>
        <el-table
          :data="entryDialogRow.voucherEntries || []"
          border
          size="small"
          style="width: 100%"
          :max-height="400"
          show-summary
          :summary-method="voucherEntrySummary"
        >
          <el-table-column prop="account_code" label="科目代码" min-width="110" />
          <el-table-column prop="account_name" label="科目名称" min-width="160" show-overflow-tooltip />
          <el-table-column prop="debit_amount" label="借方" width="130" align="right">
            <template #default="{ row: e }">
              <span v-if="e.debit_amount && Number(e.debit_amount) > 0" style="color: var(--el-color-danger)">
                {{ Number(e.debit_amount).toLocaleString('zh-CN', { minimumFractionDigits: 2 }) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="credit_amount" label="贷方" width="130" align="right">
            <template #default="{ row: e }">
              <span v-if="e.credit_amount && Number(e.credit_amount) > 0" style="color: var(--el-color-primary)">
                {{ Number(e.credit_amount).toLocaleString('zh-CN', { minimumFractionDigits: 2 }) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="summary" label="摘要" min-width="180" show-overflow-tooltip />
        </el-table>
      </div>
    </el-dialog>
  </el-dialog>
</template>

<style scoped>
.sampling-preview-dialog :deep(.el-dialog__body) {
  max-height: 80vh;
  overflow-y: auto;
  padding: 16px 20px;
}

/* ── 统计信息卡片 ── */
.stats-card {
  display: flex;
  align-items: center;
  gap: 0;
  padding: 10px 16px;
  margin-bottom: 12px;
  background: #f5f7fa;
  border-radius: 4px;
  border: 1px solid #e4e7ed;
}

.stats-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  gap: 2px;
}

.stats-label {
  font-size: 12px;
  color: #909399;
}

.stats-value {
  font-size: 14px;
  color: #303133;
}

.stats-value strong {
  font-size: 16px;
}

.stats-sub {
  font-size: 12px;
  color: #909399;
  margin-left: 4px;
}

.stats-rate strong {
  color: #409eff;
}

.stats-divider {
  width: 1px;
  height: 32px;
  background: #dcdfe6;
  margin: 0 8px;
}

/* ── 操作按钮区 ── */
.action-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  margin-bottom: 8px;
  gap: 12px;
  flex-wrap: wrap;
}

.batch-group {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}

.batch-label {
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

/* ── 表格样式 ── */
.voucher-table {
  font-size: var(--wp-font-size, 13px);
}

.voucher-table :deep(.el-table__row) {
  font-size: var(--wp-font-size, 13px);
}

.voucher-table :deep(.el-table__header th) {
  font-size: var(--wp-font-size, 13px);
}

/* ── 总体完整性校验：就地放行（与引擎主界面同款视觉，scoped 样式不跨组件，须各写一份）── */
.reconcile-override-inline {
  margin-top: 12px;
  padding: 10px 12px;
  border-left: 3px solid var(--el-color-danger);
  background: var(--el-color-danger-light-9);
  border-radius: 4px;
}

.reconcile-override-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.reconcile-override-text {
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.reconcile-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}

.reconcile-override-foot {
  margin-top: 6px;
}

/* ── 底部操作区 ── */
.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #ebeef5;
}

.fill-mode-section {
  display: flex;
  align-items: center;
  gap: 8px;
}

.fill-mode-label {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  white-space: nowrap;
}

/* ── 人工增补弹窗 ── */
.append-search-content {
  min-height: 200px;
}

.append-hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  margin-top: 8px;
  line-height: 1.5;
}

/* ── 表格内输入框优化 ── */
.voucher-table :deep(.el-input__inner) {
  font-size: var(--wp-font-size, 13px);
}

.voucher-table :deep(.el-select .el-input__inner) {
  font-size: var(--wp-font-size, 13px);
}

/* ── 凭证分录弹窗 ── */
.voucher-entry-dialog :deep(.el-dialog__body) {
  padding: 12px 20px 20px;
}
</style>
