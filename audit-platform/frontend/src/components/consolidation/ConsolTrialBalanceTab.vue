<!--
  合并试算平衡表页（spec consol-elimination-single-source-push 任务 11 / 需求 4；
  spec consol-autotree-linkage-closure R5.1 / R8.5 / R10）
  只读：按报表行次显示所选节点的五列净额（审定汇总 / 权益抵销 / 往来交易抵销 / 报表调整 / 合并审定数），
  数据来自 GET /worksheet/report-trial —— 与合并报表、报表差额表同一个求值函数，读时计算不写库；
  合并审定数由后端给出，前端不再按「借减贷」重算。每个金额可穿透：抵销与调整列 → 分录明细，审定汇总 → 各数据节点。
  - 节点下拉列出企业树全部节点（按层级缩进），切换后回写左树当前节点（node-change）；列口径按节点类型说明；
  - 「含草稿预览」列 = 已审批 + 草稿 + 待审批分录的合并数，与合并审定数不同的格高亮（只作对照，不可穿透）；
  - 节点合并数按科目自然方向做借贷平衡检查，不平时提示。
  分录审批后后端自动推送；子企业数据变化后可「重新推送」。
-->
<template>
  <div class="gt-ctb" data-testid="ctb">
    <div class="gt-ctb-type-bar">
      <span v-for="item in TRIAL_REPORT_TYPES" :key="item.key" class="gt-report-type-tag"
        :class="{ 'gt-report-type-tag--active': reportType === item.key }" :data-testid="`ctb-type-${item.key}`"
        @click="selectReportType(item.key)">
        {{ item.label }}
      </span>
    </div>

    <div class="gt-ctb-toolbar">
      <div class="gt-ctb-toolbar-left">
        <span class="gt-ctb-node-label">节点</span>
        <el-select v-model="nodeKey" size="small" style="width:260px" placeholder="根合并节点" filterable data-testid="ctb-node"
          @change="onNodeChange">
          <el-option v-for="n in nodeOptions" :key="n.value" :label="n.label" :value="n.value">
            <span :style="{ paddingLeft: n.depth * 12 + 'px' }">{{ n.label }}</span>
          </el-option>
        </el-select>
        <span class="gt-ctb-push" :class="{ 'gt-ctb-push--stale': pushStatus?.is_stale }" data-testid="ctb-push-status">
          {{ pushText }}
        </span>
      </div>
      <div class="gt-ctb-toolbar-right">
        <el-button size="small" :loading="loading" data-testid="ctb-refresh" @click="load()">🔄 刷新</el-button>
        <el-tooltip content="重算差额表 → 合并试算 → 合并报表 → 标记附注待更新（含上层合并项目）" placement="bottom">
          <el-button size="small" type="primary" :loading="pushing" data-testid="ctb-push" @click="push">📤 重新推送</el-button>
        </el-tooltip>
        <el-button size="small" :disabled="!rows.length" @click="exportTrial">📤 导出</el-button>
        <el-button size="small" :disabled="!rows.length" data-testid="ctb-audit" @click="auditTrial">✅ 审核</el-button>
      </div>
    </div>

    <el-alert v-if="pushStatus?.is_stale" type="warning" :closable="false" show-icon class="gt-ctb-stale"
      data-testid="ctb-stale" title="子企业数据已变化，建议重新推送：本页按最新数据读时计算，已生成的合并报表与附注还是旧数" />
    <el-alert v-if="loadError" type="error" :closable="false" show-icon :title="loadError" data-testid="ctb-error" />
    <el-alert v-if="balanceText" type="warning" :closable="false" show-icon class="gt-ctb-stale"
      data-testid="ctb-unbalanced" title="借贷不平衡">{{ balanceText }}</el-alert>

    <div class="gt-ctb-info">
      <span>{{ nodeLabel || '—' }} · {{ reportTypeLabel(reportType) }} · {{ rows.length }} 行</span>
      <span v-if="balance?.balanced" class="gt-ctb-balanced" data-testid="ctb-balanced">借贷平衡</span>
      <span class="gt-ctb-info-formula" data-testid="ctb-basis-note">{{ basisNote }}</span>
      <span v-if="draftPending" class="gt-ctb-draft-note" data-testid="ctb-draft-note">
        含草稿预览计入 {{ draftPending }} 笔未审批分录（草稿 / 待审批）；合并审定数、合并报表与附注只计已审批
      </span>
    </div>

    <div v-loading="loading" class="gt-ctb-table-wrap">
      <el-table :data="rows" border size="small" max-height="calc(100vh - 300px)" style="width:100%"
        :header-cell-style="{ whiteSpace: 'nowrap', fontSize: '12px' }" :cell-style="{ padding: '2px 8px', fontSize: '13px' }"
        :row-class-name="rowClassName" data-testid="ctb-table" @row-contextmenu="onRowContextMenu">
        <el-table-column prop="row_code" label="行次" width="80" align="center">
          <template #default="{ row }"><span class="gt-ctb-code">{{ row.row_code }}</span></template>
        </el-table-column>
        <el-table-column prop="row_name" label="项目" fixed="left" min-width="220">
          <template #default="{ row }">
            <span style="white-space:nowrap" :style="{ paddingLeft: (row.indent_level || 0) * 16 + 'px' }">{{ row.row_name }}</span>
          </template>
        </el-table-column>
        <el-table-column v-for="col in columns" :key="col.key" :label="col.label" min-width="128" align="right">
          <template #default="{ row }">
            <!-- 含草稿预览：与合并审定数不同 ⇒ 高亮并说明；只作对照，不穿透（穿透只计已审批） -->
            <el-tooltip v-if="col.key === DRAFT_COLUMN && draftDiffers(row)" placement="top"
              content="与合并审定数不同：差额来自未审批分录（草稿 / 待审批）">
              <span class="gt-ctb-draft gt-ctb-draft--diff" :data-testid="`ctb-cell-${row.row_code}-${col.key}`">
                <GtAmountCell :value="cellValue(row, col.key)" />
              </span>
            </el-tooltip>
            <!-- GtAmountCell 根节点是批注气泡（无包裹元素），样式与测试标识放在外层 span -->
            <span v-else-if="cellValue(row, col.key) !== null"
              :class="{ 'gt-ctb-total': col.key === 'consolidated', 'gt-ctb-draft': col.key === DRAFT_COLUMN }"
              :data-testid="`ctb-cell-${row.row_code}-${col.key}`">
              <GtAmountCell :value="cellValue(row, col.key)" :clickable="col.key !== DRAFT_COLUMN && isDrillable(row)"
                @click="openDrill(row, col.key)" />
            </span>
            <el-tooltip v-else-if="row.has_formula && row.note" :content="row.note" placement="top">
              <span class="gt-ctb-blank" :data-testid="`ctb-blank-${row.row_code}-${col.key}`">留空</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="160" show-overflow-tooltip>
          <template #default="{ row }"><span class="gt-ctb-note">{{ row.note || '' }}</span></template>
        </el-table-column>
      </el-table>
    </div>
    <el-empty v-if="!rows.length && !loading && !loadError" :image-size="80" description="该报表没有可显示的行" />

    <!-- 穿透：金额为空（取不到数）显示「空」，为 0 显示 0.00，两者分开（R10.3） -->
    <el-dialog v-model="drill.visible" :title="drill.title" width="920px" append-to-body destroy-on-close data-testid="ctb-drill">
      <div v-loading="drill.loading">
        <p v-if="drill.note" class="gt-ctb-drill-note" data-testid="ctb-drill-note">{{ drill.note }}</p>
        <p v-if="drill.composition" class="gt-ctb-drill-note gt-ctb-drill-composition" data-testid="ctb-drill-composition">
          合并审定数 {{ drill.composition.consolidated ?? '空' }} = 审定汇总 {{ drill.composition.individual ?? '空' }}
          + 已审批分录 {{ drill.composition.entries ?? '空' }}
        </p>
        <el-table v-if="drill.mode === 'entries'" :data="drill.lines" border size="small" max-height="420"
          empty-text="没有已审批分录取到该行" data-testid="ctb-drill-entries">
          <el-table-column prop="entry_no" label="分录编号" width="100" />
          <el-table-column label="类型" width="110" show-overflow-tooltip>
            <template #default="{ row }"><span data-testid="ctb-drill-type">{{ row.entry_type_label || row.entry_type }}</span></template>
          </el-table-column>
          <el-table-column prop="node_label" label="归属节点" min-width="140" show-overflow-tooltip />
          <el-table-column label="科目" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ row.account_code }} {{ row.account_name || '' }}</template>
          </el-table-column>
          <el-table-column label="借方" width="110" align="right">
            <template #default="{ row }">
              <span v-if="amountKind(row.debit) === 'blank'" class="gt-ctb-null">空</span>
              <span v-else-if="amountKind(row.debit) === 'zero'" class="gt-ctb-zero">0.00</span>
              <GtAmountCell v-else :value="row.debit" />
            </template>
          </el-table-column>
          <el-table-column label="贷方" width="110" align="right">
            <template #default="{ row }">
              <span v-if="amountKind(row.credit) === 'blank'" class="gt-ctb-null">空</span>
              <span v-else-if="amountKind(row.credit) === 'zero'" class="gt-ctb-zero">0.00</span>
              <GtAmountCell v-else :value="row.credit" />
            </template>
          </el-table-column>
          <el-table-column label="对该行贡献" width="120" align="right">
            <template #default="{ row }">
              <span v-if="amountKind(row.contribution) === 'blank'" class="gt-ctb-null" title="该行公式不能展开到科目">空</span>
              <span v-else-if="amountKind(row.contribution) === 'zero'" class="gt-ctb-zero">0.00</span>
              <GtAmountCell v-else :value="row.contribution" />
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="140" show-overflow-tooltip>
            <template #default="{ row }"><span data-testid="ctb-drill-desc">{{ row.description || '' }}</span></template>
          </el-table-column>
        </el-table>
        <el-table v-else :data="drill.individual" border size="small" max-height="420"
          empty-text="没有数据节点" data-testid="ctb-drill-individual">
          <el-table-column prop="node_label" label="数据节点" min-width="180" show-overflow-tooltip />
          <el-table-column label="所属上级" min-width="150" show-overflow-tooltip>
            <template #default="{ row }"><span data-testid="ctb-drill-parent">{{ row.parent_label || '' }}</span></template>
          </el-table-column>
          <el-table-column label="个别数" width="140" align="right">
            <template #default="{ row }">
              <span v-if="amountKind(row.amount) === 'blank'" class="gt-ctb-null" :data-testid="`ctb-drill-amount-${row.node_key}`">空</span>
              <span v-else-if="amountKind(row.amount) === 'zero'" class="gt-ctb-zero" :data-testid="`ctb-drill-amount-${row.node_key}`">0.00</span>
              <span v-else :data-testid="`ctb-drill-amount-${row.node_key}`"><GtAmountCell :value="row.amount" /></span>
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ row.reason || '' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="110" align="center">
            <template #default="{ row }">
              <el-button v-if="row.project_id" size="small" link type="primary" :data-testid="`ctb-drill-enter-${row.node_key}`"
                @click="emit('enter-project', { projectId: row.project_id, label: row.node_label })">进入项目</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="drill.total !== null" class="gt-ctb-drill-total" data-testid="ctb-drill-total">
          合计 <GtAmountCell :value="drill.total" />
          <span v-if="drill.cell !== null">（本表该格 <GtAmountCell :value="drill.cell" />）</span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import { exportMultiSheetData } from '@/composables/useExcelIO'
