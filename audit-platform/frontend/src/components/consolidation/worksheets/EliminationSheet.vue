<template>
  <!--
    合并抵消分录明细表（spec consol-elimination-single-source-push 任务 10 / 需求 1~2）
    唯一来源 = elimination_entries：列出本企业树全部未删分录的明细行（含下级合并项目承载的，只读），
    新增 / 修改与差额节点面板同一表单（ConsolElimEntryForm，归属节点下拉）；按状态提交审批 / 审批 / 驳回 / 撤销审批 / 删除。
    工作底稿（模拟权益法 / 内部往来 / 内部交易）的计算结果在「待生成」区预演，点「生成草稿分录」才写成草稿；
    旧版自定义行（consol_worksheet_data['elimination']）只提示与转入，不再参与任何计算。
  -->
  <div ref="sheetRef" class="ws-sheet" :class="{ 'gt-fullscreen': isFullscreen }" data-testid="elim-sheet">
    <div class="ws-sheet-header">
      <h3>合并抵消分录明细表</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏查看'" placement="top">
          <el-button size="small" @click="toggleFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
        <el-button size="small" @click="emit('open-formula', 'consol_elimination')">ƒx 公式</el-button>
        <el-button size="small" :disabled="!rows.length" @click="exportSheet">📤 导出</el-button>
        <el-button size="small" :loading="loading" data-testid="elim-sheet-refresh" @click="reload">🔄 刷新</el-button>
        <el-button size="small" type="primary" :disabled="!hostedNodes.length" data-testid="elim-sheet-new"
          @click="openCreate">+ 新增分录</el-button>
      </div>
    </div>

    <el-alert v-if="legacy && legacy.custom_row_count > 0" type="warning" :closable="false" show-icon
      class="elim-legacy" data-testid="elim-legacy-banner">
      <template #title>
        <span>{{ legacy.message }}。</span>
        <span v-if="legacy.pending > 0">可转为草稿分录（共 {{ legacy.group_count }} 组，按借贷平衡处切分），审批后计入合并数。</span>
        <span v-else>已全部转为草稿分录。</span>
        <el-button v-if="legacy.pending > 0" size="small" type="warning" link :loading="converting"
          data-testid="elim-legacy-convert" @click="convertLegacy">转为草稿分录</el-button>
        <el-button size="small" link @click="legacyDetailVisible = !legacyDetailVisible">
          {{ legacyDetailVisible ? '收起明细' : '查看明细' }}
        </el-button>
      </template>
      <ul v-if="legacyDetailVisible" class="elim-legacy-list" data-testid="elim-legacy-list">
        <li v-for="g in legacy.groups" :key="g.origin_key">
          <el-tag size="small" :type="actionTagType(g.action)">{{ actionLabel(g.action, !g.entry_id) }}</el-tag>
          {{ g.description }}（借 {{ fmt(g.debit_total) }} / 贷 {{ fmt(g.credit_total) }}）
          <span v-for="(r, i) in g.reasons" :key="i" class="elim-reason">{{ r }}</span>
        </li>
      </ul>
    </el-alert>

    <div class="ws-tip" v-show="!isFullscreen">
      <span>分录只有一个来源：这里与企业树「差额节点」面板是同一批分录，<b>审批后才计入合并数</b>，并自动推送到合并试算、合并报表与附注。
        工作底稿算出的抵销先在下方「待生成」预览，确认后生成草稿分录；来源数据变化后再次生成会更新草稿，已提交审批的不改。</span>
    </div>

    <el-table v-loading="loading" :data="rows" border size="small" class="ws-table" data-testid="elim-sheet-table"
      :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
      :max-height="isFullscreen ? 'calc(100vh - 160px)' : 'calc(100vh - 380px)'"
      :span-method="spanMethod" :row-class-name="rowClass" empty-text="暂无分录">
      <el-table-column label="编号" width="110" fixed>
        <template #default="{ row }">
          <span :data-testid="`elim-row-${row.entry_no}`">{{ row.entry_no }}</span>
        </template>
      </el-table-column>
      <el-table-column label="来源" width="96" align="center">
        <template #default="{ row }">
          <el-tag size="small" effect="plain" :type="row.origin ? 'success' : 'info'">{{ row.origin_label }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="归属节点" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.node_label">{{ row.node_label }}</span>
          <el-tooltip v-else-if="row.orphan_reason" :content="row.orphan_reason" placement="top">
            <span class="elim-orphan">未归属</span>
          </el-tooltip>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="110">
        <template #default="{ row }">{{ row.entry_type_label }}</template>
      </el-table-column>
      <el-table-column label="科目" min-width="170" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.account_code">{{ row.account_code }} {{ row.account_name || '' }}</span>
          <span v-else class="elim-orphan">明细无法识别</span>
        </template>
      </el-table-column>
      <el-table-column label="借方" width="130" align="right">
        <template #default="{ row }"><GtAmountCell :value="row.debit" /></template>
      </el-table-column>
      <el-table-column label="贷方" width="130" align="right">
        <template #default="{ row }"><GtAmountCell :value="row.credit" /></template>
      </el-table-column>
      <el-table-column label="说明" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">{{ row.description || '' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="84" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="statusTagType(row.review_status)" :data-testid="`elim-sheet-status-${row.entry_no}`">
            {{ row.review_status_label }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="计入" width="60" align="center">
        <template #default="{ row }">
          <span :class="row.counted ? 'elim-counted' : 'elim-not-counted'">{{ row.counted ? '是' : '否' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <template v-if="row.readonly">
            <span class="elim-host">由「{{ row.host_project_name || '其他合并项目' }}」承载</span>
            <el-button size="small" link type="primary" :data-testid="`elim-sheet-goto-${row.entry_no}`"
              @click="goHost(row)">前往</el-button>
          </template>
          <template v-else>
            <el-button v-if="canEdit(row)" size="small" link type="primary" @click="openEdit(row)">修改</el-button>
            <el-button v-if="canSubmit(row)" size="small" link type="primary" :data-testid="`elim-sheet-submit-${row.entry_no}`"
              @click="act(row, 'submit')">提交审批</el-button>
            <el-button v-if="canApprove(row)" size="small" link type="success" :data-testid="`elim-sheet-approve-${row.entry_no}`"
              @click="act(row, 'approve')">审批</el-button>
            <el-button v-if="canApprove(row)" size="small" link type="warning" @click="rejectEntry(row)">驳回</el-button>
            <el-button v-if="canRevoke(row)" size="small" link type="warning" :data-testid="`elim-sheet-revoke-${row.entry_no}`"
              @click="revokeEntry(row)">撤销审批</el-button>
            <el-button v-if="canEdit(row)" size="small" link type="danger" :data-testid="`elim-sheet-delete-${row.entry_no}`"
              @click="removeEntry(row)">删除</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计三行：全部分录 / 已审批 / 实际计入合并数（已审批且归属成功） -->
    <div class="ws-balance-check" data-testid="elim-sheet-totals">
      <div v-for="t in totalRows" :key="t.key" class="elim-total-row" :data-testid="`elim-total-${t.key}`">
        <span class="elim-total-label">{{ t.label }}（{{ t.value.entry_count }} 笔）</span>
        <span>借方 <b class="ws-computed">{{ fmt(t.value.debit) }}</b></span>
        <span>贷方 <b class="ws-computed">{{ fmt(t.value.credit) }}</b></span>
        <span :class="isZeroAmount(t.value.difference) ? '' : 'ws-diff-warn'">
          差额 {{ fmt(t.value.difference) }}
          <span v-if="isZeroAmount(t.value.difference)" class="elim-balanced">✓ 平衡</span>
          <span v-else class="elim-unbalanced">⚠ 不平衡</span>
        </span>
      </div>
    </div>

    <!-- 待生成：工作底稿计算结果的预演（不写库） -->
    <div class="ws-section elim-pending" data-testid="elim-pending">
      <div class="ws-section-title elim-pending-title">
        <span>待生成（来自
          <a class="ws-link" @click="emit('goto-sheet', 'equity_sim')">模拟权益法</a>、
          <a class="ws-link" @click="emit('goto-sheet', 'internal_arap')">内部往来</a>、
          <a class="ws-link" @click="emit('goto-sheet', 'internal_trade')">内部交易</a>）</span>
        <span style="flex:1" />
        <el-button size="small" :loading="previewing" data-testid="elim-pending-preview" @click="preview">重新预览</el-button>
        <el-button size="small" type="primary" :loading="generating" :disabled="!summary.actionable"
          data-testid="elim-pending-generate" @click="generate">生成草稿分录</el-button>
      </div>
      <p class="elim-pending-summary" data-testid="elim-pending-summary">{{ previewError || summaryText }}</p>
      <p v-if="missingOriginsText" class="elim-pending-summary elim-warn-text" data-testid="elim-pending-missing">
        {{ missingOriginsText }}
      </p>
      <el-alert v-for="(w, i) in previewWarnings" :key="`w${i}`" type="warning" :closable="false" :title="w"
        class="elim-pending-warning" />
      <el-table v-if="pendingRows.length" :data="pendingRows" border size="small" class="ws-table" max-height="320"
        :span-method="pendingSpan" data-testid="elim-pending-table">
        <el-table-column label="来源" width="96" align="center">
          <template #default="{ row }">{{ row.group.origin_label }}</template>
        </el-table-column>
        <el-table-column label="说明" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.group.description }}</template>
        </el-table-column>
        <el-table-column label="结果" width="130" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="actionTagType(row.group.action)" :data-testid="`elim-pending-action-${row.groupIndex}`">
              {{ actionLabel(row.group.action, true) }}
            </el-tag>
            <div v-if="row.group.entry_no" class="elim-pending-entry">{{ row.group.entry_no }}</div>
          </template>
        </el-table-column>
        <el-table-column label="来源科目" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.line ? lineLabel(row.line) : '—' }}</template>
        </el-table-column>
        <el-table-column label="入账科目" min-width="170">
          <template #default="{ row }">
            <template v-if="row.line">
              <span v-if="row.line.account_code" :class="{ 'elim-warn-text': !row.line.in_report }">
                {{ row.line.account_code }} {{ row.line.account_name || '' }}
              </span>
              <span v-else class="elim-bad-text">未映射</span>
              <div v-if="row.line.reason" class="elim-bad-text elim-small">{{ row.line.reason }}</div>
              <div v-else-if="row.line.warning" class="elim-warn-text elim-small">{{ row.line.warning }}</div>
              <div v-else-if="row.line.note" class="elim-small">{{ row.line.note }}</div>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="借方" width="120" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.line?.direction === 'debit' ? row.line.amount : null" /></template>
        </el-table-column>
        <el-table-column label="贷方" width="120" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.line?.direction === 'credit' ? row.line.amount : null" /></template>
        </el-table-column>
        <el-table-column label="原因" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="elim-bad-text">{{ groupReasons(row.group).join('；') }}</span>
          </template>
        </el-table-column>
      </el-table>
      <ul v-if="reviewNotes.length" class="elim-review-notes" data-testid="elim-pending-review-notes">
        <li v-for="n in reviewNotes" :key="n.entry_id">{{ n.entry_no }}：{{ n.reason }}</li>
      </ul>
    </div>

    <ConsolElimEntryForm
      v-model="formVisible"
      :project-id="projectId"
      :year="year"
      :targets="hostedNodes"
      :accounts="accounts"
      :entry="editingEntry"
      @saved="onSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import ConsolElimEntryForm from '@/components/consolidation/ConsolElimEntryForm.vue'
