<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'ws-sheet--fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>净资产表_股比变{{ changeTimes }}次</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="isFullscreen = !isFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
        <el-button size="small" @click="$emit('save', allData)">💾 保存</el-button>
      </div>
    </div>
    <div class="ws-tip" v-show="!isFullscreen">
      <span>共 <b>{{ companies.length }}</b> 家企业发生{{ changeTimes }}次股比变动。左栏净资产变动（变动前 + {{ changeTimes }}次变动后），右栏权益法模拟。回填模拟权益法表时取最后一次变动后的合计数。</span>
    </div>

    <div v-for="(comp, ci) in companies" :key="comp.code || ci" class="sc-company-block">
      <div class="sc-company-header">
        <span class="sc-company-name">{{ comp.name }}</span>
        <el-tag size="small" effect="plain">{{ comp.ratio }}%</el-tag>
        <el-tag size="small" type="info" effect="plain">{{ comp.accountSubject || '' }}</el-tag>
      </div>

      <div class="sc-two-col">
        <!-- 左栏：净资产变动（变动前 + N次变动后） -->
        <div class="sc-col sc-col-left" :style="{ maxWidth: (200 + 110 * (changeTimes + 1)) + 'px' }">
          <div class="sc-col-title">净资产变动</div>
          <el-table :data="companyData[ci].naRows" border size="small" class="sc-table" max-height="450"
            :header-cell-style="headerStyle" :cell-style="cellStyle" :row-class-name="naRowClass">
            <el-table-column prop="item" label="项目" width="180" fixed show-overflow-tooltip>
              <template #default="{ row }">
                <span :style="{ paddingLeft: (row.indent || 0) * 10 + 'px', fontWeight: row.bold ? 700 : 400 }">{{ row.item }}</span>
              </template>
            </el-table-column>
            <el-table-column label="变动前" width="110" align="right">
              <template #default="{ row }">
                <span v-if="row.isComputed" class="sc-computed">{{ fmt(row.vals[0]) }}</span>
                <el-input-number v-else-if="!row.isHeader" v-model="row.vals[0]" size="small" :precision="2" :controls="false" style="width:100%" />
              </template>
            </el-table-column>
            <el-table-column v-for="t in changeTimes" :key="'na'+t"
              :label="changeTimes === 1 ? '变动后' : `第${t}次变动后`" width="110" align="right">
              <template #default="{ row }">
                <span v-if="row.isComputed" class="sc-computed">{{ fmt(row.vals[t]) }}</span>
                <el-input-number v-else-if="!row.isHeader" v-model="row.vals[t]" size="small" :precision="2" :controls="false" style="width:100%" />
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 右栏：权益法模拟（变动前 + N次变动后，每次借贷两列） -->
        <div class="sc-col sc-col-right">
          <div class="sc-col-title">直接持股权益法模拟 ({{ comp.ratio }}%)</div>
          <el-table :data="companyData[ci].simRows" border size="small" class="sc-table" max-height="450"
            :header-cell-style="headerStyle" :cell-style="cellStyle" :row-class-name="simRowClass">
            <el-table-column prop="subject" label="科目" width="140" fixed show-overflow-tooltip />
            <el-table-column prop="detail" label="明细" width="120" show-overflow-tooltip />
            <el-table-column label="变动前" align="center">
              <el-table-column label="借" width="85" align="right">
                <template #default="{ row }"><el-input-number v-if="!row.isSection" v-model="row.dc[0]" size="small" :precision="2" :controls="false" style="width:100%" /></template>
              </el-table-column>
              <el-table-column label="贷" width="85" align="right">
                <template #default="{ row }"><el-input-number v-if="!row.isSection" v-model="row.dc[1]" size="small" :precision="2" :controls="false" style="width:100%" /></template>
              </el-table-column>
            </el-table-column>
            <el-table-column v-for="t in changeTimes" :key="'sim'+t"
              :label="changeTimes === 1 ? '变动后' : `第${t}次变动后`" align="center">
              <el-table-column label="借" width="85" align="right">
                <template #default="{ row }"><el-input-number v-if="!row.isSection" v-model="row.dc[t * 2]" size="small" :precision="2" :controls="false" style="width:100%" /></template>
              </el-table-column>
              <el-table-column label="贷" width="85" align="right">
                <template #default="{ row }"><el-input-number v-if="!row.isSection" v-model="row.dc[t * 2 + 1]" size="small" :precision="2" :controls="false" style="width:100%" /></template>
              </el-table-column>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </div>

    <el-empty v-if="!companies.length" description="没有符合条件的企业（需在基本信息表设置股比变动）" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'