import {
  drillConsolRowEntries,
  drillConsolRowIndividual,
  getConsolPushStatus,
  getConsolReportTrial,
  pushConsolidation,
  type ConsolDrillMeasure,
  type ConsolEntryDrillLine,
  type ConsolIndividualDrillRow,
  type ConsolPushStatus,
  type ConsolReportTrialRow,
  type ConsolTreeNode,
  type ConsolTrialBalanceCheck,
  type ConsolTrialColumnKey,
} from '@/services/consolidationApi'
import { treeOptionsWithDepth } from '@/components/consolidation/composables/consolTreeView'
import {
  amountKind,
  balanceHint,
  cellValue,
  DRAFT_COLUMN,
  draftDiffers,
  isDrillable,
  pushStatusText,
  reportTypeLabel,
  sumAmounts,
  TRIAL_MEASURES,
  TRIAL_REPORT_TYPES,
  trialAuditResults,
  trialBasisNote,
  trialExportAoa,
  type TrialAuditResult,
} from '@/components/consolidation/composables/consolTrialView'

defineOptions({ name: 'ConsolTrialBalanceTab' })

const props = defineProps<{
  projectId: string
  year: number | null
  /** 企业树（页面已加载）：节点下拉取自它（全部节点，按层级缩进），与报表差额表的节点同一来源 */
  tree?: ConsolTreeNode | null
  /** CP-01：父级选中的节点键；左树选择变化时传入，同步到内部 nodeKey 并刷新 */
  selectedNodeKey?: string | null
}>()