import { useFullscreen } from '@/composables/useFullscreen'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { exportData } from '@/composables/useExcelIO'
import { confirmDangerous, confirmDelete, promptRejectReason } from '@/utils/confirm'
import {
  convertLegacyEliminationSheet,
  deleteElimination,
  generateEliminationsFromWorksheet,
  getEliminationTreeLines,
  getLegacyEliminationSheet,
  getWorksheetAccounts,
  reviewElimination,
  type ConsolAccountOption,
  type ElimHostedNode,
  type ElimLineTotals,
  type ElimTreeLine,
  type EliminationEntry,
  type GenerateFromWorksheetResult,
  type GenerateGroupResult,
  type GeneratePlannedLine,
  type LegacySheetResult,
  type WorksheetOrigin,
  type WorksheetSourceGroup,
} from '@/services/consolidationApi'
import {
  canApprove,
  canEdit,
  canRevoke,
  canSubmit,
  statusTagType,
} from '@/components/consolidation/composables/elimNodePanel'
import {
  actionLabel,
  actionTagType,
  deletionConfirmText,
  entryFromLines,
  entrySpan,
  EXPORT_COLUMNS,
  exportRows,
  generateResultText,
  groupReasons,
  linesOfEntry,
  pendingSummary,
  pendingSummaryText,
} from '@/components/consolidation/composables/elimSheet'
import { WORKSHEET_ORIGINS } from '@/components/consolidation/composables/elimSourceGroups'

