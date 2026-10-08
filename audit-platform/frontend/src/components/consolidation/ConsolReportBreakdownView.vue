<!--
  合并报表「差额表」视图（spec consol-elimination-single-source-push 任务 12.1 / 需求 5）
  按报表格式显示所选汇总节点下每个直接子节点对每一行的贡献：母公司 / 本部、子公司、下级合并、合并差额 / 母分差额各一列，
  合计 = 该节点合并数。数据来自 GET /worksheet/report-breakdown —— 与合并报表、合并试算平衡表同一个求值函数，读时计算不写库。
  差额列（归属该差额节点的已审批调整 / 抵销分录）浅黄底，可穿透到分录；下级汇总列可下钻到该节点的差额表。
-->
<template>
  <div class="gt-crb" data-testid="crb">
    <div class="gt-crb-toolbar">
      <div class="gt-crb-toolbar-left">
        <span class="gt-crb-label">汇总节点</span>
        <el-select v-model="nodeKey" size="small" style="width:240px" placeholder="根合并节点" data-testid="crb-node"
          @change="() => load()">
          <el-option v-for="n in nodeOptions" :key="n.node_key" :label="n.label" :value="n.node_key" />
        </el-select>
        <span class="gt-crb-check" :class="{ 'gt-crb-check--bad': check.mismatched.length }" data-testid="crb-check">
          {{ checkText }}
        </span>
      </div>
      <div class="gt-crb-toolbar-right">
        <el-button size="small" :loading="loading" data-testid="crb-refresh" @click="load()">🔄 刷新</el-button>
        <el-button size="small" :disabled="!rows.length" data-testid="crb-export" @click="exportBreakdown">📤 导出</el-button>
      </div>
    </div>

    <el-alert v-if="loadError" type="error" :closable="false" show-icon :title="loadError" data-testid="crb-error" />
    <el-alert v-if="check.mismatched.length" type="warning" :closable="false" show-icon data-testid="crb-mismatch"
      :title="`以下行各列之和与合计不等：${check.mismatched.slice(0, 5).map((m) => m.row_name).join('、')}`" />

    <div class="gt-crb-info">
      <span>{{ nodeLabel || '—' }} · {{ rows.length }} 行 · {{ columns.length }} 个下级</span>
      <span class="gt-crb-legend"><i class="gt-crb-swatch" />差额列 = 归属该差额节点的已审批调整 / 抵销分录（只计已审批）</span>
    </div>

    <div v-loading="loading" class="gt-crb-table-wrap">
      <el-table :data="rows" border size="small" max-height="calc(100vh - 300px)" style="width:100%"
        :header-cell-style="{ whiteSpace: 'nowrap', fontSize: '12px' }" :cell-style="{ padding: '2px 8px', fontSize: '13px' }"
        :row-class-name="rowClassName" data-testid="crb-table">
        <el-table-column prop="row_code" label="行次" width="80" align="center">
          <template #default="{ row }"><span class="gt-crb-code">{{ row.row_code }}</span></template>
        </el-table-column>
        <el-table-column prop="row_name" label="项目" fixed="left" min-width="220">
          <template #default="{ row }">
            <span style="white-space:nowrap" :style="{ paddingLeft: (row.indent_level || 0) * 16 + 'px' }">{{ row.row_name }}</span>
          </template>
        </el-table-column>
        <el-table-column v-for="col in columns" :key="col.node_key" :label="col.label" min-width="132" align="right"
          :class-name="isElimColumn(col) ? 'gt-crb-elim-col' : ''"
          :label-class-name="isElimColumn(col) ? 'gt-crb-elim-col' : ''">
          <template #header>
            <span class="gt-crb-head" :data-testid="`crb-head-${col.node_key}`">
              {{ col.label }}<small class="gt-crb-kind" :class="`gt-crb-kind--${col.kind}`">{{ columnKindLabel(col.kind) }}</small>
              <a v-if="col.kind === 'aggregate'" class="gt-crb-dive" :data-testid="`crb-dive-${col.node_key}`"
                @click.stop="diveInto(col)">展开</a>
            </span>
          </template>
          <template #default="{ row }">
            <!-- GtAmountCell 根节点是批注气泡（无包裹元素），样式与测试标识放在外层 span -->
            <span v-if="breakdownCell(row, col.node_key) !== null"
              :class="{ 'gt-crb-cell--elim': isElimColumn(col) }" :data-testid="`crb-cell-${row.row_code}-${col.node_key}`">
              <GtAmountCell :value="breakdownCell(row, col.node_key)" :clickable="isElimColumn(col)"
                @click="openEntryDrill(row, col)" />
            </span>
            <el-tooltip v-else-if="row.has_formula && row.note" :content="row.note" placement="top">
              <span class="gt-crb-blank" :data-testid="`crb-blank-${row.row_code}-${col.node_key}`">留空</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="合计" min-width="140" align="right">
          <template #default="{ row }">
            <span v-if="breakdownTotal(row) !== null" class="gt-crb-total" :data-testid="`crb-total-${row.row_code}`">
              <GtAmountCell :value="breakdownTotal(row)" />
            </span>
            <el-tooltip v-else-if="row.has_formula && row.note" :content="row.note" placement="top">
              <span class="gt-crb-blank" :data-testid="`crb-total-blank-${row.row_code}`">留空</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="160" show-overflow-tooltip>
          <template #default="{ row }"><span class="gt-crb-note">{{ row.note || '' }}</span></template>
        </el-table-column>
      </el-table>
    </div>
    <el-empty v-if="!rows.length && !loading && !loadError" :image-size="80" description="该报表没有可显示的行" />

    <!-- 差额列穿透：构成该格的已审批分录明细 -->
    <el-dialog v-model="drill.visible" :title="drill.title" width="860px" append-to-body destroy-on-close data-testid="crb-drill">
      <div v-loading="drill.loading">
        <p v-if="drill.note" class="gt-crb-drill-note">{{ drill.note }}</p>
        <el-table :data="drill.lines" border size="small" max-height="420" empty-text="没有已审批分录取到该行"
          data-testid="crb-drill-entries">
          <el-table-column prop="entry_no" label="分录编号" width="110" />
          <el-table-column label="科目" min-width="180" show-overflow-tooltip>
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
        <div v-if="drill.total !== null" class="gt-crb-drill-total" data-testid="crb-drill-total">
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
  getConsolReportBreakdown,
  type ConsolBreakdownColumn,
  type ConsolEntryDrillLine,
  type ConsolReportBreakdownRow,
  type ConsolTreeNode,
} from '@/services/consolidationApi'
import { nodeLabel as nodeLabelOf, walkTree } from '@/components/consolidation/composables/consolTreeView'
import { reportTypeLabel } from '@/components/consolidation/composables/consolTrialView'
import {
  breakdownCell,
  breakdownCheck,
  breakdownCheckText,
  breakdownExportAoa,
  breakdownTotal,
  columnKindLabel,
  isElimColumn,
} from '@/components/consolidation/composables/consolReportBreakdown'