const emit = defineEmits<{
  (e: 'audit', results: TrialAuditResult[]): void
  (e: 'cell-context-menu', event: MouseEvent, row: ConsolReportTrialRow, ri: number): void
  /** 本页下拉切换节点 ⇒ 回写合并页当前节点（左树同步高亮，R10.2） */
  (e: 'node-change', nodeKey: string): void
  /** 个别数穿透里「进入项目」 */
  (e: 'enter-project', target: { projectId: string; label: string }): void
}>()

// ─── 读取 ────────────────────────────────────────────────────────────────────
const reportType = ref('balance_sheet')
const nodeKey = ref<string | null>(null)
const loading = ref(false)
const loadError = ref('')
const rows = ref<ConsolReportTrialRow[]>([])
const columns = ref<ReadonlyArray<{ key: ConsolTrialColumnKey; label: string }>>(TRIAL_MEASURES)
const nodeLabel = ref('')
const nodeKind = ref<string | null>(null)
const balance = ref<ConsolTrialBalanceCheck | null>(null)
const draftPending = ref(0)
const pushStatus = ref<ConsolPushStatus | null>(null)
const pushText = computed(() => pushStatusText(pushStatus.value))
const basisNote = computed(() => trialBasisNote(nodeKind.value))
const balanceText = computed(() => balanceHint(balance.value))
/** 已加载过（年度 / 项目变化时才需要重读；没打开过本页就不读） */
let loaded = false