defineOptions({ name: 'EliminationSheet' })

const props = withDefaults(defineProps<{
  projectId: string
  year: number | null
  /** 工作底稿来源分组（ConsolWorksheetTabs 按模拟权益法 / 内部往来 / 内部交易算出） */
  sourceGroups?: ReadonlyArray<WorksheetSourceGroup>
  /**
   * 本次负责的来源（其数据已知：已保存或本次打开过）。只有这些来源里不再产出的来源键才删除草稿 ——
   * 某张表的数据本次没加载，就不能当成「它算出来是空的」去删它以前生成的草稿。
   */
  sourceOrigins?: ReadonlyArray<WorksheetOrigin>
}>(), {
  sourceGroups: () => [],
  sourceOrigins: () => [...WORKSHEET_ORIGINS],
})
const emit = defineEmits<{
  (e: 'open-formula', key: string): void
  (e: 'goto-sheet', key: string): void
  /** 分录有增删改或状态变化（父组件可据此刷新依赖合并数的视图） */
  (e: 'changed'): void
}>()

const router = useRouter()
const { isFullscreen, toggleFullscreen } = useFullscreen()
const displayPrefs = useDisplayPrefsStore()
const fmt = (v: unknown) => displayPrefs.fmt(v)
const sheetRef = ref<HTMLElement | null>(null)

