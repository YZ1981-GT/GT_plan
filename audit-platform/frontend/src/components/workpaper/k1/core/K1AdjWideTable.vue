<!-- K1-1 致同宽表：期初/期末各四列 + 变动 + 原因 -->
<template>
  <el-table
    :data="rows"
    border
    stripe
    size="small"
    class="wide-table"
    :max-height="maxHeight"
    :row-key="(row: K1AdjRow) => row.rowKey"
    :row-class-name="rowClassName"
  >
    <el-table-column prop="label" label="项目" min-width="120" fixed />

    <el-table-column label="期初数" align="center">
      <el-table-column label="未审" min-width="88" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="editable(row)"
            :model-value="row.priorUnadjusted"
            :controls="false"
            size="small"
            class="amount-input"
            @change="emitField(row, 'prior-unadj', $event)"
          />
          <span v-else>{{ fmt(row.priorUnadjusted) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="AJE" min-width="80" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="editable(row)"
            :model-value="row.priorAje"
            :controls="false"
            size="small"
            class="amount-input"
            @change="emitField(row, 'prior-aje', $event)"
          />
          <span v-else>{{ fmt(row.priorAje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="RJE" min-width="80" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="editable(row)"
            :model-value="row.priorRje"
            :controls="false"
            size="small"
            class="amount-input"
            @change="emitField(row, 'prior-rje', $event)"
          />
          <span v-else>{{ fmt(row.priorRje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审定" min-width="88" align="right">
        <template #default="{ row }">
          <span class="formula-cell">{{ fmt(row.priorAudited) }}</span>
        </template>
      </el-table-column>
    </el-table-column>

    <el-table-column label="期末数" align="center">
      <el-table-column label="未审" min-width="88" align="right">
        <template #default="{ row }">
          <span class="tb-auto">{{ fmt(row.unadjusted) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="AJE" min-width="80" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="editable(row)"
            :model-value="row.aje"
            :controls="false"
            size="small"
            class="amount-input"
            @change="emitField(row, 'aje', $event)"
          />
          <span v-else>{{ fmt(row.aje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="RJE" min-width="80" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="editable(row)"
            :model-value="row.rje"
            :controls="false"
            size="small"
            class="amount-input"
            @change="emitField(row, 'rje', $event)"
          />
          <span v-else>{{ fmt(row.rje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审定" min-width="88" align="right">
        <template #default="{ row }">
          <span class="formula-cell">{{ fmt(row.audited) }}</span>
        </template>
      </el-table-column>
    </el-table-column>

    <el-table-column label="变动额" min-width="88" align="right">
      <template #default="{ row }">
        <span :class="{ 'warn-change': isHighVariance(row) }">{{ fmt(row.changeAmount) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="变动率" min-width="72" align="right">
      <template #default="{ row }">
        <span :class="{ 'warn-change': isHighVariance(row) }">
          {{ row.changeRate != null ? (row.changeRate * 100).toFixed(1) + '%' : '-' }}
        </span>
      </template>
    </el-table-column>
    <el-table-column label="原因分析" min-width="160">
      <template #default="{ row }">
        <el-input
          v-if="editable(row)"
          :model-value="row.remark"
          size="small"
          placeholder="变动超30%须说明"
          @change="emitField(row, 'remark', $event)"
        />
        <span v-else>{{ row.remark || '-' }}</span>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import type { K1AdjRow } from '../../composables/useK1Adjudication'
import { K1_VARIANCE_THRESHOLD } from '../../composables/k1AdjudicationCross'

const props = defineProps<{
  rows: K1AdjRow[]
  prefix: string
  isReadonly: boolean
  maxHeight?: number
  highlightRowKey?: string
}>()

const emit = defineEmits<{
  (e: 'field-change', payload: { prefix: string; rowKey: string; field: string; value: string | number }): void
}>()

function editable(row: K1AdjRow): boolean {
  return row.rowKey !== 'subtotal' && !props.isReadonly
}

function isHighVariance(row: K1AdjRow): boolean {
  return row.changeRate != null && Math.abs(row.changeRate) >= K1_VARIANCE_THRESHOLD
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function emitField(row: K1AdjRow, field: string, value: string | number | undefined) {
  if (row.rowKey === 'subtotal') return
  emit('field-change', { prefix: props.prefix, rowKey: row.rowKey, field, value: value ?? '' })
}

function rowClassName({ row }: { row: K1AdjRow }): string {
  if (props.highlightRowKey && row.rowKey === props.highlightRowKey) return 'k1-row-deeplink-hl'
  return ''
}
</script>

<style scoped>
.wide-table { font-size: var(--wp-font-size, 13px); }
.amount-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); font-variant-numeric: tabular-nums; }
.tb-auto { color: var(--el-text-color-secondary); font-style: italic; font-variant-numeric: tabular-nums; }
.warn-change { color: var(--el-color-warning); font-weight: 600; }
.wide-table :deep(.k1-row-deeplink-hl > td) {
  background-color: #ecf5ff !important;
  animation: k1-row-flash 1.2s ease-in-out 0s 2;
}
@keyframes k1-row-flash { 0%, 100% { background-color: #ecf5ff; } 50% { background-color: #d9ecff; } }
</style>