/** 节点下拉：企业树全部节点（先序、按层级缩进、显示名称，不显示内部键） */
const nodeOptions = computed(() => treeOptionsWithDepth(props.tree))

let loadSeq = 0
let loadAbort: AbortController | null = null

async function load() {
  if (!props.projectId) return
  loaded = true
  const seq = ++loadSeq
  // 取消前一个飞行中的请求
  if (loadAbort) loadAbort.abort()
  loadAbort = new AbortController()
  const signal = loadAbort.signal
  loading.value = true
  loadError.value = ''
  try {
    const res = await getConsolReportTrial(props.projectId, {
      reportType: reportType.value, nodeKey: nodeKey.value, year: props.year, signal,
    })
    if (seq !== loadSeq) return
    rows.value = res?.rows || []
    columns.value = res?.columns?.length ? res.columns : TRIAL_MEASURES
    nodeLabel.value = res?.node_label || ''
    nodeKind.value = res?.node_kind || null
    balance.value = res?.balance || null
    draftPending.value = res?.draft_pending_entries || 0
    if (!nodeKey.value && res?.node_key) nodeKey.value = res.node_key
  } catch (e: any) {
    if (seq !== loadSeq) return
    // 被 abort 的请求不算错误
    if (e?.code === 'ERR_CANCELED' || e?.name === 'AbortError') return
    rows.value = []
    balance.value = null
    const detail = e?.response?.data?.detail
    loadError.value = typeof detail === 'string' && detail ? detail : '加载合并试算平衡表失败'
  } finally {
    if (seq === loadSeq) loading.value = false
  }
  loadPushStatus()
}