// ─── 明细行 ──────────────────────────────────────────────────────────────────
const loading = ref(false)
const rows = ref<ElimTreeLine[]>([])
const hostedNodes = ref<ElimHostedNode[]>([])
const accounts = ref<ConsolAccountOption[]>([])
const EMPTY_TOTALS: ElimLineTotals = { debit: '0.00', credit: '0.00', difference: '0.00', entry_count: 0 }
const totals = ref<{ all: ElimLineTotals; approved: ElimLineTotals; counted: ElimLineTotals }>({
  all: EMPTY_TOTALS, approved: EMPTY_TOTALS, counted: EMPTY_TOTALS,
})
const totalRows = computed(() => [
  { key: 'all', label: '全部分录', value: totals.value.all },
  { key: 'approved', label: '已审批', value: totals.value.approved },
  { key: 'counted', label: '计入合并数', value: totals.value.counted },
])

function isZeroAmount(v: string | null | undefined): boolean {
  return !v || /^-?0+(\.0+)?$/.test(String(v).trim())
}

async function loadLines() {
  if (!props.projectId) return
  loading.value = true
  try {
    const res = await getEliminationTreeLines(props.projectId, props.year)
    rows.value = res?.rows || []
    hostedNodes.value = res?.hosted_nodes || []
    totals.value = res?.totals || { all: EMPTY_TOTALS, approved: EMPTY_TOTALS, counted: EMPTY_TOTALS }
  } catch {
    rows.value = []
    hostedNodes.value = []
  } finally {
    loading.value = false
  }
}

async function loadAccounts() {
  try {
    const res = await getWorksheetAccounts(props.projectId, props.year)
    accounts.value = res?.accounts || []
  } catch {
    accounts.value = []
  }
}

async function loadLegacy() {
  try {
    legacy.value = await getLegacyEliminationSheet(props.projectId, props.year)
  } catch {
    legacy.value = null
  }
}

async function reload() {
  await Promise.all([loadLines(), preview(), loadLegacy()])
}

/** 分录有变化：刷新明细与预演（来源键对应的分录状态变了，预演结果也随之变） */
async function afterChange() {
  await Promise.all([loadLines(), preview()])
  emit('changed')
}