defineOptions({ name: 'ConsolReportBreakdownView' })

const props = defineProps<{
  projectId: string
  /** 企业树的审计年度（与试算页、明细表同一年度来源）；不传由后端取项目审计年度 */
  year: number | null
  /** 报表类型：与合并报表页顶部的报表标签共用 */
  reportType: string
  /** 企业树（页面已加载）：汇总节点下拉取自它，与合并试算平衡表同一来源 */
  tree?: ConsolTreeNode | null
  /** CP-01：父级选中的节点键；左树选择变化时传入，同步到内部 nodeKey 并刷新 */
  selectedNodeKey?: string | null
}>()

const nodeKey = ref<string | null>(null)
const loading = ref(false)
const loadError = ref('')
const rows = ref<ConsolReportBreakdownRow[]>([])
const columns = ref<ConsolBreakdownColumn[]>([])
const nodeLabel = ref('')
/** 后端给的可选汇总节点（树未加载时兜底） */
const serverNodes = ref<Array<{ node_key: string; label: string }>>([])
/** 已加载过：报表类型 / 年度 / 树变化时才需要重读；没打开过本视图就不读 */
let loaded = false
let loadSeq = 0

/** 汇总节点（树序；与后端 aggregate_nodes 同一判定：kind = aggregate） */
const nodeOptions = computed(() => {
  const out: Array<{ node_key: string; label: string }> = []
  for (const n of walkTree(props.tree)) if (n.kind === 'aggregate') out.push({ node_key: n.node_key, label: nodeLabelOf(n) })
  return out.length ? out : serverNodes.value
})

const check = computed(() => breakdownCheck(rows.value, columns.value))
const checkText = computed(() => (rows.value.length ? breakdownCheckText(check.value) : ''))