/** 本页下拉切换节点：按新节点重读，并回写左树当前节点 */
function onNodeChange(key: string) {
  load()
  if (key) emit('node-change', key)
}

// 树变了（重新识别 / 范围调整）且所选节点已不在树中 ⇒ 回到根合并节点
watch(nodeOptions, (nodes) => {
  if (!nodeKey.value || !nodes.length || nodes.some((n) => n.value === nodeKey.value)) return
  nodeKey.value = null
  if (loaded) load()
})

// CP-01：父级选中节点变化时同步到内部 nodeKey 并刷新（左树点击传播）
watch(() => props.selectedNodeKey, (newKey) => {
  if (newKey != null && newKey !== nodeKey.value) {
    nodeKey.value = newKey
    if (loaded) load()
  }
})

async function loadPushStatus() {
  if (!props.year) return
  try {
    pushStatus.value = await getConsolPushStatus(props.projectId, props.year)
  } catch {
    pushStatus.value = null
  }
}

function selectReportType(key: string) {
  if (reportType.value === key) return
  reportType.value = key
  load()
}

// ─── 重新推送 ────────────────────────────────────────────────────────────────
const pushing = ref(false)

async function push() {
  if (!props.year || pushing.value) return
  pushing.value = true
  try {
    const res = await pushConsolidation(props.projectId, props.year, 'manual')
    ElMessage.success(res?.message || '已开始推送，完成后自动刷新')
  } catch {
    /* 由 http 拦截器提示（如无编辑权限） */
  } finally {
    pushing.value = false
  }
}

// ─── 穿透 ────────────────────────────────────────────────────────────────────
const drill = reactive({
  visible: false,
  loading: false,
  title: '',
  mode: 'entries' as 'entries' | 'individual',
  note: '',
  lines: [] as ConsolEntryDrillLine[],
  individual: [] as ConsolIndividualDrillRow[],
  total: null as string | null,
  cell: null as string | null,
  /** 合并审定数列的完整构成（审定汇总 + 已审批分录 = 合并数） */
  composition: null as { individual: string | null; entries: string | null; consolidated: string | null } | null,
})

async function openDrill(row: ConsolReportTrialRow, measure: ConsolTrialColumnKey) {
  if (measure === DRAFT_COLUMN || !isDrillable(row)) return
  const label = columns.value.find((c) => c.key === measure)?.label || measure
  Object.assign(drill, {
    visible: true, loading: true, title: `${row.row_name} — ${label}`, note: '', composition: null,
    lines: [], individual: [], total: null, cell: cellValue(row, measure),
    mode: measure === 'individual' ? 'individual' : 'entries',
  })
  try {
    if (measure === 'individual') {
      const res = await drillConsolRowIndividual(props.projectId, {
        rowCode: row.row_code, nodeKey: nodeKey.value, year: props.year,
      })
      drill.individual = res?.rows || []
      drill.total = drill.individual.length ? sumAmounts(drill.individual.map((r) => r.amount)) : null
      if (!row.linear) drill.note = '该行公式非线性，各数据节点的值之和不一定等于本表该格'
    } else {
      const res = await drillConsolRowEntries(props.projectId, {
        rowCode: row.row_code, measure: measure as ConsolDrillMeasure, nodeKey: nodeKey.value, year: props.year,
      })
      drill.lines = res?.lines || []
      drill.total = res?.decomposable ? res.total : null
      drill.note = res?.note || ''
      if (measure === 'consolidated' && res?.decomposable) {
        drill.composition = {
          individual: res.individual_total ?? null, entries: res.total, consolidated: res.consolidated_total ?? null,
        }
      }
    }
  } catch {
    drill.visible = false
  } finally {
    drill.loading = false
  }
}

// ─── 导出 / 审核 ─────────────────────────────────────────────────────────────
async function exportTrial() {
  if (!rows.value.length) return
  await exportMultiSheetData({
    sheets: [{
      sheetName: '合并试算平衡表',
      rows: trialExportAoa(rows.value, columns.value),
      colWidths: [{ wch: 10 }, { wch: 30 }, ...columns.value.map(() => ({ wch: 16 })), { wch: 30 }],
    }],
    fileName: `合并试算平衡表_${reportTypeLabel(reportType.value)}_${props.year ?? ''}.xlsx`,
    applyStyles: false,
    successMessage: false,
  })
  ElMessage.success('已导出')
}