function spanMethod({ row, column }: { row: ElimTreeLine; column: { label?: string } }) {
  // 科目、借方、贷方逐行显示；其余是分录级信息，跨该分录的明细行合并
  if (['科目', '借方', '贷方'].includes(column.label || '')) return { rowspan: 1, colspan: 1 }
  return entrySpan(row)
}

function rowClass({ row }: { row: ElimTreeLine }) {
  if (row.readonly) return 'elim-row-readonly'
  return row.counted ? '' : 'elim-row-uncounted'
}

// ─── 新增 / 修改（与差额节点面板同一表单）────────────────────────────────────
const formVisible = ref(false)
const editingEntry = ref<EliminationEntry | null>(null)
let accountsFor = ''

function ensureAccounts() {
  const scope = `${props.projectId}:${props.year ?? ''}`
  if (accountsFor === scope) return
  accountsFor = scope
  loadAccounts()
}

function openCreate() {
  editingEntry.value = null
  ensureAccounts()
  formVisible.value = true
}

function openEdit(row: ElimTreeLine) {
  editingEntry.value = entryFromLines(linesOfEntry(rows.value, row.entry_id), props.year)
  ensureAccounts()
  formVisible.value = true
}

async function onSaved() {
  await afterChange()
}

// ─── 状态操作（规则与差额节点面板一致）──────────────────────────────────────
async function act(row: ElimTreeLine, action: 'submit' | 'approve') {
  try {
    await reviewElimination(row.entry_id, props.projectId, { action })
    ElMessage.success(action === 'submit' ? '已提交审批' : '已审批，合并试算、报表与附注将自动推送')
    await afterChange()
  } catch {
    /* 由 http 拦截器提示（如归属节点已不在企业树中） */
  }
}

async function rejectEntry(row: ElimTreeLine) {
  let reason = ''
  try {
    reason = await promptRejectReason(`分录 ${row.entry_no}`)
  } catch {
    return
  }
  try {
    await reviewElimination(row.entry_id, props.projectId, { action: 'reject', rejection_reason: reason || undefined })
    ElMessage.success('已驳回')
    await afterChange()
  } catch {
    /* 由 http 拦截器提示 */
  }
}

async function revokeEntry(row: ElimTreeLine) {
  try {
    await confirmDangerous({
      title: '撤销审批',
      message: `撤销分录 ${row.entry_no} 的审批？撤销后分录回到草稿，合并试算、报表与附注将重新推送。`,
      confirmText: '撤销审批',
    })
  } catch {
    return
  }
  try {
    await reviewElimination(row.entry_id, props.projectId, { action: 'revoke' })
    ElMessage.success('已撤销审批，合并数将自动重算')
    await afterChange()
  } catch {
    /* 由 http 拦截器提示（如合并已锁定） */
  }
}

async function removeEntry(row: ElimTreeLine) {
  try {
    await confirmDelete(`分录 ${row.entry_no}`)
  } catch {
    return
  }
  try {
    await deleteElimination(row.entry_id, props.projectId)
    ElMessage.success('分录已删除')
    await afterChange()
  } catch {
    /* 由 http 拦截器提示 */
  }
}

function goHost(row: ElimTreeLine) {
  router.push({
    path: `/projects/${row.host_project_id}/consolidation`,
    query: props.year ? { year: String(props.year) } : undefined,
  })
}

// ─── 待生成：预演与生成 ──────────────────────────────────────────────────────
const previewing = ref(false)
const generating = ref(false)
const previewResult = ref<GenerateFromWorksheetResult | null>(null)
const previewError = ref('')
const summary = computed(() => pendingSummary(previewResult.value))
const summaryText = computed(() => pendingSummaryText(summary.value))
const previewWarnings = computed(() => previewResult.value?.warnings || [])
const reviewNotes = computed(() => previewResult.value?.changed_after_review || [])

interface PendingRow {
  group: GenerateGroupResult
  groupIndex: number
  line: GeneratePlannedLine | null
  first: boolean
  span: number
}

/** 预演结果展开为行（每组的来源行各一行；分组级列跨行合并）；无变化与无金额的组不占行 */
const pendingRows = computed<PendingRow[]>(() => {
  const out: PendingRow[] = []
  ;(previewResult.value?.groups || []).forEach((group, groupIndex) => {
    if (group.action === 'unchanged' || group.action === 'empty') return
    const lines = group.lines.length ? group.lines : [null]
    lines.forEach((line, i) => out.push({ group, groupIndex, line, first: i === 0, span: lines.length }))
  })
  return out
})

