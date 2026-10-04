<!--
  合并试算平衡表页（spec consol-elimination-single-source-push 任务 11 / 需求 4）
  只读：按报表行次显示所选汇总节点的五列净额（审定汇总 / 权益抵销 / 往来交易抵销 / 报表调整 / 合并审定数），
  数据来自 GET /worksheet/report-trial —— 与合并报表、报表差额表同一个求值函数，读时计算不写库；
  合并审定数由后端给出，前端不再按「借减贷」重算。每个金额可穿透：抵销与调整列 → 分录明细，审定汇总 → 各数据节点。
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
        <span class="gt-ctb-node-label">汇总节点</span>
        <el-select v-model="nodeKey" size="small" style="width:240px" placeholder="根合并节点" data-testid="ctb-node"
          @change="() => load()">
          <el-option v-for="n in aggregateNodes" :key="n.node_key" :label="n.label" :value="n.node_key" />
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

    <div class="gt-ctb-info">
      <span>{{ nodeLabel || '—' }} · {{ reportTypeLabel(reportType) }} · {{ rows.length }} 行</span>
      <span class="gt-ctb-info-formula">合并审定数 = 审定汇总 + 权益抵销 + 往来交易抵销 + 报表调整（按科目自然方向的净额；只计已审批分录）</span>
    </div>

    <div v-loading="loading" class="gt-ctb-table-wrap">
      <el-table :data="rows" border size="small" max-height="calc(100vh - 280px)" style="width:100%"
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
            <!-- GtAmountCell 根节点是批注气泡（无包裹元素），样式与测试标识放在外层 span -->
            <span v-if="cellValue(row, col.key) !== null" :class="{ 'gt-ctb-total': col.key === 'consolidated' }"
              :data-testid="`ctb-cell-${row.row_code}-${col.key}`">
              <GtAmountCell :value="cellValue(row, col.key)" :clickable="isDrillable(row)" @click="openDrill(row, col.key)" />
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

    <!-- 穿透 -->
    <el-dialog v-model="drill.visible" :title="drill.title" width="860px" append-to-body destroy-on-close data-testid="ctb-drill">
      <div v-loading="drill.loading">
        <p v-if="drill.note" class="gt-ctb-drill-note" data-testid="ctb-drill-note">{{ drill.note }}</p>
        <el-table v-if="drill.mode === 'entries'" :data="drill.lines" border size="small" max-height="420"
          empty-text="没有已审批分录取到该行" data-testid="ctb-drill-entries">
          <el-table-column prop="entry_no" label="分录编号" width="110" />
          <el-table-column prop="node_label" label="归属节点" min-width="150" show-overflow-tooltip />
          <el-table-column label="科目" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ row.account_code }} {{ row.account_name || '' }}</template>
          </el-table-column>
          <el-table-column label="借方" width="120" align="right">
            <template #default="{ row }"><GtAmountCell :value="row.debit" /></template>
          </el-table-column>
          <el-table-column label="贷方" width="120" align="right">
            <template #default="{ row }"><GtAmountCell :value="row.credit" /></template>
          </el-table-column>
          <el-table-column label="对该行贡献" width="130" align="right">
            <template #default="{ row }"><GtAmountCell :value="row.contribution" /></template>
          </el-table-column>
        </el-table>
        <el-table v-else :data="drill.individual" border size="small" max-height="420"
          empty-text="没有数据节点" data-testid="ctb-drill-individual">
          <el-table-column prop="node_label" label="数据节点" min-width="200" show-overflow-tooltip />
          <el-table-column label="个别数" width="150" align="right">
            <template #default="{ row }"><GtAmountCell :value="row.amount" /></template>
          </el-table-column>
          <el-table-column label="说明" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">{{ row.reason || '' }}</template>
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
import { computed, reactive, ref, watch } from 'vue'
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
  type ConsolTrialMeasure,
} from '@/services/consolidationApi'
import { nodeLabel as nodeLabelOf, walkTree } from '@/components/consolidation/composables/consolTreeView'
import {
  cellValue,
  isDrillable,
  pushStatusText,
  reportTypeLabel,
  sumAmounts,
  TRIAL_MEASURES,
  TRIAL_REPORT_TYPES,
  trialAuditResults,
  trialExportAoa,
  type TrialAuditResult,
} from '@/components/consolidation/composables/consolTrialView'

defineOptions({ name: 'ConsolTrialBalanceTab' })

