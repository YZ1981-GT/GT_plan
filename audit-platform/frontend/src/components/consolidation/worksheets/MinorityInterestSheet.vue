<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'ws-sheet--fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>少数股东权益及损益明细表</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="isFullscreen = !isFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
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
        <a class="ws-link" @click="$emit('goto-sheet', 'elimination')">合并抵消分录</a>(少数股东权益/损益)。
        <b>可编辑覆盖，可增删行</b>。
      </span>
    </div>

    <el-table :data="tableRows" border size="small" class="ws-table"
      :max-height="isFullscreen ? 'calc(100vh - 100px)' : 'calc(100vh - 280px)'"
      :header-cell-style="headerStyle" :cell-style="cellStyle"
      show-summary :summary-method="getSummary"
      @selection-change="sel => selectedRows = sel">
      <el-table-column type="selection" width="36" fixed align="center" />
      <el-table-column prop="companyName" label="子企业" width="160" fixed show-overflow-tooltip />
      <el-table-column prop="parentRatio" label="母公司持股" width="90" align="right">
        <template #default="{ row }"><span>{{ row.parentRatio }}%</span></template>
      </el-table-column>
      <el-table-column prop="minorityRatio" label="少数股东比例" width="100" align="right">
        <template #default="{ row }"><span style="color:#4b2d77;font-weight:600">{{ row.minorityRatio }}%</span></template>
      </el-table-column>
      <el-table-column label="少数股东权益" align="center">
        <el-table-column prop="endNetAsset" label="期末净资产" width="120" align="right">
          <template #default="{ row }"><span>{{ fmt(row.endNetAsset) }}</span></template>
        </el-table-column>
        <el-table-column prop="minorityEquity" label="少数股东权益" width="120" align="right">
          <template #default="{ row }"><span class="ws-computed ws-bold">{{ fmt(row.minorityEquity) }}</span></template>
        </el-table-column>
        <el-table-column prop="elimMinorityEquity" label="抵消分录数" width="110" align="right">
          <template #default="{ row }"><span style="color:#e6a23c">{{ fmt(row.elimMinorityEquity) }}</span></template>
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
          <template #default="{ row }"><span style="color:#e6a23c">{{ fmt(row.elimMinorityProfit) }}</span></template>
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
          <span v-else style="color:#67c23a">—</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessageBox } from 'element-plus'

interface CompanyCol { name: string; code?: string; ratio: number }

const props = defineProps<{
  companies: CompanyCol[]
  netAssetData: any[]       // 净资产表数据
  equitySimDirect: any[]    // 模拟权益法
  elimEquity: any[]         // 合并抵消-权益
  elimIncome: any[]         // 合并抵消-损益
}>()

defineEmits<{ (e: 'save', data: any): void; (e: 'goto-sheet', key: string): void }>()

const isFullscreen = ref(false)
const sheetRef = ref<HTMLElement | null>(null)
const selectedRows = ref<any[]>([])
const manualRows = reactive<any[]>([])

function addRow() {
  const nr = { companyName: '', parentRatio: 0, minorityRatio: 0, endNetAsset: 0, minorityEquity: 0, elimMinorityEquity: 0, equityDiff: 0, currentProfit: 0, minorityProfit: 0, elimMinorityProfit: 0, profitDiff: 0, isExcessLoss: false, _manual: true, _editable: true }
  if (selectedRows.value.length > 0) {
    const last = selectedRows.value[selectedRows.value.length - 1]
    const idx = manualRows.indexOf(last)
    if (idx >= 0) { manualRows.splice(idx + 1, 0, nr); return }
  }
  manualRows.push(nr)
}
async function batchDeleteRows() {
  if (!selectedRows.value.length) return
  try { await ElMessageBox.confirm(`确定删除 ${selectedRows.value.length} 行？`, '删除确认', { type: 'warning' })
    const del = new Set(selectedRows.value); const remaining = manualRows.filter(r => !del.has(r)); manualRows.length = 0; manualRows.push(...remaining); selectedRows.value = []
  } catch {}
}
const n = (v: any) => Number(v) || 0

const overrides = reactive<Record<string, Record<string, number | null>>>({})

const tableRows = computed(() => {
  return props.companies.map((comp, ci) => {
    const parentRatio = comp.ratio
    const minorityRatio = Math.round((100 - parentRatio) * 100) / 100

    // 期末净资产（从净资产表取"期末金额"行的该企业列值）
    const endRow = props.netAssetData.find((r: any) => r.item === '期末金额' && r.bold && r.isComputed)
    const endNetAsset = endRow?.values?.[ci] != null ? n(endRow.values[ci]) : 0

    // 少数股东权益 = 期末净资产 × 少数股东比例
    const minorityEquity = Math.round(endNetAsset * minorityRatio) / 100

    // 从抵消分录取少数股东权益
    const elimEqRow = props.elimEquity.find((r: any) => r.subject === '少数股东权益')
    const elimMinorityEquity = elimEqRow?.values?.[ci] != null ? n(elimEqRow.values[ci]) : 0
    const equityDiff = minorityEquity - elimMinorityEquity

    // 当期净利润（从净资产表取"综合收益总额"或"当期归母净利润"行）
    const profitRow = props.netAssetData.find((r: any) => r.item === '（一）综合收益总额')
    const currentProfit = profitRow?.values?.[ci] != null ? n(profitRow.values[ci]) : 0

    // 少数股东损益 = 当期净利润 × 少数股东比例
    const minorityProfit = Math.round(currentProfit * minorityRatio) / 100

    // 从抵消分录取少数股权损益
    const elimIncRow = props.elimIncome.find((r: any) => r.subject === '少数股权损益')
    const elimMinorityProfit = elimIncRow?.values?.[ci] != null ? n(elimIncRow.values[ci]) : 0
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
})

function fmt(v: any) { if (v == null) return '-'; const num = Number(v); return isNaN(num) ? '-' : num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
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

<style>
.ws-link { color: #4b2d77; cursor: pointer; text-decoration: underline; font-weight: 500; }
.ws-link:hover { color: #7c5caa; }
</style>