const GROUP_COLUMNS = new Set(['来源', '说明', '结果', '原因'])

function pendingSpan({ row, column }: { row: PendingRow; column: { label?: string } }) {
  if (!GROUP_COLUMNS.has(column.label || '')) return { rowspan: 1, colspan: 1 }
  return row.first ? { rowspan: row.span, colspan: 1 } : { rowspan: 0, colspan: 0 }
}

function lineLabel(line: GeneratePlannedLine): string {
  return line.detail ? `${line.subject}-${line.detail}` : line.subject
}

const ORIGIN_NAMES: Record<WorksheetOrigin, string> = {
  ws_equity_sim: '模拟权益法',
  ws_internal_arap: '内部往来',
  ws_internal_trade: '内部交易',
}

/** 本次没纳入的来源（数据未加载）：提示用户，其已生成的草稿本次不动 */
const missingOriginsText = computed(() => {
  const names = WORKSHEET_ORIGINS.filter((o) => !props.sourceOrigins.includes(o)).map((o) => ORIGIN_NAMES[o])
  return names.length
    ? `${names.join('、')}表尚无已保存的数据，本次不参与生成（其已生成的草稿保持不变）；请先打开该表填写并保存`
    : ''
})

function requestBody(dryRun: boolean) {
  const origins = [...props.sourceOrigins]
  return {
    year: props.year as number,
    groups: props.sourceGroups.filter((g) => origins.includes(g.origin)),
    // 显式声明负责的来源：其中某张表本次一组都没算出时，它以前生成的草稿也随之删除（需求 2.5）
    origins,
    dry_run: dryRun,
  }
}

let previewSeq = 0

async function preview() {
  if (!props.projectId || !props.year) return
  const seq = ++previewSeq
  previewing.value = true
  previewError.value = ''
  try {
    const res = await generateEliminationsFromWorksheet(props.projectId, requestBody(true), { silent: true })
    if (seq === previewSeq) previewResult.value = res
  } catch (e: any) {
    if (seq === previewSeq) {
      previewResult.value = null
      const status = e?.response?.status
      const detail = e?.response?.data?.detail
      const why = typeof detail === 'string' ? detail.trim() : ''
      previewError.value = status === 403
        ? '需要本项目的编辑权限才能预览与生成草稿分录'
        : `预览失败${why ? `：${why}` : ''}，请稍后点「重新预览」`
    }
  } finally {
    if (seq === previewSeq) previewing.value = false
  }
}

async function generate() {
  if (!props.projectId || !props.year || generating.value) return
  const dry = previewResult.value
  if (dry?.deleted_entries?.length) {
    try {
      await confirmDangerous({ title: '删除草稿分录', message: deletionConfirmText(dry), confirmText: '确认生成' })
    } catch {
      return
    }
  }
  generating.value = true
  try {
    const res = await generateEliminationsFromWorksheet(props.projectId, requestBody(false))
    ElMessage.success(generateResultText(res))
    await afterChange()
  } catch {
    /* 由 http 拦截器提示（409 并发 / 400 请求错误） */
  } finally {
    generating.value = false
  }
}

// 来源数据变化 ⇒ 重新预演（去抖：工作底稿逐格编辑时不逐键请求）
let previewTimer: ReturnType<typeof setTimeout> | null = null
watch(() => [props.sourceGroups, props.sourceOrigins], () => {
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = setTimeout(() => { previewTimer = null; preview() }, 600)
}, { deep: true })
onBeforeUnmount(() => { if (previewTimer) clearTimeout(previewTimer) })

// ─── 旧版明细表 ──────────────────────────────────────────────────────────────
const legacy = ref<LegacySheetResult | null>(null)
const legacyDetailVisible = ref(false)
const converting = ref(false)

