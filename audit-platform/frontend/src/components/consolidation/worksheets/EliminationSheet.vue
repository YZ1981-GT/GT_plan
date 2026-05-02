<template>
  <div class="ws-sheet">
    <div class="ws-sheet-header">
      <h3>合并抵消分录明细表</h3>
      <div class="ws-sheet-actions">
        <el-button size="small" @click="$emit('save', { equity: equityRows, income: incomeRows, cross: crossRows })">💾 保存</el-button>
      </div>
    </div>

    <!-- 子企业列头 -->
    <div class="ws-company-bar">
      <span v-for="(c, i) in companies" :key="i" class="ws-company-tag">
        {{ c.name }} <small>({{ c.ratio }}%)</small>
      </span>
    </div>

    <!-- 1. 期末权益抵消 -->
    <div class="ws-section">
      <div class="ws-section-title">1. 期末权益抵消</div>
      <el-table :data="equityRows" border size="small" class="ws-table" max-height="400"
        :header-cell-style="headerStyle" :cell-style="cellStyle" :row-class-name="rowClassName">
        <el-table-column prop="direction" label="借贷" width="40" align="center">
          <template #default="{ row }">
            <el-tag :type="row.direction === '借' ? 'danger' : 'success'" size="small" effect="plain">{{ row.direction }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="subject" label="项目" width="180" show-overflow-tooltip />
        <el-table-column prop="detail" label="二级明细" width="120" show-overflow-tooltip />
        <el-table-column prop="total" label="合计" width="120" align="right">
          <template #default="{ row }">
            <span v-if="row.isComputed" class="ws-computed ws-bold">{{ fmt(row.total) }}</span>
            <span v-else class="ws-computed">{{ fmt(sumValues(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-for="(c, ci) in companies" :key="ci" :label="c.name" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.values" v-model="row.values[ci]" size="small" :precision="2" :controls="false" style="width:100%" />
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 2. 当期损益抵消 -->
    <div class="ws-section">
      <div class="ws-section-title">2. 当期损益抵消</div>
      <el-table :data="incomeRows" border size="small" class="ws-table" max-height="400"
        :header-cell-style="headerStyle" :cell-style="cellStyle" :row-class-name="rowClassName">
        <el-table-column prop="direction" label="借贷" width="40" align="center">
          <template #default="{ row }">
            <el-tag :type="row.direction === '借' ? 'danger' : 'success'" size="small" effect="plain">{{ row.direction }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="subject" label="项目" width="220" show-overflow-tooltip />
        <el-table-column prop="detail" label="二级明细" width="160" show-overflow-tooltip />
        <el-table-column prop="total" label="合计" width="120" align="right">
          <template #default="{ row }">
            <span class="ws-computed">{{ fmt(sumValues(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-for="(c, ci) in companies" :key="ci" :label="c.name" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.values" v-model="row.values[ci]" size="small" :precision="2" :controls="false" style="width:100%" />
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 3. 交叉持股的权益和损益抵消 -->
    <div class="ws-section">
      <div class="ws-section-title">3. 交叉持股的权益和损益抵消</div>
      <el-table :data="crossRows" border size="small" class="ws-table"
        :header-cell-style="headerStyle" :cell-style="cellStyle">
        <el-table-column prop="direction" label="借贷" width="40" align="center">
          <template #default="{ row }">
            <el-tag :type="row.direction === '借' ? 'danger' : 'success'" size="small" effect="plain">{{ row.direction }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="subject" label="项目" width="180" />
        <el-table-column prop="total" label="金额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.total" size="small" :precision="2" :controls="false" style="width:100%" />
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 汇总：抵销后的少数股东 -->
    <div class="ws-section">
      <div class="ws-section-title">抵销后汇总</div>
      <el-table :data="summaryRows" border size="small" class="ws-table"
        :header-cell-style="headerStyle" :cell-style="cellStyle">
        <el-table-column prop="label" label="项目" width="200" />
        <el-table-column prop="source" label="来源" width="140">
          <template #default><span style="color:#999">合并抵消环节产生</span></template>
        </el-table-column>
        <el-table-column prop="total" label="合计" width="120" align="right">
          <template #default="{ row }">
            <span class="ws-computed ws-bold">{{ fmt(row.total) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-for="(c, ci) in companies" :key="ci" :label="c.name" width="120" align="right">
          <template #default="{ row }">
            <span class="ws-computed">{{ fmt(row.values?.[ci]) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'

interface CompanyCol { name: string; ratio: number }

interface ElimRow {
  direction: string; subject: string; detail?: string
  total?: number | null; values?: (number | null)[]
  isComputed?: boolean
}

const props = defineProps<{
  companies: CompanyCol[]
  equityRows: ElimRow[]
  incomeRows: ElimRow[]
  crossRows: ElimRow[]
}>()

defineEmits<{
  (e: 'save', data: { equity: ElimRow[]; income: ElimRow[]; cross: ElimRow[] }): void
}>()

const companies = ref(props.companies)
const equityRows = ref([...props.equityRows])
const incomeRows = ref([...props.incomeRows])
const crossRows = ref([...props.crossRows])

watch(() => props.companies, (v) => { companies.value = v })
watch(() => props.equityRows, (v) => { equityRows.value = [...v] }, { deep: true })
watch(() => props.incomeRows, (v) => { incomeRows.value = [...v] }, { deep: true })
watch(() => props.crossRows, (v) => { crossRows.value = [...v] }, { deep: true })

function sumValues(row: ElimRow): number {
  if (!row.values) return Number(row.total) || 0
  return row.values.reduce((s: number, v) => s + (Number(v) || 0), 0)
}

// 汇总行：少数股东权益 / 少数股东损益
const summaryRows = computed(() => {
  const minorityEquity: (number | null)[] = companies.value.map((_: any, ci: number) => {
    const row = equityRows.value.find((r: ElimRow) => r.subject === '少数股东权益')
    return row?.values?.[ci] ?? null
  })
  const minorityIncome: (number | null)[] = companies.value.map((_: any, ci: number) => {
    const row = incomeRows.value.find((r: ElimRow) => r.subject === '少数股权损益')
    return row?.values?.[ci] ?? null
  })
  return [
    { label: '抵销后的少数股东权益', total: minorityEquity.reduce((s: number, v) => s + (Number(v) || 0), 0), values: minorityEquity },
    { label: '抵销后的少数股东损益', total: minorityIncome.reduce((s: number, v) => s + (Number(v) || 0), 0), values: minorityIncome },
  ]
})

function fmt(v: any) {
  if (v == null) return '-'
  const num = Number(v)
  return isNaN(num) ? '-' : num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const headerStyle = { background: '#f0edf5', fontSize: '11px', color: '#333', padding: '3px 0' }
const cellStyle = { padding: '2px 4px', fontSize: '11px' }
function rowClassName() { return '' }
</script>

<style scoped>
.ws-sheet { padding: 0; }
.ws-sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.ws-sheet-header h3 { margin: 0; font-size: 15px; color: #333; }
.ws-sheet-actions { display: flex; gap: 8px; }
.ws-company-bar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.ws-company-tag { padding: 4px 10px; background: #f8f6fb; border-radius: 4px; font-size: 12px; color: #4b2d77; }
.ws-section { margin-bottom: 16px; }
.ws-section-title { font-size: 13px; font-weight: 600; color: #4b2d77; margin-bottom: 6px; padding: 6px 10px; background: #f8f6fb; border-radius: 4px; }
.ws-computed { color: #4b2d77; font-weight: 500; }
.ws-bold { font-weight: 700; }
.ws-table :deep(.el-input__inner) { text-align: right; font-size: 11px; }
</style>
