<template>
  <div class="table-scroll">
    <table class="labor-table">
      <thead>
        <tr>
          <th rowspan="2" class="col-product">产品</th>
          <th colspan="12">月份</th>
          <th rowspan="2" class="col-summary">{{ summaryLabel }}</th>
          <th rowspan="2" class="col-prior">上年度</th>
          <th rowspan="2" class="col-rate">变动率</th>
          <th v-if="showReason" rowspan="2" class="col-reason">变动原因</th>
          <th v-if="!isReadonly && valueKind === 'labor'" rowspan="2" class="col-act" />
        </tr>
        <tr>
          <th v-for="m in monthLabels" :key="m.key">{{ m.label }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="line in lines"
          :key="`${line.id}-${valueKind}`"
          :class="{ 'row-warn': highlightVariance && isRateAbnormal(line) }"
        >
          <td class="col-product">
            <el-input
              v-if="!isReadonly && valueKind === 'labor'"
              :model-value="line.productName"
              size="small"
              placeholder="品名"
              @update:model-value="(v: string) => $emit('updateName', line.id, v)"
            />
            <span v-else>{{ line.productName || '—' }}</span>
          </td>
          <td v-for="m in monthLabels" :key="m.key">
            <el-input-number
              v-if="isEditable"
              :model-value="monthValue(line, m.key)"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              class="compact-num"
              @change="(v: number | undefined) => $emit('updateMonth', line.id, m.key as LaborMonthKey, v ?? 0)"
            />
            <span v-else class="auto">{{ fmtCell(monthValue(line, m.key)) }}</span>
          </td>
          <td class="auto col-summary">{{ fmtCell(summaryValue(line)) }}</td>
          <td>
            <el-input-number
              v-if="!isReadonly && valueKind !== 'unit'"
              :model-value="priorValue(line)"
              size="small"
              :controls="false"
              class="compact-num"
              @change="(v: number | undefined) => $emit('updatePrior', line.id, v ?? 0)"
            />
            <el-input-number
              v-else-if="!isReadonly && valueKind === 'unit'"
              :model-value="line.unitPriorYear"
              size="small"
              :controls="false"
              class="compact-num"
              @change="(v: number | undefined) => $emit('updatePrior', line.id, v ?? 0)"
            />
            <span v-else class="auto">{{ fmtCell(priorValue(line)) }}</span>
          </td>
          <td class="auto col-rate" :class="{ 'var-warn': highlightVariance && isRateAbnormal(line) }">
            {{ fmtRate(rateValue(line)) }}
          </td>
          <td v-if="showReason">
            <el-input
              v-if="!isReadonly && valueKind === 'labor'"
              :model-value="line.changeReason"
              size="small"
              @update:model-value="(v: string) => $emit('updateReason', line.id, v)"
            />
          </td>
          <td v-if="!isReadonly && valueKind === 'labor'" class="col-act">
            <el-button link type="danger" size="small" @click="$emit('remove', line.id)">删</el-button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { EnrichedLaborProductLine, LaborMonthKey } from '../../composables/useF2DirectLaborMatrixFormulas'

const props = defineProps<{
  lines: EnrichedLaborProductLine[]
  monthLabels: ReadonlyArray<{ key: string; label: string }>
  isReadonly?: boolean
  summaryLabel: string
  valueKind: 'labor' | 'output' | 'unit'
  priorField: string
  changeRateField: string
  totalField: string
  highlightVariance?: boolean
}>()

defineEmits<{
  updateName: [id: string, name: string]
  updateMonth: [id: string, month: LaborMonthKey, value: number]
  updatePrior: [id: string, value: number]
  updateReason: [id: string, reason: string]
  remove: [id: string]
}>()

const isEditable = computed(() => props.valueKind !== 'unit' && !props.isReadonly)
const showReason = computed(() => props.valueKind === 'labor')

function monthValue(line: EnrichedLaborProductLine, key: string): number {
  if (props.valueKind === 'labor') return line.laborMonths[key as LaborMonthKey] ?? 0
  if (props.valueKind === 'output') return line.outputMonths[key as LaborMonthKey] ?? 0
  return line.unitMonths[key as LaborMonthKey] ?? 0
}

function summaryValue(line: EnrichedLaborProductLine): number {
  if (props.totalField === 'laborTotal') return line.laborTotal
  if (props.totalField === 'outputTotal') return line.outputTotal
  return line.unitAverage
}

function priorValue(line: EnrichedLaborProductLine): number {
  if (props.priorField === 'laborPriorYear') return line.laborPriorYear
  if (props.priorField === 'outputPriorYear') return line.outputPriorYear
  return line.unitPriorYear
}

function rateValue(line: EnrichedLaborProductLine): number | '' | 'N/A' {
  if (props.changeRateField === 'laborChangeRate') return line.laborChangeRate
  if (props.changeRateField === 'outputChangeRate') return line.outputChangeRate
  return line.unitChangeRate
}

function isRateAbnormal(line: EnrichedLaborProductLine): boolean {
  const r = line.unitChangeRate
  return typeof r === 'number' && Math.abs(r) > 0.05
}

function fmtCell(v: number): string {
  if (v === 0 || !Number.isFinite(v)) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}

function fmtRate(r: number | '' | 'N/A'): string {
  if (r === '' || r === 'N/A') return '—'
  return `${(r * 100).toFixed(2)}%`
}
</script>

<style scoped>
.table-scroll { overflow-x: auto; margin-bottom: 8px; }
.labor-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  min-width: 1200px;
}
.labor-table th,
.labor-table td {
  border: 1px solid #d4c8e0;
  padding: 2px 3px;
  text-align: center;
  vertical-align: middle;
}
.labor-table thead th {
  background: #f3eef8;
  color: #3d2a55;
  font-weight: 600;
}
.col-product { width: 100px; background: #faf8fc; }
.col-summary { background: #f0ebf5 !important; min-width: 76px; }
.col-prior { min-width: 76px; }
.col-rate { min-width: 64px; }
.col-reason { min-width: 90px; }
.col-act { width: 36px; }
.auto { display: block; text-align: right; padding-right: 4px; white-space: nowrap; color: #606266; }
.row-warn td { background: #fdf6ec; }
.var-warn { color: #f56c6c !important; font-weight: 600; }
:deep(.compact-num) { width: 64px; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 3px; font-size: 11px; }
</style>