const EQUITY_ITEMS = ['实收资本（或股本）','其他权益工具','资本公积','减：库存股','其他综合收益','专项储备','盈余公积','△一般风险准备','未分配利润']

interface CompanyInfo { name: string; code: string; ratio: number; accountSubject?: string; accountingMethod?: string }
// vals[0]=变动前, vals[1]=第1次变动后, vals[2]=第2次变动后, vals[3]=第3次变动后
interface NARow { item: string; vals: (number | null)[]; indent?: number; bold?: boolean; isHeader?: boolean; isComputed?: boolean }
// dc = [变动前借, 变动前贷, 第1次后借, 第1次后贷, 第2次后借, 第2次后贷, ...]
interface SimRow { subject: string; detail: string; dc: (number | null)[]; isSection?: boolean }

const props = defineProps<{
  changeTimes: 1 | 2 | 3
  companies: CompanyInfo[]
  allCompanies: { name: string; code?: string; ratio: number }[]
}>()

defineEmits<{ (e: 'save', data: any): void }>()

const isFullscreen = ref(false)
const sheetRef = ref<HTMLElement | null>(null)
const colCount = computed(() => props.changeTimes + 1) // 变动前 + N次变动后
const dcCount = computed(() => colCount.value * 2) // 每列借贷两个

const companyData = reactive<{ naRows: NARow[]; simRows: SimRow[] }[]>([])

watch(() => props.companies, (comps) => {
  while (companyData.length < comps.length) {
    companyData.push({ naRows: buildNARows(), simRows: buildSimRows() })
  }
  companyData.length = comps.length
}, { immediate: true, deep: true })

function buildNARows(): NARow[] {
  const rows: NARow[] = []
  const mk = (item: string, opts: Partial<NARow> = {}): NARow =>
    ({ item, vals: new Array(colCount.value).fill(null), ...opts })
  rows.push(mk('所有者权益/股东权益', { isHeader: true, bold: true }))
  rows.push(mk('期初合计：', { bold: true, isComputed: true }))
  EQUITY_ITEMS.forEach(i => rows.push(mk(i, { indent: 1 })))
  rows.push(mk('本期增加', { bold: true, isComputed: true }))
  EQUITY_ITEMS.forEach(i => rows.push(mk(i, { indent: 1 })))
  rows.push(mk('本期减少', { bold: true, isComputed: true }))
  EQUITY_ITEMS.forEach(i => rows.push(mk(i, { indent: 1 })))
  rows.push(mk('期末金额', { bold: true, isComputed: true }))
  EQUITY_ITEMS.forEach(i => rows.push(mk(i, { indent: 1 })))
  return rows
}

const SIM_STRUCTURE = [
  { s: '1.基础信息', d: '', sec: true }, { s: '持股比例', d: '', sec: true },
  { s: '2.权益法模拟', d: '', sec: true }, { s: '2.1 期初模拟', d: '', sec: true },
  { s: '长期股权投资', d: '损益调整' }, { s: '长期股权投资', d: '其他权益变动' },
  { s: '年初未分配利润', d: '' }, { s: '资本公积', d: '' }, { s: '其他综合收益', d: '' },
  { s: '专项储备', d: '' }, { s: '其他权益工具', d: '' }, { s: '△一般风险准备', d: '' },
  { s: '2.2 当期变动', d: '', sec: true },
  { s: '长期股权投资', d: '损益调整' }, { s: '长期股权投资', d: '其他权益变动' },
  { s: '投资收益', d: '' }, { s: '资本公积', d: '' }, { s: '其他综合收益', d: '' },
  { s: '专项储备', d: '' }, { s: '其他权益工具', d: '' }, { s: '△一般风险准备', d: '' },
  { s: '2-3股份支付', d: '（二）所有者投入和减少资本' }, { s: '2-4其他', d: '（二）所有者投入和减少资本' },
  { s: '4-3对所有者的分配', d: '（四）利润分配' }, { s: '4-4其他', d: '（四）利润分配' },
  { s: '3.分红影响', d: '', sec: true },
  { s: '投资收益', d: '' }, { s: '长期股权投资', d: '损益调整' },
  { s: '4.股比变动影响', d: '', sec: true },
  { s: '长期股权投资', d: '损益调整' }, { s: '长期股权投资', d: '其他权益变动' },
  { s: '资本公积', d: '' }, { s: '投资收益', d: '' },
  { s: '模拟后长投', d: '', sec: true },
  { s: '长期股权投资', d: '投资成本' }, { s: '长期股权投资', d: '损益调整' },
  { s: '长期股权投资', d: '其他权益变动' }, { s: '长期股权投资', d: '减值准备' },
  { s: '长期股权投资', d: '小计' },
]

