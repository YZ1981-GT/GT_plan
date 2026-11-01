<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'gt-fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>少数股东权益及损益明细表</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="toggleFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
        <el-button size="small" @click="$emit('open-formula', 'consol_minority')">ƒx 公式</el-button>
        <el-button size="small" @click="exportData">📤 导出数据</el-button>
        <el-button size="small" type="primary" @click="addRow">+ 新增行</el-button>
        <el-button size="small" type="danger" :disabled="!selectedRows.length" @click="batchDeleteRows">
          删除{{ selectedRows.length ? `(${selectedRows.length})` : '' }}
        </el-button>
        <el-button size="small" @click="$emit('save', tableRows)">💾 保存</el-button>
      </div>
    </div>
    <div class="ws-tip" v-show="!isFullscreen">
      <span>取数来源：
        <a class="ws-link" @click="$emit('goto-sheet', 'net_asset')">净资产表</a>(期末净资产/净利润) →
        <a class="ws-link" @click="$emit('goto-sheet', 'info')">基本信息表</a>(持股比例) →
        <a class="ws-link" @click="$emit('goto-sheet', 'elimination')">合并抵消分录</a>(少数股东权益抵消为<b>已审批分录</b>派生只读)。
        <b>可编辑覆盖，可增删行</b>。
      </span>
    </div>
    <el-alert v-if="elimEquityUnallocated !== 0" v-show="!isFullscreen" type="warning" :closable="false" class="ws-unalloc"
      :title="`有 ${fmt(elimEquityUnallocated)} 的少数股东权益抵销无法唯一归属到单家子企业，未计入上表逐企业列`" />
    <el-alert v-for="(w, i) in elimEquityWarnings" :key="i" v-show="!isFullscreen" type="info" :closable="false" class="ws-unalloc" :title="w" />
    <el-alert v-show="!isFullscreen" type="info" :closable="false" class="ws-unalloc"
      title="少数股东损益的抵消数需由分录明细提供，当前列不自动填充（按净资产×比例计算的少数股东损益仍自动给出）" />

    <el-table :data="tableRows" border size="small" class="ws-table"
      :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
      :max-height="isFullscreen ? 'calc(100vh - 100px)' : 'calc(100vh - 280px)'"
      :header-cell-style="headerStyle" :cell-style="cellStyle"
      show-summary :summary-method="getSummary"
      @selection-change="(_sel: any[]) => selectedRows = _sel">
      <el-table-column type="selection" width="36" fixed align="center" />
      <el-table-column prop="companyName" label="子企业" width="160" fixed show-overflow-tooltip />
      <el-table-column prop="parentRatio" label="母公司持股" width="90" align="right">
        <template #default="{ row }"><span>{{ row.parentRatio }}%</span></template>
      </el-table-column>
      <el-table-column prop="minorityRatio" label="少数股东比例" width="100" align="right">
        <template #default="{ row }"><span style="color: var(--gt-color-primary);font-weight:600">{{ row.minorityRatio }}%</span></template>
      </el-table-column>
      <el-table-column label="少数股东权益" align="center">
        <el-table-column prop="endNetAsset" label="期末净资产" width="120" align="right">
          <template #default="{ row }"><span>{{ fmt(row.endNetAsset) }}</span></template>
        </el-table-column>
        <el-table-column prop="minorityEquity" label="少数股东权益" width="120" align="right">
          <template #default="{ row }"><span class="ws-computed ws-bold">{{ fmt(row.minorityEquity) }}</span></template>
        </el-table-column>
        <el-table-column prop="elimMinorityEquity" label="抵消分录数" width="110" align="right">
          <template #default="{ row }"><span style="color: var(--gt-color-wheat)">{{ fmt(row.elimMinorityEquity) }}</span></template>
        </el-table-column>
        <el-table-column prop="equityDiff" label="差异" width="90" align="right">
          <template #default="{ row }">
            <span :class="n(row.equityDiff) !== 0 ? 'ws-diff-warn' : 'ws-computed'">{{ fmt(row.equityDiff) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="少数股东损益" align="center">
        <el-table-column prop="currentProfit" label="当期净利润" width="120" align="right">
          <template #default="{ row }"><span>{{ fmt(row.currentProfit) }}</span></template>
        </el-table-column>
        <el-table-column prop="minorityProfit" label="少数股东损益" width="120" align="right">
          <template #default="{ row }"><span class="ws-computed ws-bold">{{ fmt(row.minorityProfit) }}</span></template>
        </el-table-column>
        <el-table-column prop="elimMinorityProfit" label="抵消分录数" width="110" align="right">
          <template #default="{ row }"><span style="color: var(--gt-color-wheat)">{{ fmt(row.elimMinorityProfit) }}</span></template>
        </el-table-column>
        <el-table-column prop="profitDiff" label="差异" width="90" align="right">
          <template #default="{ row }">
            <span :class="n(row.profitDiff) !== 0 ? 'ws-diff-warn' : 'ws-computed'">{{ fmt(row.profitDiff) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="超额亏损" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.isExcessLoss" type="danger" size="small">超额</el-tag>
          <span v-else style="color: var(--gt-color-success)">—</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { confirmBatch } from '@/utils/confirm'
import { useFullscreen } from '@/composables/useFullscreen'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useExcelIO, type ExcelColumn } from '@/composables/useExcelIO'
import { splitPersistedProjectionRows } from '@/components/consolidation/composables/consolProjectionDraft'
import { POST_ELIM_ACCOUNT, type PostEliminationProjection } from '@/services/consolidationApi'
import { companyElimMap, unallocatedOf, warningsOf } from '@/components/consolidation/composables/consolPostElimView'

interface CompanyCol { name: string; code?: string; ratio: number }

const props = defineProps<{
  companies: CompanyCol[]
  netAssetData: any[]       // 净资产表数据
  equitySimDirect: any[]    // 模拟权益法
  // 服务端 canonical projection：少数股东权益（4501）逐企业抵销合计（approved 分录唯一真源）。
  // 少数股东损益侧无独立标准科目码，projection 不提供，损益抵消列不臆造（置 0 并提示）。
  projection: PostEliminationProjection | null
  initialRows?: any[]
}>()

const emit = defineEmits<{
  (e: 'save', data: any[]): void
  (e: 'draft-change', data: any[]): void
  (e: 'goto-sheet', key: string): void
  (e: 'open-formula', key: string): void
}>()

const { isFullscreen, toggleFullscreen } = useFullscreen()
const displayPrefs = useDisplayPrefsStore()
const fmt = (v: any) => displayPrefs.fmt(v)
const sheetRef = ref<HTMLElement | null>(null)
const selectedRows = ref<any[]>([])
const manualRows = reactive<any[]>([])

function emitDraft() {
  emit('draft-change', tableRows.value)
}

function addRow() {
  const nr = { companyName: '', parentRatio: 0, minorityRatio: 0, endNetAsset: 0, minorityEquity: 0, elimMinorityEquity: 0, equityDiff: 0, currentProfit: 0, minorityProfit: 0, elimMinorityProfit: 0, profitDiff: 0, isExcessLoss: false, _manual: true, _editable: true }
  if (selectedRows.value.length > 0) {
    const last = selectedRows.value[selectedRows.value.length - 1]
    const idx = manualRows.indexOf(last)
    if (idx >= 0) {
      manualRows.splice(idx + 1, 0, nr)
      emitDraft()
      return
    }
  }
  manualRows.push(nr)
  emitDraft()
}
async function batchDeleteRows() {
  if (!selectedRows.value.length) return
  try {
    await confirmBatch('删除', selectedRows.value.length)
    const del = new Set(selectedRows.value)
    const remaining = manualRows.filter(r => !del.has(r))
    manualRows.length = 0; manualRows.push(...remaining)
    selectedRows.value = []
    emitDraft()
  } catch {}
}
const n = (v: any) => Number(v) || 0

const overrides = reactive<Record<string, Record<string, any>>>({})

function hydratePersistedRows() {
  const hydrated = splitPersistedProjectionRows(props.companies, props.initialRows)
  for (const key of Object.keys(overrides)) delete overrides[key]
  Object.assign(overrides, hydrated.overrides)
  manualRows.length = 0
  manualRows.push(...hydrated.manualRows)
}
watch([() => props.initialRows, () => props.companies], hydratePersistedRows, { deep: true, immediate: true })

// 少数股东权益（4501）抵销：企业代码 → 逐企业合计（projection 真源）
const elimEquityByCompany = computed(() => companyElimMap(props.projection, POST_ELIM_ACCOUNT.minorityEquity))
const elimEquityUnallocated = computed(() => unallocatedOf(props.projection, POST_ELIM_ACCOUNT.minorityEquity))
const elimEquityWarnings = computed(() => warningsOf(props.projection, POST_ELIM_ACCOUNT.minorityEquity))

const { exportData: _exportData } = useExcelIO()

const MINORITY_COLS: ExcelColumn[] = [
  { key: 'companyName', header: '子企业' },
  { key: 'parentRatio', header: '母公司持股' },
  { key: 'minorityRatio', header: '少数股东比例' },
  { key: 'endNetAsset', header: '期末净资产' },
  { key: 'minorityEquity', header: '少数股东权益' },
  { key: 'elimMinorityEquity', header: '抵消分录数(权益)' },
  { key: 'equityDiff', header: '权益差异' },
  { key: 'currentProfit', header: '当期净利润' },
  { key: 'minorityProfit', header: '少数股东损益' },
  { key: 'elimMinorityProfit', header: '抵消分录数(损益)' },
  { key: 'profitDiff', header: '损益差异' },
]

async function exportData() {
  const data = tableRows.value.map((r: any) => ({
    ...r,
    isExcessLoss: r.isExcessLoss ? '是' : '否',
  }))
  await _exportData({
    data,
    columns: [...MINORITY_COLS, { key: 'isExcessLoss', header: '超额亏损' }],
    sheetName: '少数股东权益损益',
    fileName: '少数股东权益损益_数据.xlsx',
  })
}

const tableRows = computed(() => {
  const automaticRows = props.companies.map((comp, ci) => {
    const parentRatio = comp.ratio
    const minorityRatio = Math.round((100 - parentRatio) * 100) / 100

    // 期末净资产（从净资产表取"期末金额"行的该企业列值）
    const endRow = props.netAssetData.find((r: any) => r.item === '期末金额' && r.bold && r.isComputed)
    const endNetAsset = endRow?.values?.[ci] != null ? n(endRow.values[ci]) : 0

    // 少数股东权益 = 期末净资产 × 少数股东比例
    const minorityEquity = Math.round(endNetAsset * minorityRatio) / 100

    // 少数股东权益（4501）抵销：服务端 canonical projection 逐企业合计（approved 分录真源）
    const elimMinorityEquity = elimEquityByCompany.value.get(comp.code || comp.name) ?? 0
    const equityDiff = minorityEquity - elimMinorityEquity

    // 当期净利润（从净资产表取"综合收益总额"或"当期归母净利润"行）
    const profitRow = props.netAssetData.find((r: any) => r.item === '（一）综合收益总额')
    const currentProfit = profitRow?.values?.[ci] != null ? n(profitRow.values[ci]) : 0

    // 少数股东损益 = 当期净利润 × 少数股东比例
    const minorityProfit = Math.round(currentProfit * minorityRatio) / 100

    // 少数股东损益侧无独立标准科目码，canonical projection 不提供 ⇒ 不臆造，置 0（由分录明细另行支持）
    const elimMinorityProfit = 0
    const profitDiff = minorityProfit - elimMinorityProfit

    // 超额亏损判断
    const isExcessLoss = endNetAsset < 0 && minorityEquity < 0

    const ov = overrides[comp.name] || {}
    const result: any = {
      companyName: comp.name, parentRatio, minorityRatio,
      endNetAsset, minorityEquity, elimMinorityEquity, equityDiff,
      currentProfit, minorityProfit, elimMinorityProfit, profitDiff,
      isExcessLoss, _editable: true,
    }
    for (const k of Object.keys(ov)) { if (ov[k] != null) result[k] = ov[k] }
    return result
  })
  return [...automaticRows, ...manualRows]
})

const headerStyle = { background: '#f0edf5', fontSize: '11px', color: '#333', padding: '3px 0' }
const cellStyle = { padding: '4px 8px', fontSize: '12px' }

function getSummary({ columns, data }: any) {
  const sums: string[] = []
  const sumFields = new Set(['endNetAsset','minorityEquity','elimMinorityEquity','equityDiff','currentProfit','minorityProfit','elimMinorityProfit','profitDiff'])
  columns.forEach((col: any, idx: number) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    const prop = col.property
    if (prop && sumFields.has(prop)) { sums[idx] = fmt(data.reduce((s: number, r: any) => s + n(r[prop]), 0)) }
    else { sums[idx] = '' }
  })
  return sums
}


</script>

<style scoped>
.ws-sheet { padding: 0; position: relative; }
.ws-sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.ws-sheet-header h3 { margin: 0; font-size: var(--gt-font-size-base); color: var(--gt-color-text-primary); }
.ws-sheet-actions { display: flex; gap: 8px; }
.ws-tip { display: flex; align-items: flex-start; gap: 6px; padding: 6px 10px; margin-bottom: 10px; background: var(--gt-color-bg); border-radius: 6px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); line-height: 1.5; }
.ws-computed { color: var(--gt-color-primary); font-weight: 500; }
.ws-bold { font-weight: 700; }
.ws-diff-warn { color: var(--gt-color-wheat) !important; font-weight: 700 !important; }
.ws-table :deep(.el-table__footer-wrapper td) { background: var(--gt-color-primary-bg) !important; font-weight: 700; color: var(--gt-color-primary); }
</style>

<style>
.ws-link { color: var(--gt-color-primary); cursor: pointer; text-decoration: underline; font-weight: 500; }
.ws-link:hover { color: var(--gt-color-primary); }
</style>
