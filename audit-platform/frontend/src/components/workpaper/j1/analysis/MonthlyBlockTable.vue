<template>
  <div class="monthly-block-table">
    <el-table :data="tableData" border size="small" style="font-size:13px" max-height="300"
      :row-class-name="({ row }) => row.isTotal ? 'total-row' : ''">
      <el-table-column label="部门" width="140" fixed>
        <template #default="{ row }">
          <span v-if="row.isTotal"><b>合计</b></span>
          <template v-else>
            <div class="dept-cell">
              <el-input
                v-if="!isReadonly && !isFormula"
                :model-value="row.dept"
                size="small"
                style="width:90px"
                @change="(v: string) => $emit('rename-dept', row.dept, v)"
              />
              <span v-else>{{ row.dept }}</span>
              <el-button v-if="!isReadonly && !isFormula" type="danger" link size="small" @click="$emit('remove-dept', row.dept)">×</el-button>
            </div>
          </template>
        </template>
      </el-table-column>
      <el-table-column v-for="m in 12" :key="m" :label="`${m}月`" width="90" align="right">
        <template #default="{ row }">
          <template v-if="row.isTotal || isFormula || isReadonly">
            <span :class="{ 'formula-cell': isFormula || row.isTotal }">{{ fmtVal(row.months[m-1]) }}</span>
          </template>
          <template v-else>
            <el-input-number
              :model-value="row.months[m-1]"
              :controls="false" size="small" style="width:78px"
              :precision="isInteger ? 0 : 2"
              @change="(v: number) => $emit('update', row.dept, m-1, v ?? 0)"
            />
          </template>
        </template>
      </el-table-column>
      <el-table-column label="合计" width="100" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <b class="formula-cell">{{ fmtVal(sum12(row.months)) }}</b>
        </template>
      </el-table-column>
      <el-table-column v-if="showProportion" label="占比" width="70" align="right">
        <template #default="{ row }">
          {{ calcProportion(row.months) }}
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  departments: string[]
  data: Map<string, number[]>
  totalRow: number[]
  isReadonly: boolean
  blockName: string
  isFormula?: boolean
  isInteger?: boolean
  showProportion?: boolean
  formulaFn?: (dept: string) => number[]
}>()

defineEmits<{
  update: [dept: string, monthIdx: number, value: number]
  'remove-dept': [dept: string]
  'rename-dept': [oldName: string, newName: string]
}>()

interface RowData {
  dept: string
  months: number[]
  isTotal: boolean
}

const tableData = computed<RowData[]>(() => {
  const rows: RowData[] = []
  for (const dept of props.departments) {
    if (props.isFormula && props.formulaFn) {
      rows.push({ dept, months: props.formulaFn(dept), isTotal: false })
    } else {
      rows.push({ dept, months: props.data.get(dept) || Array(12).fill(0), isTotal: false })
    }
  }
  rows.push({ dept: '合计', months: props.totalRow, isTotal: true })
  return rows
})

function sum12(months: number[]): number {
  return months.reduce((s, v) => s + v, 0)
}

function fmtVal(v: number): string {
  if (v === 0) return '-'
  if (props.isInteger) return Math.round(v).toLocaleString()
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function calcProportion(months: number[]): string {
  const total = sum12(props.totalRow)
  if (total === 0) return '-'
  const rowTotal = sum12(months)
  return ((rowTotal / total) * 100).toFixed(1) + '%'
}
</script>

<style scoped>
.monthly-block-table { overflow-x: auto; margin-bottom: 8px; }
.monthly-block-table :deep(.el-table) { font-size: 13px !important; }
.monthly-block-table :deep(.el-table th), .monthly-block-table :deep(.el-table td) { font-size: 13px !important; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.total-row) { background: #f5f7fa !important; font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.dept-cell { display: flex; align-items: center; gap: 4px; }
</style>
