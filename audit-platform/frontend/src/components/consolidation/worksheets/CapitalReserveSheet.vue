<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'ws-sheet--fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>资本公积变动核查表</h3>
      <p class="ws-subtitle">从合并抵消分录按科目提取，核查资本公积勾稽关系</p>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="isFullscreen = !isFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
        <el-button size="small" @click="$emit('open-formula', 'consol_capital')">ƒx 公式</el-button>
        <el-button size="small" type="warning" @click="extractFromElimination">🔄 从抵消分录提取</el-button>
        <el-button size="small" @click="$emit('save', tableData)">💾 保存</el-button>
      </div>
    </div>

    <el-table :data="tableData" border size="small" class="ws-table" max-height="calc(100vh - 300px)"
      :header-cell-style="headerStyle" :cell-style="cellStyle" :row-class-name="rowClassName">
      <el-table-column prop="item" label="资本公积" width="200" fixed show-overflow-tooltip>
        <template #default="{ row }">
          <span :style="{ fontWeight: row.bold ? 700 : 400, color: row.isDiff ? '#e6a23c' : '' }">{{ row.item }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="total" label="合计" width="120" align="right">
        <template #default="{ row }">
          <span class="ws-auto-cell" style="display:block;text-align:right;padding:2px 8px;color:#4b2d77;font-weight:500;font-size:12px"
            :class="{ 'ws-bold': row.bold }">
            {{ fmt(calcCapitalTotal(row)) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="elimAdj" label="合并抵消环节" width="140" align="right">
        <template #default="{ row }">
          <span v-if="row.isComputed || row.fromElim" class="ws-computed">{{ fmt(row.elimAdj) }}</span>
          <el-input-number v-else v-model="row.elimAdj" size="small" :precision="2" :controls="false" style="width:100%" />
        </template>
      </el-table-column>
      <el-table-column prop="parentVal" label="母公司" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!row.isComputed" v-model="row.parentVal" size="small" :precision="2" :controls="false" style="width:100%" />
          <span v-else class="ws-computed">{{ fmt(row.parentVal) }}</span>
        </template>
      </el-table-column>
      <!-- 动态子企业列 -->
      <el-table-column v-for="(c, ci) in companies" :key="ci" align="center" min-width="120">
        <template #header>
          <div style="text-align:center;line-height:1.3">
            <div style="font-weight:600">{{ c.name }}</div>
            <div style="color:#4b2d77;font-size:10px">{{ c.ratio }}%</div>
          </div>
        </template>
        <template #default="{ row }">
          <el-input-number v-if="!row.isComputed && row.values" v-model="row.values[ci]" size="small" :precision="2" :controls="false" style="width:100%" />
          <span v-else-if="row.isComputed && row.values" class="ws-computed">{{ fmt(row.values?.[ci]) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 差异核查 -->
    <div class="ws-check-area">
      <div class="ws-check-row">
        <span>期末合并报表金额:</span>
        <el-input-number v-model="consolReportAmount" size="small" :precision="2" :controls="false" style="width:160px" />
        <small style="color:#999">取自合并后财务报表期末数</small>
      </div>
      <div class="ws-check-row" :class="{ 'ws-diff-warn': diffAmount !== 0 }">
        <span>差异:</span>
        <span class="ws-computed ws-bold">{{ fmt(diffAmount) }}</span>
        <span v-if="diffAmount === 0" style="color:#67c23a">✓ 无差异</span>
        <span v-else style="color:#e6a23c">⚠ 存在差异，请核查</span>
      </div>
    </div>

    <!-- 合并抵消环节调整事项 -->
    <div class="ws-adj-section">
      <div class="ws-section-title">合并抵消环节调整事项</div>
      <el-table :data="adjItems" border size="small" class="ws-table">
        <el-table-column type="index" label="序号" width="50" align="center" />
        <el-table-column prop="description" label="调整事项说明" min-width="300">
          <template #default="{ row }">
            <el-input v-model="row.description" size="small" placeholder="输入调整事项" />
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="金额" width="150" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.amount" size="small" :precision="2" :controls="false" style="width:100%" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" @click="adjItems.splice($index, 1)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-button size="small" style="margin-top:6px" @click="adjItems.push({ description: '', amount: null })">+ 新增调整事项</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'

interface CompanyCol { name: string; ratio: number }

interface CapitalReserveRow {
  item: string; total: number | null; elimAdj: number | null; parentVal: number | null
  values?: (number | null)[]; bold?: boolean; isComputed?: boolean; fromElim?: boolean
  isDiff?: boolean; note?: string
}

interface AdjItem { description: string; amount: number | null }

const props = defineProps<{
  companies: CompanyCol[]
  modelValue: CapitalReserveRow[]
  eliminationData?: any // 从合并抵消分录传入的数据
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: CapitalReserveRow[]): void
  (e: 'save', v: CapitalReserveRow[]): void
  (e: 'open-formula', sheetKey: string): void
}>()

const isFullscreen = ref(false)
const sheetRef = ref<HTMLElement | null>(null)

const companies = ref(props.companies)
const tableData = ref<CapitalReserveRow[]>([...props.modelValue])
const consolReportAmount = ref<number | null>(null)
const adjItems = ref<AdjItem[]>([
  { description: '', amount: null },
  { description: '', amount: null },
])

watch(() => props.companies, (v) => { companies.value = v })
watch(() => props.modelValue, (v) => { tableData.value = [...v] }, { deep: true })
watch(tableData, (v) => { emit('update:modelValue', v) }, { deep: true })

// 期末金额行
const endRow = computed(() => tableData.value.find(r => r.item === '期末金额'))
const diffAmount = computed(() => {
  if (consolReportAmount.value == null || !endRow.value) return 0
  return (endRow.value.total || 0) - consolReportAmount.value
})

// 从合并抵消分录提取资本公积相关科目
function extractFromElimination() {
  if (!props.eliminationData) return
  // 从抵消分录中提取"资本公积"科目的借贷方金额
  const elimData = props.eliminationData
  // 权益法模拟中的资本公积
  const equitySimCapital = elimData.equitySimCapital || 0
  // 合并抵消中的资本公积
  const elimCapital = elimData.elimCapital || 0

  // 更新表中对应行
  const equityRow = tableData.value.find(r => r.item === '+权益法模拟')
  if (equityRow) { equityRow.total = equitySimCapital; equityRow.fromElim = true }

  const elimRow = tableData.value.find(r => r.item === '-合并抵消数')
  if (elimRow) { elimRow.total = elimCapital; elimRow.fromElim = true }

  // 重算当期变动和期末
  recalcRows()
}

function recalcRows() {
  const openRow = tableData.value.find(r => r.item === '期初金额')
  const changeRow = tableData.value.find(r => r.item === '当期变动')
  const eqRow = tableData.value.find(r => r.item === '+权益法模拟')
  const elimRow = tableData.value.find(r => r.item === '-合并抵消数')
  const selfRow = tableData.value.find(r => r.item === '+自身报表变动')
  const otherRow = tableData.value.find(r => r.item === '其他')
  const endRowRef = tableData.value.find(r => r.item === '期末金额')

  if (changeRow) {
    changeRow.total = (Number(eqRow?.total) || 0) + (Number(elimRow?.total) || 0)
      + (Number(selfRow?.total) || 0) + (Number(otherRow?.total) || 0)
  }
  if (endRowRef && openRow) {
    endRowRef.total = (Number(openRow.total) || 0) + (Number(changeRow?.total) || 0)
  }
}

// 合计 = 合并抵消环节 + 母公司 + 各子企业
function calcCapitalTotal(row: CapitalReserveRow): number {
  const n = (v: any) => Number(v) || 0
  let sum = n(row.elimAdj) + n(row.parentVal)
  if (row.values) {
    for (const v of row.values) sum += n(v)
  }
  row.total = sum
  return sum
}

function fmt(v: any) {
  if (v == null) return '-'
  const num = Number(v)
  return isNaN(num) ? '-' : num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const headerStyle = { background: '#f0edf5', fontSize: '12px', color: '#333', padding: '4px 0' }
const cellStyle = { padding: '2px 4px', fontSize: '12px' }
function rowClassName({ row }: { row: CapitalReserveRow }) {
  if (row.bold) return 'ws-row-bold'
  if (row.isDiff) return 'ws-row-diff'
  return ''
}

function onEsc(e: KeyboardEvent) { if (e.key === 'Escape' && isFullscreen.value) isFullscreen.value = false }
onMounted(() => document.addEventListener('keydown', onEsc))
onUnmounted(() => document.removeEventListener('keydown', onEsc))
</script>

<style scoped>
.ws-sheet { padding: 0; position: relative; }
.ws-sheet--fullscreen { position: fixed !important; top: 0; left: 0; right: 0; bottom: 0; z-index: 2000; background: #fff; padding: 16px; overflow: auto; }
.ws-sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.ws-sheet-header h3 { margin: 0; font-size: 15px; color: #333; }
.ws-subtitle { font-size: 12px; color: #999; margin: 0; flex-basis: 100%; }
.ws-sheet-actions { display: flex; gap: 8px; }
.ws-section-title { font-size: 13px; font-weight: 600; color: #4b2d77; margin-bottom: 6px; padding: 6px 10px; background: #f8f6fb; border-radius: 4px; }
.ws-computed { color: #4b2d77; font-weight: 500; }
.ws-bold { font-weight: 700; }
.ws-check-area { margin-top: 12px; padding: 10px 14px; background: #fafafa; border-radius: 6px; border: 1px solid #eee; }
.ws-check-row { display: flex; gap: 12px; align-items: center; padding: 4px 0; font-size: 13px; }
.ws-diff-warn { color: #e6a23c; font-weight: 600; }
.ws-adj-section { margin-top: 16px; }
.ws-table :deep(.el-input__inner) { text-align: right; }
.ws-table :deep(.ws-row-bold td) { font-weight: 600; }
.ws-table :deep(.ws-row-diff td) { background: #fdf6ec !important; }
.ws-auto-cell { background: #faf8fd; }
</style>
