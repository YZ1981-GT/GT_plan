<template>
  <div class="ws-sheet">
    <div class="ws-sheet-header">
      <h3>模拟权益法调整表</h3>
      <div class="ws-sheet-actions">
        <el-button size="small" @click="$emit('save', { direct: directRows, indirect: indirectSections })">💾 保存</el-button>
      </div>
    </div>
    <div class="ws-tip">
      <span>4步模拟流程：❶期初长投模拟 → ❷当期变动模拟 → ❸还原分红影响 → ❹股比变动影响。底部自动比对模拟后长投与按比例享有净资产的差异。</span>
    </div>

    <!-- 动态子企业列头 -->
    <div class="ws-company-bar">
      <span v-for="(c, i) in companies" :key="i" class="ws-company-tag">
        {{ c.name }} <small>({{ c.ratio }}%)</small>
      </span>
    </div>

    <!-- 1. 直接长期股权投资权益法模拟 -->
    <div class="ws-section">
      <div class="ws-section-title">1. 直接长期股权投资权益法模拟</div>

      <el-table :data="directRows" border size="small" class="ws-table" max-height="500"
        :header-cell-style="headerStyle" :cell-style="cellStyle" :row-class-name="rowClassName">
        <el-table-column prop="seq" label="序号" width="40" align="center" />
        <el-table-column prop="step" label="步骤" width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span :style="{ fontWeight: row.isStep ? 700 : 400 }">{{ row.step }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="direction" label="借贷" width="40" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.direction" :type="row.direction === '借' ? 'danger' : 'success'" size="small" effect="plain">
              {{ row.direction }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="subject" label="项目" width="160" show-overflow-tooltip />
        <el-table-column prop="detail" label="二级明细" width="140" show-overflow-tooltip />
        <el-table-column prop="total" label="合计" width="120" align="right">
          <template #default="{ row }">
            <span v-if="row.isComputed" class="ws-computed">{{ fmt(row.total) }}</span>
            <el-input-number v-else-if="!row.isStep" v-model="row.total" size="small" :precision="2" :controls="false" style="width:100%" @change="recalcTotal(row)" />
          </template>
        </el-table-column>
        <!-- 动态子企业列 -->
        <el-table-column v-for="(c, ci) in companies" :key="ci" :label="c.name" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isStep && !row.isComputed && row.values"
              v-model="row.values[ci]" size="small" :precision="2" :controls="false" style="width:100%" />
            <span v-else-if="row.isComputed && row.values" class="ws-computed">{{ fmt(row.values?.[ci]) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 2. 间接/交叉持股权益法模拟（可重复多个单位） -->
    <div v-for="(section, si) in indirectSections" :key="si" class="ws-section">
      <div class="ws-section-title">
        2. 间接/交叉持股权益法模拟 — {{ section.companyName }}
        <small style="color:#999;margin-left:8px">期末持股比例: {{ section.ratio }}%</small>
      </div>

      <el-table :data="section.rows" border size="small" class="ws-table" max-height="400"
        :header-cell-style="headerStyle" :cell-style="cellStyle" :row-class-name="rowClassName">
        <el-table-column prop="seq" label="序号" width="40" align="center" />
        <el-table-column prop="step" label="步骤" width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span :style="{ fontWeight: row.isStep ? 700 : 400 }">{{ row.step }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="direction" label="借贷" width="40" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.direction" :type="row.direction === '借' ? 'danger' : 'success'" size="small" effect="plain">
              {{ row.direction }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="subject" label="项目" width="160" show-overflow-tooltip />
        <el-table-column prop="detail" label="二级明细" width="140" show-overflow-tooltip />
        <el-table-column prop="total" label="金额" width="120" align="right">
          <template #default="{ row }">
            <span v-if="row.isComputed" class="ws-computed">{{ fmt(row.total) }}</span>
            <el-input-number v-else-if="!row.isStep" v-model="row.total" size="small" :precision="2" :controls="false" style="width:100%" />
          </template>
        </el-table-column>
      </el-table>

      <!-- 比对区 -->
      <div class="ws-compare">
        <div class="ws-compare-row">
          <span>模拟后期末长投小计:</span>
          <span class="ws-computed">{{ fmt(section.endLongInvest) }}</span>
        </div>
        <div class="ws-compare-row">
          <span>期末所有者权益 × 持股比例:</span>
          <span class="ws-computed">{{ fmt(section.endNetAssetShare) }}</span>
        </div>
        <div class="ws-compare-row" :class="{ 'ws-diff-warn': section.difference !== 0 }">
          <span>差异金额:</span>
          <span>{{ fmt(section.difference) }}</span>
        </div>
        <div v-if="section.difference !== 0" class="ws-compare-row">
          <span>差异原因:</span>
          <el-input v-model="section.diffReason" size="small" placeholder="分析过程简要注明" style="flex:1" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

interface CompanyCol { name: string; ratio: number }

interface EquitySimRow {
  seq: string; step: string; direction: string; subject: string; detail: string
  total: number | null; values?: (number | null)[]
  isStep?: boolean; isComputed?: boolean
}

interface IndirectSection {
  companyName: string; ratio: number
  rows: EquitySimRow[]
  endLongInvest: number; endNetAssetShare: number; difference: number; diffReason: string
}

const props = defineProps<{
  companies: CompanyCol[]
  directRows: EquitySimRow[]
  indirectSections: IndirectSection[]
}>()

defineEmits<{
  (e: 'save', data: { direct: EquitySimRow[]; indirect: IndirectSection[] }): void
}>()

const companies = ref(props.companies)
const directRows = ref([...props.directRows])
const indirectSections = ref([...props.indirectSections])

watch(() => props.companies, (v) => { companies.value = v })
watch(() => props.directRows, (v) => { directRows.value = [...v] }, { deep: true })
watch(() => props.indirectSections, (v) => { indirectSections.value = [...v] }, { deep: true })

function recalcTotal(row: EquitySimRow) {
  if (row.values) {
    row.total = row.values.reduce((s, v) => s! + (Number(v) || 0), 0)
  }
}

function fmt(v: any) {
  if (v == null) return '-'
  const num = Number(v)
  return isNaN(num) ? '-' : num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const headerStyle = { background: '#f0edf5', fontSize: '11px', color: '#333', padding: '3px 0' }
const cellStyle = { padding: '2px 4px', fontSize: '11px' }

function rowClassName({ row }: { row: EquitySimRow }) {
  if (row.isStep) return 'ws-row-step'
  return ''
}
</script>

<style scoped>
.ws-sheet { padding: 0; }
.ws-sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.ws-sheet-header h3 { margin: 0; font-size: 15px; color: #333; }
.ws-sheet-actions { display: flex; gap: 8px; }
.ws-tip {
  display: flex; align-items: flex-start; gap: 6px; padding: 6px 10px; margin-bottom: 10px;
  background: #f4f4f5; border-radius: 6px; font-size: 12px; color: #666; line-height: 1.5;
}
.ws-company-bar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.ws-company-tag { padding: 4px 10px; background: #f8f6fb; border-radius: 4px; font-size: 12px; color: #4b2d77; }
.ws-section { margin-bottom: 20px; }
.ws-section-title { font-size: 13px; font-weight: 600; color: #4b2d77; margin-bottom: 6px; padding: 6px 10px; background: #f8f6fb; border-radius: 4px; }
.ws-compare { margin-top: 8px; padding: 8px 12px; background: #fafafa; border-radius: 6px; border: 1px solid #eee; }
.ws-compare-row { display: flex; gap: 12px; align-items: center; padding: 3px 0; font-size: 12px; }
.ws-diff-warn { color: #e6a23c; font-weight: 600; }
.ws-computed { color: #4b2d77; font-weight: 500; }
.ws-table :deep(.el-input__inner) { text-align: right; font-size: 11px; }
.ws-table :deep(.ws-row-step td) { background: #f8f6fb !important; font-weight: 600; }
</style>