function auditTrial() {
  emit('audit', trialAuditResults(rows.value, `${nodeLabel.value} · ${reportTypeLabel(reportType.value)}`))
}

function rowClassName({ row }: { row: ConsolReportTrialRow }): string {
  if (row.is_total_row) return 'gt-cm-total-row'
  if (!row.has_formula) return 'gt-cm-category'
  return ''
}

function onRowContextMenu(row: ConsolReportTrialRow, _col: unknown, event: MouseEvent) {
  event.preventDefault()
  emit('cell-context-menu', event, row, rows.value.indexOf(row))
}

watch(() => [props.projectId, props.year] as const, ([pid, y], old) => {
  if (!pid || !old || (old[0] === pid && old[1] === y)) return
  nodeKey.value = null
  if (loaded) load()
})

// 组件卸载时取消飞行中的请求
onBeforeUnmount(() => {
  if (loadAbort) loadAbort.abort()
  loadSeq += 1
})

defineExpose({ load, rows, reportType, loading, nodeKey })
</script>

<style scoped>
.gt-ctb { display: flex; flex-direction: column; height: calc(100vh - 120px); padding: 0 16px; }
.gt-ctb-type-bar {
  display: flex; gap: 0; border-bottom: 2px solid var(--gt-color-border-light, #f0f0f5); margin-bottom: 8px; flex-shrink: 0;
}
.gt-ctb-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 6px; flex-shrink: 0; flex-wrap: wrap; }
.gt-ctb-toolbar-left, .gt-ctb-toolbar-right { display: flex; align-items: center; gap: 8px; }
.gt-ctb-node-label { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
.gt-ctb-push { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-ctb-push--stale { color: var(--gt-color-wheat); }
.gt-ctb-stale { margin-bottom: 6px; flex-shrink: 0; }
.gt-ctb-info {
  display: flex; align-items: center; gap: 12px; padding: 2px 0 6px; flex-wrap: wrap;
  font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary, #6e6e73); flex-shrink: 0;
}
.gt-ctb-info-formula {
  padding: 2px 8px; background: var(--gt-color-primary-bg, #f4f0fa); border-radius: var(--gt-radius-sm, 4px);
  font-size: var(--gt-font-size-xs); color: var(--gt-color-primary, #4b2d77);
}
.gt-ctb-balanced { color: var(--gt-color-success); }
.gt-ctb-draft-note { color: var(--gt-color-text-tertiary); }
.gt-ctb-table-wrap { flex: 1; min-height: 0; overflow: hidden; }
.gt-ctb-code { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-ctb-blank { font-size: var(--gt-font-size-xs); color: var(--gt-color-wheat); cursor: help; }
.gt-ctb-note { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-ctb-total { font-weight: 700; color: var(--gt-color-primary); }
.gt-ctb-draft { color: var(--gt-color-text-secondary); font-style: italic; }
.gt-ctb-draft--diff {
  padding: 0 4px; border-radius: var(--gt-radius-sm, 4px); background: var(--gt-color-wheat-light);
  color: var(--gt-color-text-primary); font-style: normal; cursor: help;
}
.gt-ctb-null { font-size: var(--gt-font-size-xs); color: var(--gt-color-wheat); }
.gt-ctb-zero { color: var(--gt-color-text-secondary); }
.gt-ctb-drill-note { margin: 0 0 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
.gt-ctb-drill-composition { color: var(--gt-color-primary); }
.gt-ctb-drill-total { margin-top: 8px; text-align: right; font-size: var(--gt-font-size-sm); font-weight: 600; }
:deep(.gt-cm-total-row td) { font-weight: 700; background: var(--gt-color-primary-bg) !important; }
:deep(.gt-cm-category td) { font-weight: 600; color: var(--gt-color-primary); }
</style>