const props = defineProps<{
  projectId: string
  year: number | null
  /** 企业树（页面已加载）：汇总节点下拉取自它，与报表差额表的节点同一来源 */
  tree?: ConsolTreeNode | null
}>()

const emit = defineEmits<{
  (e: 'audit', results: TrialAuditResult[]): void
  (e: 'cell-context-menu', event: MouseEvent, row: ConsolReportTrialRow, ri: number): void
}>()

// ─── 读取 ────────────────────────────────────────────────────────────────────
const reportType = ref('balance_sheet')
const nodeKey = ref<string | null>(null)
const loading = ref(false)
const loadError = ref('')
const rows = ref<ConsolReportTrialRow[]>([])
const columns = ref<ReadonlyArray<{ key: ConsolTrialMeasure; label: string }>>(TRIAL_MEASURES)
const nodeLabel = ref('')
const pushStatus = ref<ConsolPushStatus | null>(null)
const pushText = computed(() => pushStatusText(pushStatus.value))
/** 已加载过（年度 / 项目变化时才需要重读；没打开过本页就不读） */
let loaded = false

/** 汇总节点（树序；与后端 aggregate_nodes 同一判定：kind = aggregate） */
const aggregateNodes = computed(() => {
  const out: Array<{ node_key: string; label: string }> = []
  for (const n of walkTree(props.tree)) if (n.kind === 'aggregate') out.push({ node_key: n.node_key, label: nodeLabelOf(n) })
  return out
})

let loadSeq = 0

async function load() {
  if (!props.projectId) return
  loaded = true
  const seq = ++loadSeq
  loading.value = true
  loadError.value = ''
  try {
    const res = await getConsolReportTrial(props.projectId, {
      reportType: reportType.value, nodeKey: nodeKey.value, year: props.year,
    })
    if (seq !== loadSeq) return
    rows.value = res?.rows || []
    columns.value = res?.columns?.length ? res.columns : TRIAL_MEASURES
    nodeLabel.value = res?.node_label || ''
    if (!nodeKey.value && res?.node_key) nodeKey.value = res.node_key
  } catch (e: any) {
    if (seq !== loadSeq) return
    rows.value = []
    const detail = e?.response?.data?.detail
    loadError.value = typeof detail === 'string' && detail ? detail : '加载合并试算平衡表失败'
  } finally {
    if (seq === loadSeq) loading.value = false
  }
  loadPushStatus()
}

// 树变了（重新识别 / 范围调整）且所选节点已不在树中 ⇒ 回到根合并节点
watch(aggregateNodes, (nodes) => {
  if (!nodeKey.value || !nodes.length || nodes.some((n) => n.node_key === nodeKey.value)) return
  nodeKey.value = null
  if (loaded) load()
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
})

async function openDrill(row: ConsolReportTrialRow, measure: ConsolTrialMeasure) {
  if (!isDrillable(row)) return
  const label = columns.value.find((c) => c.key === measure)?.label || measure
  Object.assign(drill, {
    visible: true, loading: true, title: `${row.row_name} — ${label}`, note: '',
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
      drill.note = res?.note || (measure === 'consolidated' ? '合并审定数中由分录构成的部分（个别数见「审定汇总」列）' : '')
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
  display: flex; align-items: center; gap: 12px; padding: 2px 0 6px;
  font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary, #6e6e73); flex-shrink: 0;
}
.gt-ctb-info-formula {
  padding: 2px 8px; background: var(--gt-color-primary-bg, #f4f0fa); border-radius: var(--gt-radius-sm, 4px);
  font-size: var(--gt-font-size-xs); color: var(--gt-color-primary, #4b2d77);
}
.gt-ctb-table-wrap { flex: 1; min-height: 0; overflow: hidden; }
.gt-ctb-code { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-ctb-blank { font-size: var(--gt-font-size-xs); color: var(--gt-color-wheat); cursor: help; }
.gt-ctb-note { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-ctb-total { font-weight: 700; color: var(--gt-color-primary); }
.gt-ctb-drill-note { margin: 0 0 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
.gt-ctb-drill-total { margin-top: 8px; text-align: right; font-size: var(--gt-font-size-sm); font-weight: 600; }
:deep(.gt-cm-total-row td) { font-weight: 700; background: var(--gt-color-primary-bg) !important; }
:deep(.gt-cm-category td) { font-weight: 600; color: var(--gt-color-primary); }
</style>
