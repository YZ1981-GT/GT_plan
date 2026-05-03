<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'ws-sheet--fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>抵消后长期股权投资明细表</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="isFullscreen = !isFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
        <el-button size="small" @click="$emit('open-formula', 'consol_post_invest')">ƒx 公式</el-button>
        <el-button size="small" @click="$emit('save', tableRows)">💾 保存</el-button>
      </div>
    </div>
    <div class="ws-tip" v-show="!isFullscreen">
      <span>自动汇总：各家账面长投 + 权益法模拟调整 - 合并抵消 = 抵消后长投（合并报表列示数）。全资子公司抵消后应为0。数据来源于投资明细表、模拟权益法表和合并抵消分录表。</span>
    </div>

    <el-table :data="tableRows" border size="small" class="ws-table"
      :max-height="isFullscreen ? 'calc(100vh - 100px)' : 'calc(100vh - 280px)'"
      :header-cell-style="headerStyle" :cell-style="rowCellStyle" :row-class-name="rowClassName"
      show-summary :summary-method="getSummary">
      <el-table-column prop="companyName" label="子企业" width="160" fixed show-overflow-tooltip />
      <el-table-column prop="ratio" label="持股比例" width="80" align="right">
        <template #default="{ row }"><span>{{ row.ratio }}%</span></template>
      </el-table-column>
      <el-table-column label="账面长投" align="center">
        <el-table-column prop="bookCost" label="投资成本" width="110" align="right">
          <template #default="{ row }"><span>{{ fmt(row.bookCost) }}</span></template>
        </el-table-column>
        <el-table-column prop="bookImpairment" label="减值准备" width="100" align="right">
          <template #default="{ row }"><span>{{ fmt(row.bookImpairment) }}</span></template>
        </el-table-column>
        <el-table-column prop="bookNet" label="账面净额" width="110" align="right">
          <template #default="{ row }"><span class="ws-computed">{{ fmt(row.bookNet) }}</span></template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="权益法模拟调整" align="center">
        <el-table-column prop="simIncomeAdj" label="损益调整" width="100" align="right">
          <template #default="{ row }"><span>{{ fmt(row.simIncomeAdj) }}</span></template>
        </el-table-column>
        <el-table-column prop="simOtherEquity" label="其他权益变动" width="100" align="right">
          <template #default="{ row }"><span>{{ fmt(row.simOtherEquity) }}</span></template>
        </el-table-column>
        <el-table-column prop="simTotal" label="模拟后长投" width="110" align="right">
          <template #default="{ row }"><span class="ws-computed ws-bold">{{ fmt(row.simTotal) }}</span></template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="合并抵消" align="center">
        <el-table-column prop="elimCost" label="投资成本" width="110" align="right">
          <template #default="{ row }"><span style="color:#e6a23c">{{ fmt(row.elimCost) }}</span></template>
        </el-table-column>
        <el-table-column prop="elimIncomeAdj" label="损益调整" width="100" align="right">
          <template #default="{ row }"><span style="color:#e6a23c">{{ fmt(row.elimIncomeAdj) }}</span></template>
        </el-table-column>
        <el-table-column prop="elimOtherEquity" label="其他权益变动" width="100" align="right">
          <template #default="{ row }"><span style="color:#e6a23c">{{ fmt(row.elimOtherEquity) }}</span></template>
        </el-table-column>
        <el-table-column prop="elimTotal" label="抵消合计" width="110" align="right">
          <template #default="{ row }"><span style="color:#e6a23c;font-weight:600">{{ fmt(row.elimTotal) }}</span></template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="抵消后" align="center">
        <el-table-column prop="postElimTotal" label="抵消后长投" width="120" align="right">
          <template #default="{ row }">
            <span :class="n(row.postElimTotal) !== 0 ? 'ws-diff-warn ws-bold' : 'ws-computed'">{{ fmt(row.postElimTotal) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="checkResult" label="校验" width="60" align="center">
          <template #default="{ row }">
            <span v-if="n(row.postElimTotal) === 0" style="color:#67c23a">✓</span>
            <span v-else style="color:#e6a23c">⚠</span>
          </template>
        </el-table-column>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

interface CompanyCol { name: string; code?: string; ratio: number }
interface InvestRow { company_name: string; company_code: string; open_cost: number|null; open_impairment: number|null; [k: string]: any }
interface EquitySimRow { seq: string; subject: string; detail: string; total: number|null; values?: (number|null)[]; isStep?: boolean; isComputed?: boolean }
interface ElimRow { direction: string; subject: string; detail?: string; values?: (number|null)[] }

const props = defineProps<{
  companies: CompanyCol[]
  investmentCost: InvestRow[]       // 成本法投资明细
  investmentEquity: InvestRow[]     // 权益法投资明细
  equitySimDirect: EquitySimRow[]   // 模拟权益法直接持股
  elimEquity: ElimRow[]             // 合并抵消-权益抵消
}>()

defineEmits<{ (e: 'save', data: any): void; (e: 'open-formula', key: string): void }>()

const isFullscreen = ref(false)
const sheetRef = ref<HTMLElement | null>(null)
const n = (v: any) => Number(v) || 0

// 逐家计算
const tableRows = computed(() => {
  return props.companies.map((comp, ci) => {
    // 1. 账面长投（从投资明细表取期末数）
    const costRow = props.investmentCost.find(r => r.company_name === comp.name || r.company_code === comp.code)
    const equityRow = props.investmentEquity.find(r => r.company_name === comp.name || r.company_code === comp.code)
    const bookCost = n(costRow?.open_cost) + n(costRow?.add_cost) - n(costRow?.reduce_cost)
      + n(equityRow?.open_amount) + n(equityRow?.add_cost) - n(equityRow?.reduce_cost)
    const bookImpairment = n(costRow?.open_impairment) + n(costRow?.add_impairment) - n(costRow?.reduce_impairment)
      + n(equityRow?.open_impairment) + n(equityRow?.add_impairment) - n(equityRow?.reduce_impairment)
    const bookNet = bookCost - bookImpairment

    // 2. 权益法模拟调整（从模拟权益法表取该企业列的损益调整和其他权益变动）
    const findSimVal = (detail: string) => {
      // 找"模拟后长投"区域的对应行
      const startIdx = props.equitySimDirect.findIndex(r => r.subject === '长期股权投资' && r.detail === '投资成本' &&
        props.equitySimDirect.indexOf(r) > (props.equitySimDirect.length - 10))
      if (startIdx < 0) return 0
      const row = props.equitySimDirect.find((r, idx) => idx >= startIdx && r.detail === detail)
      return row?.values?.[ci] != null ? n(row.values[ci]) : n(row?.total)
    }
    const simIncomeAdj = findSimVal('损益调整')
    const simOtherEquity = findSimVal('其他权益变动')
    const simTotal = bookNet + simIncomeAdj + simOtherEquity

    // 3. 合并抵消（从抵消分录表取该企业列）
    const findElimVal = (subject: string, detail?: string) => {
      const row = props.elimEquity.find(r => r.subject === subject && (!detail || r.detail === detail))
      return row?.values?.[ci] != null ? n(row.values[ci]) : 0
    }
    const elimCost = findElimVal('长期股权投资', '投资成本')
    const elimIncomeAdj = findElimVal('长期股权投资', '损益调整')
    const elimOtherEquity = findElimVal('长期股权投资', '其他权益变动')
    const elimTotal = elimCost + elimIncomeAdj + elimOtherEquity

    // 4. 抵消后 = 模拟后长投 - 合并抵消
    const postElimTotal = simTotal - elimTotal

    return {
      companyName: comp.name, companyCode: comp.code, ratio: comp.ratio,
      bookCost, bookImpairment, bookNet,
      simIncomeAdj, simOtherEquity, simTotal,
      elimCost, elimIncomeAdj, elimOtherEquity, elimTotal,
      postElimTotal,
    }
  })
})

function fmt(v: any) { if (v == null) return '-'; const num = Number(v); return isNaN(num) ? '-' : num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function calcCls(v: any) { return n(v) === 0 ? 'ws-computed ws-zero' : 'ws-computed' }

const headerStyle = { background: '#f0edf5', fontSize: '11px', color: '#333', padding: '3px 0' }
function rowCellStyle() { return { padding: '4px 8px', fontSize: '12px' } }
function rowClassName({ row }: any) { return n(row.postElimTotal) !== 0 ? 'ws-row-warn' : '' }

function getSummary({ columns, data }: any) {
  const sums: string[] = []
  const sumFields = new Set(['bookCost','bookImpairment','bookNet','simIncomeAdj','simOtherEquity','simTotal',
    'elimCost','elimIncomeAdj','elimOtherEquity','elimTotal','postElimTotal'])
  columns.forEach((col: any, idx: number) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    const prop = col.property
    if (prop && sumFields.has(prop)) {
      const total = data.reduce((s: number, r: any) => s + n(r[prop]), 0)
      sums[idx] = fmt(total)
    } else { sums[idx] = '' }
  })
  return sums
}

function onEsc(e: KeyboardEvent) { if (e.key === 'Escape' && isFullscreen.value) isFullscreen.value = false }
onMounted(() => document.addEventListener('keydown', onEsc))
onUnmounted(() => document.removeEventListener('keydown', onEsc))
</script>

<style scoped>
.ws-sheet { padding: 0; position: relative; }
.ws-sheet--fullscreen { position: fixed !important; top: 0; left: 0; right: 0; bottom: 0; z-index: 2000; background: #fff; padding: 16px; overflow: auto; }
.ws-sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.ws-sheet-header h3 { margin: 0; font-size: 15px; color: #333; }
.ws-sheet-actions { display: flex; gap: 8px; }
.ws-tip { display: flex; align-items: flex-start; gap: 6px; padding: 6px 10px; margin-bottom: 10px; background: #f4f4f5; border-radius: 6px; font-size: 12px; color: #666; line-height: 1.5; }
.ws-computed { color: #4b2d77; font-weight: 500; }
.ws-zero { color: #c0c4cc !important; font-weight: 400 !important; }
.ws-bold { font-weight: 700; }
.ws-diff-warn { color: #e6a23c !important; font-weight: 700 !important; }
.ws-table :deep(.ws-row-warn td) { background: #fdf6ec !important; }
.ws-table :deep(.el-table__footer-wrapper td) { background: #f8f6fb !important; font-weight: 700; color: #4b2d77; }
</style>