async function convertLegacy() {
  if (!props.year || converting.value) return
  try {
    await confirmDangerous({
      title: '转为草稿分录',
      message: `把旧版明细表的 ${legacy.value?.custom_row_count || 0} 条自定义行按借贷平衡处切分转为草稿分录（默认类型「其他调整」，`
        + '审批前请逐笔确认类型与归属）。转入后旧版数据不再使用，重复点击不会重复转入。',
      confirmText: '转为草稿分录',
    })
  } catch {
    return
  }
  converting.value = true
  try {
    const res = await convertLegacyEliminationSheet(props.projectId, props.year)
    legacy.value = res
    const blocked = res.blocked?.length || 0
    ElMessage.success(`已转入 ${res.created} 笔草稿分录${blocked ? `，${blocked} 组不能转入，原因见明细` : ''}`)
    if (blocked) legacyDetailVisible.value = true
    await afterChange()
  } catch {
    /* 由 http 拦截器提示 */
  } finally {
    converting.value = false
  }
}

// ─── 导出 ────────────────────────────────────────────────────────────────────
async function exportSheet() {
  await exportData({
    data: exportRows(rows.value),
    columns: EXPORT_COLUMNS.map((c) => ({ ...c })),
    sheetName: '合并抵消分录',
    fileName: `合并抵消分录明细_${props.year ?? ''}.xlsx`,
  })
}

watch(() => [props.projectId, props.year] as const, ([pid], old) => {
  if (!pid || (old && old[0] === pid && old[1] === props.year)) return
  accountsFor = ''
  reload()
})

onMounted(reload)

defineExpose({ reload })
</script>

<style scoped>
.ws-sheet { padding: 0; position: relative; }
.ws-sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 6px; }
.ws-sheet-header h3 { margin: 0; font-size: var(--gt-font-size-base); color: var(--gt-color-text-primary); }
.ws-sheet-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.ws-tip { padding: 6px 10px; margin-bottom: 10px; background: var(--gt-color-bg); border-radius: 6px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); line-height: 1.5; }
.ws-tip b { color: var(--gt-color-primary); }
.ws-link { color: var(--gt-color-primary); cursor: pointer; text-decoration: underline; font-weight: 500; }
.ws-computed { color: var(--gt-color-primary); font-weight: 500; }
.ws-diff-warn { color: var(--gt-color-wheat) !important; font-weight: 700 !important; }
.ws-section { margin-top: 14px; }
.ws-section-title { font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-primary); padding: 6px 10px; background: var(--gt-color-primary-bg); border-radius: 4px; }
.ws-balance-check {
  margin-top: 10px; padding: 8px 14px; background: var(--gt-color-bg); border-radius: 6px;
  border: 1px solid var(--gt-color-border-light); font-size: var(--gt-font-size-sm); display: flex; flex-direction: column; gap: 4px;
}
.elim-total-row { display: flex; gap: 16px; align-items: center; }
.elim-total-label { min-width: 150px; color: var(--gt-color-text-secondary); }
.elim-balanced { color: var(--gt-color-success); margin-left: 4px; }
.elim-unbalanced { color: var(--gt-color-wheat); margin-left: 4px; }
.elim-legacy { margin-bottom: 10px; }
.elim-legacy-list { margin: 6px 0 0; padding-left: 18px; font-size: var(--gt-font-size-xs); line-height: 1.8; }
.elim-reason { margin-left: 6px; color: var(--gt-color-coral, #e6443e); }
.elim-orphan { color: var(--gt-color-coral, #e6443e); }
.elim-host { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-right: 4px; }
.elim-counted { color: var(--gt-color-success); }
.elim-not-counted { color: var(--gt-color-text-tertiary); }
.elim-pending-title { display: flex; align-items: center; gap: 6px; }
.elim-pending-summary { margin: 6px 0; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
.elim-pending-warning { margin-bottom: 4px; }
.elim-pending-entry { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.elim-review-notes { margin: 6px 0 0; padding-left: 18px; font-size: var(--gt-font-size-xs); color: var(--gt-color-wheat); }
.elim-bad-text { color: var(--gt-color-coral, #e6443e); }
.elim-warn-text { color: var(--gt-color-wheat); }
.elim-small { font-size: var(--gt-font-size-xs); line-height: 1.4; }
.ws-table :deep(.elim-row-readonly td) { background: var(--gt-color-bg) !important; color: var(--gt-color-text-secondary); }
.ws-table :deep(.elim-row-uncounted td) { color: var(--gt-color-text-secondary); }
</style>