function buildSimRows(): SimRow[] {
  return SIM_STRUCTURE.map(r => ({
    subject: r.s, detail: r.d, dc: new Array(dcCount.value).fill(null), isSection: r.sec || false,
  }))
}

// 自动计算净资产汇总行
watch(companyData, () => {
  const n = (v: any) => Number(v) || 0
  for (const cd of companyData) {
    for (let i = 0; i < cd.naRows.length; i++) {
      const row = cd.naRows[i]
      if (!row.isComputed || !row.bold || row.isHeader) continue
      const sums = new Array(colCount.value).fill(0)
      for (let j = i + 1; j < cd.naRows.length; j++) {
        const child = cd.naRows[j]
        if (child.bold || child.isHeader || (child.indent || 0) === 0) break
        if (child.isComputed) continue
        for (let k = 0; k < colCount.value; k++) sums[k] += n(child.vals[k])
      }
      for (let k = 0; k < colCount.value; k++) row.vals[k] = sums[k]
    }
  }
}, { deep: true })

// 回填数据：取最后一次变动后的模拟长投小计
const allData = computed(() => companyData.map((cd, i) => {
  // 最后一次变动后的借贷列索引
  const lastDebitIdx = props.changeTimes * 2
  const lastCreditIdx = props.changeTimes * 2 + 1
  const totalRow = cd.simRows.find(r => r.subject === '长期股权投资' && r.detail === '小计')
  const endInvestTotal = totalRow ? (Number(totalRow.dc[lastDebitIdx]) || 0) - (Number(totalRow.dc[lastCreditIdx]) || 0) : 0
  return {
    company: props.companies[i],
    naRows: cd.naRows,
    simRows: cd.simRows,
    endInvestTotal, // 回填到模拟权益法表的值
  }
}))

function fmt(v: any) { if (v == null) return '-'; const num = Number(v); return isNaN(num) ? '-' : num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

const headerStyle = { background: '#f0edf5', fontSize: '11px', color: '#333', padding: '2px 0' }
const cellStyle = { padding: '2px 4px', fontSize: '11px' }
function naRowClass({ row }: any) { return row.isHeader ? 'sc-row-header' : row.bold ? 'sc-row-bold' : '' }
function simRowClass({ row }: any) { return row.isSection ? 'sc-row-section' : '' }

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
.ws-tip b { color: #4b2d77; }
.sc-company-block { margin-bottom: 24px; border: 1px solid #e8e4f0; border-radius: 8px; padding: 12px; }
.sc-company-header { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 2px solid #4b2d77; }
.sc-company-name { font-size: 15px; font-weight: 700; color: #4b2d77; }
.sc-two-col { display: flex; gap: 12px; overflow-x: auto; }
.sc-col { flex-shrink: 0; }
.sc-col-left { }
.sc-col-right { flex: 1; min-width: 0; }
.sc-col-title { font-size: 12px; font-weight: 600; color: #666; margin-bottom: 6px; padding: 4px 8px; background: #f8f6fb; border-radius: 4px; }
.sc-computed { color: #4b2d77; font-weight: 500; }
.sc-table :deep(.el-input__inner) { text-align: right; font-size: 11px; }
.sc-table :deep(.sc-row-header td) { background: #f8f6fb !important; font-weight: 600; }
.sc-table :deep(.sc-row-bold td) { font-weight: 600; }
.sc-table :deep(.sc-row-section td) { background: #f0edf5 !important; font-weight: 600; color: #4b2d77; }
</style>
