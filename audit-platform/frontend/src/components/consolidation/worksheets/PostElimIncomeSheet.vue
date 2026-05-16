<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'gt-fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>抵消后投资收益明细表</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="toggleFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
        <el-button size="small" @click="$emit('open-formula', 'consol_post_income')">ƒx 公式</el-button>
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
        <a class="ws-link" @click="$emit('goto-sheet', 'cost')">投资明细-成本法</a>(现金红利) →
        <a class="ws-link" @click="$emit('goto-sheet', 'equity_sim')">模拟权益法</a>(投资收益/还原分红) →
        <a class="ws-link" @click="$emit('goto-sheet', 'elimination')">合并抵消分录</a>(抵消投资收益)。
        <b>可编辑覆盖，可增删行</b>。
      </span>
    </div>

    <el-table :data="tableRows" border size="small" class="ws-table"
      :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
      :max-height="isFullscreen ? 'calc(100vh - 100px)' : 'calc(100vh - 280px)'"
      :header-cell-style="headerStyle" :cell-style="cellStyle"
      show-summary :summary-method="getSummary"
      @selection-change="(_sel: any[]) => selectedRows = _sel">
      <el-table-column type="selection" width="36" fixed align="center" />
      <el-table-column prop="companyName" label="子企业" width="160" fixed show-overflow-tooltip />
      <el-table-column prop="ratio" label="持股比例" width="80" align="right">
        <template #default="{ row }"><span>{{ row.ratio }}%</span></template>
      </el-table-column>
      <el-table-column prop="bookDividend" label="账面现金红利" width="110" align="right">
        <template #default="{ row }"><span>{{ fmt(row.bookDividend) }}</span></template>
      </el-table-column>
      <el-table-column prop="simInvestIncome" label="模拟投资收益" width="110" align="right">
        <template #default="{ row }"><span class="ws-computed">{{ fmt(row.simInvestIncome) }}</span></template>
      </el-table-column>
      <el-table-column prop="dividendReverse" label="还原分红" width="100" align="right">
        <template #default="{ row }"><span style="color: var(--gt-color-wheat)">{{ fmt(row.dividendReverse) }}</span></template>
      </el-table-column>
      <el-table-column prop="elimInvestIncome" label="抵消投资收益" width="110" align="right">
        <template #default="{ row }"><span style="color: var(--gt-color-wheat)">{{ fmt(row.elimInvestIncome) }}</span></template>
      </el-table-column>
      <el-table-column prop="postElimIncome" label="抵消后投资收益" width="130" align="right">
        <template #default="{ row }">
          <span :class="n(row.postElimIncome) !== 0 ? 'ws-diff-warn ws-bold' : 'ws-computed'">{{ fmt(row.postElimIncome) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="checkResult" label="校验" width="50" align="center">
        <template #default="{ row }">
          <span v-if="n(row.postElimIncome) === 0" style="color: var(--gt-color-success)">✓</span>
          <span v-else style="color: var(--gt-color-wheat)">⚠</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { confirmBatch } from '@/utils/confirm'
import { useFullscreen } from '@/composables/useFullscreen'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useExcelIO, type ExcelColumn } from '@/composables/useExcelIO'

interface CompanyCol { name: string; code?: string; ratio: number }

const props = defineProps<{
  companies: CompanyCol[]
  investmentCost: any[]
  equitySimDirect: any[]
  elimIncome: any[]
}>()

defineEmits<{ (e: 'save', data: any): void; (e: 'goto-sheet', key: string): void; (e: 'open-formula', key: string): void }>()

const { isFullscreen, toggleFullscreen } = useFullscreen()
const displayPrefs = useDisplayPrefsStore()
const fmt = (v: any) => displayPrefs.fmt(v)
const sheetRef = ref<HTMLElement | null>(null)
const selectedRows = ref<any[]>([])
const manualRows = reactive<any[]>([])

function addRow() {
  const nr = { companyName: '', ratio: 0, bookDividend: 0, simInvestIncome: 0, dividendReverse: 0, elimInvestIncome: 0, postElimIncome: 0, _manual: true, _editable: true }
  if (selectedRows.value.length > 0) {
    const last = selectedRows.value[selectedRows.value.length - 1]
    const idx = manualRows.indexOf(last)
    if (idx >= 0) { manualRows.splice(idx + 1, 0, nr); return }
  }
  manualRows.push(nr)
}
async function batchDeleteRows() {
  if (!selectedRows.value.length) return
  try { await confirmBatch('删除', selectedRows.value.length)
    const del = new Set(selectedRows.value); const remaining = manualRows.filter(r => !del.has(r)); manualRows.length = 0; manualRows.push(...remaining); selectedRows.value = []
  } catch {}
}
const n = (v: any) => Number(v) || 0

const overrides = reactive<Record<string, Record<string, number | null>>>({})

const { exportData: _exportData } = useExcelIO()

const INCOME_COLS: ExcelColumn[] = [
  { key: 'companyName', header: '子企业' },
  { key: 'ratio', header: '持股比例' },
  { key: 'bookDividend', header: '账面现金红利' },
  { key: 'simInvestIncome', header: '模拟投资收益' },
  { key: 'dividendReverse', header: '还原分红' },
  { key: 'elimInvestIncome', header: '抵消投资收益' },
  { key: 'postElimIncome', header: '抵消后投资收益' },
]

async function exportData() {
  await _exportData({
    data: tableRows.value,
    columns: INCOME_COLS,
    sheetName: '抵消后投资收益',
    fileName: '抵消后投资收益_数据.xlsx',
  })
}

const tableRows = computed(() => {
  return props.companies.map((comp, ci) => {
    // 账面现金红利
    const costRow = props.investmentCost.find((r: any) => r.company_name === comp.name || r.company_code === comp.code)
    const bookDividend = n(costRow?.current_dividend)

    // 模拟投资收益（从模拟权益法的"投资收益"贷方行取值）
    const simIncomeRow = props.equitySimDirect.find((r: any) => r.subject === '投资收益' && !r.isStep && r.detail === '')
    const simInvestIncome = simIncomeRow?.values?.[ci] != null ? n(simIncomeRow.values[ci]) : 0

    // 还原分红（模拟权益法第3步的投资收益借方）
    const dividendRows = props.equitySimDirect.filter((r: any) => r.subject === '投资收益' && !r.isStep)
    // 第3步的投资收益（还原分红影响）通常是第二个投资收益行
    const dividendReverse = dividendRows.length > 1 ? n(dividendRows[1]?.values?.[ci] || dividendRows[1]?.total) : 0

    // 合并抵消的投资收益
    const elimRow = props.elimIncome.find((r: any) => r.subject === '投资收益')
    const elimInvestIncome = elimRow?.values?.[ci] != null ? n(elimRow.values[ci]) : 0

    // 抵消后 = 账面红利 + 模拟投资收益 - 还原分红 - 抵消投资收益
    const postElimIncome = bookDividend + simInvestIncome - dividendReverse - elimInvestIncome

    const ov = overrides[comp.name] || {}
    const result: any = { companyName: comp.name, ratio: comp.ratio, bookDividend, simInvestIncome, dividendReverse, elimInvestIncome, postElimIncome, _editable: true }
    for (const k of Object.keys(ov)) { if (ov[k] != null) result[k] = ov[k] }
    return result
  })
})

const headerStyle = { background: '#f0edf5', fontSize: '11px', color: '#333', padding: '3px 0' }
const cellStyle = { padding: '4px 8px', fontSize: '12px' }

function getSummary({ columns, data }: any) {
  const sums: string[] = []
  const sumFields = new Set(['bookDividend','simInvestIncome','dividendReverse','elimInvestIncome','postElimIncome'])
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