async function load() {
  if (!props.projectId) return
  loaded = true
  const seq = ++loadSeq
  loading.value = true
  loadError.value = ''
  try {
    const res = await getConsolReportBreakdown(props.projectId, {
      reportType: props.reportType, nodeKey: nodeKey.value, year: props.year,
    })
    if (seq !== loadSeq) return
    rows.value = res?.rows || []
    columns.value = res?.columns || []
    nodeLabel.value = res?.node_label || ''
    serverNodes.value = (res?.aggregate_nodes || []).map((n) => ({ node_key: n.node_key, label: n.label }))
    if (!nodeKey.value && res?.node_key) nodeKey.value = res.node_key
  } catch (e: any) {
    if (seq !== loadSeq) return
    rows.value = []
    columns.value = []
    const detail = e?.response?.data?.detail
    loadError.value = typeof detail === 'string' && detail ? detail : '加载报表差额表失败'
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

/** 下级汇总列「展开」：切到该节点的差额表（下拉同步） */
function diveInto(col: ConsolBreakdownColumn) {
  if (col.kind !== 'aggregate') return
  nodeKey.value = col.node_key
  load()
}

// 报表类型切换（顶部标签） ⇒ 已打开过则按新类型重读
watch(() => props.reportType, (v, old) => {
  if (v !== old && loaded) load()
})

// 树变了（重新识别 / 范围调整）且所选节点已不在树中 ⇒ 回到根合并节点
watch(nodeOptions, (nodes) => {
  if (!nodeKey.value || !nodes.length || nodes.some((n) => n.node_key === nodeKey.value)) return
  nodeKey.value = null
  if (loaded) load()
})

watch(() => [props.projectId, props.year] as const, ([pid, y], old) => {
  if (!pid || !old || (old[0] === pid && old[1] === y)) return
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

// ─── 差额列穿透 ──────────────────────────────────────────────────────────────
const drill = reactive({
  visible: false,
  loading: false,
  title: '',
  note: '',
  lines: [] as ConsolEntryDrillLine[],
  total: null as string | null,
  cell: null as string | null,
})

async function openEntryDrill(row: ConsolReportBreakdownRow, col: ConsolBreakdownColumn) {
  if (!isElimColumn(col)) return
  Object.assign(drill, {
    visible: true, loading: true, title: `${row.row_name} — ${col.label}`, note: '',
    lines: [], total: null, cell: breakdownCell(row, col.node_key),
  })
  try {
    // 差额节点即穿透节点：只取归属它的已审批分录（调整 + 抵销），贡献之和 = 本格
    const res = await drillConsolRowEntries(props.projectId, {
      rowCode: row.row_code, measure: 'consolidated', nodeKey: col.node_key, year: props.year,
    })
    drill.lines = res?.lines || []
    drill.total = res?.decomposable ? res.total : null
    drill.note = res?.note || ''
  } catch {
    drill.visible = false
  } finally {
    drill.loading = false
  }
}

// ─── 导出 ────────────────────────────────────────────────────────────────────
async function exportBreakdown() {
  if (!rows.value.length) return
  await exportMultiSheetData({
    sheets: [{
      sheetName: '报表差额表',
      rows: breakdownExportAoa(rows.value, columns.value),
      colWidths: [{ wch: 10 }, { wch: 30 }, ...columns.value.map(() => ({ wch: 16 })), { wch: 16 }, { wch: 30 }],
    }],
    fileName: `报表差额表_${nodeLabel.value}_${reportTypeLabel(props.reportType)}_${props.year ?? ''}.xlsx`,
    applyStyles: false,
    successMessage: false,
  })
  ElMessage.success('已导出')
}

function rowClassName({ row }: { row: ConsolReportBreakdownRow }): string {
  if (row.is_total_row) return 'gt-cm-total-row'
  if (!row.has_formula) return 'gt-cm-category'
  return ''
}

defineExpose({ load, rows, columns, nodeKey, loading })
</script>

<style scoped>
.gt-crb { display: flex; flex-direction: column; }
.gt-crb-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin: 8px 0 6px; flex-wrap: wrap; }
.gt-crb-toolbar-left, .gt-crb-toolbar-right { display: flex; align-items: center; gap: 8px; }
.gt-crb-label { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
.gt-crb-check { font-size: var(--gt-font-size-xs); color: var(--gt-color-success); }
.gt-crb-check--bad { color: var(--gt-color-coral); }
.gt-crb-info {
  display: flex; align-items: center; gap: 12px; padding: 2px 0 6px;
  font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary);
}
.gt-crb-legend { display: inline-flex; align-items: center; gap: 4px; }
.gt-crb-swatch {
  display: inline-block; width: 12px; height: 12px; border-radius: 2px;
  background: var(--gt-color-wheat-light); border: 1px solid var(--gt-color-wheat);
}
.gt-crb-table-wrap { min-height: 0; overflow: hidden; }
.gt-crb-code { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-crb-head { display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
.gt-crb-kind {
  padding: 0 4px; border-radius: var(--gt-radius-sm, 4px); font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary); background: var(--gt-color-bg-light, #f5f5f7);
}
.gt-crb-kind--elim { color: var(--gt-color-text-secondary); background: var(--gt-color-wheat-light); }
.gt-crb-dive { font-size: var(--gt-font-size-xs); color: var(--gt-color-primary); cursor: pointer; }
.gt-crb-blank { font-size: var(--gt-font-size-xs); color: var(--gt-color-wheat); cursor: help; }
.gt-crb-note { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-crb-total { font-weight: 700; color: var(--gt-color-primary); }
.gt-crb-drill-note { margin: 0 0 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
.gt-crb-drill-total { margin-top: 8px; text-align: right; font-size: var(--gt-font-size-sm); font-weight: 600; }
/* 差额列：浅黄底（表头与单元格） */
:deep(td.gt-crb-elim-col), :deep(th.gt-crb-elim-col) { background: var(--gt-color-wheat-light) !important; }
:deep(.gt-cm-total-row td) { font-weight: 700; }
:deep(.gt-cm-category td) { font-weight: 600; color: var(--gt-color-primary); }
</style>
