<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'ws-sheet--fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>抵消后投资收益明细表</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="isFullscreen = !isFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
        <el-button size="small" @click="$emit('save', tableRows)">💾 保存</el-button>
      </div>
    </div>
    <div class="ws-tip" v-show="!isFullscreen">
      <span>自动汇总：各家账面投资收益 + 权益法模拟投资收益 - 还原分红 - 合并抵消投资收益 = 抵消后投资收益（合并利润表列示数）。</span>
    </div>

    <el-table :data="tableRows" border size="small" class="ws-table"
      :max-height="isFullscreen ? 'calc(100vh - 100px)' : 'calc(100vh - 280px)'"
      :header-cell-style="headerStyle" :cell-style="cellStyle"
      show-summary :summary-method="getSummary">
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
        <template #default="{ row }"><span style="color:#e6a23c">{{ fmt(row.dividendReverse) }}</span></template>
      </el-table-column>
      <el-table-column prop="elimInvestIncome" label="抵消投资收益" width="110" align="right">
        <template #default="{ row }"><span style="color:#e6a23c">{{ fmt(row.elimInvestIncome) }}</span></template>
      </el-table-column>
      <el-table-column prop="postElimIncome" label="抵消后投资收益" width="130" align="right">
        <template #default="{ row }">
          <span :class="n(row.postElimIncome) !== 0 ? 'ws-diff-warn ws-bold' : 'ws-computed'">{{ fmt(row.postElimIncome) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="checkResult" label="校验" width="50" align="center">
        <template #default="{ row }">
          <span v-if="n(row.postElimIncome) === 0" style="color:#67c23a">✓</span>
          <span v-else style="color:#e6a23c">⚠</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'

interface CompanyCol { name: string; code?: string; ratio: number }

const props = defineProps<{
  companies: CompanyCol[]
  investmentCost: any[]
  equitySimDirect: any[]
  elimIncome: any[]
}>()

defineEmits<{ (e: 'save', data: any): void }>()

const isFullscreen = ref(false)
const sheetRef = ref<HTMLElement | null>(null)
const n = (v: any) => Number(v) || 0

const overrides = reactive<Record<string, Record<string, number | null>>>({})

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

function fmt(v: any) { if (v == null) return '-'; const num = Number(v); return isNaN(num) ? '-' : num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
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
.ws-bold { font-weight: 700; }
.ws-diff-warn { color: #e6a23c !important; font-weight: 700 !important; }
.ws-table :deep(.el-table__footer-wrapper td) { background: #f8f6fb !important; font-weight: 700; color: #4b2d77; }
</style>
