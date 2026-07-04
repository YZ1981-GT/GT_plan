<template>
  <el-table :data="tableData" size="small" border stripe style="width:100%;font-size:13px">
    <el-table-column prop="label" label="项目" min-width="160" fixed />
    <el-table-column label="索引" width="72" fixed>
      <template #default="{ row }">
        <GtIndexChip
          v-if="row.rowKey !== 'subtotal' && sheetCodeForRowKey(row.rowKey)"
          :value="sheetCodeForRowKey(row.rowKey)!"
          :context-project-id="projectId"
        />
      </template>
    </el-table-column>
    <el-table-column label="期初数" min-width="110" align="right">
      <template #default="{ row }">
        <el-input-number
          v-if="!readonly && row.rowKey !== 'subtotal'"
          :model-value="row.opening"
          size="small"
          :controls="false"
          @change="(v: number) => onUpdate(row.rowKey, 'opening', v)"
        />
        <span v-else>{{ fmt(row.opening) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="本期增加" min-width="110" align="right">
      <template #default="{ row }">
        <el-input-number
          v-if="!readonly && row.rowKey !== 'subtotal'"
          :model-value="row.increase"
          size="small"
          :controls="false"
          @change="(v: number) => onUpdate(row.rowKey, 'increase', v)"
        />
        <span v-else>{{ fmt(row.increase) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="本期减少" min-width="110" align="right">
      <template #default="{ row }">
        <el-input-number
          v-if="!readonly && row.rowKey !== 'subtotal'"
          :model-value="row.decrease"
          size="small"
          :controls="false"
          @change="(v: number) => onUpdate(row.rowKey, 'decrease', v)"
        />
        <span v-else>{{ fmt(row.decrease) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="期末未审" min-width="110" align="right">
      <template #default="{ row }">
        <el-tooltip content="公式：期初 + 增加 - 减少" placement="top">
          <span class="formula-cell">{{ fmt(row.endUnadjusted) }}</span>
        </el-tooltip>
      </template>
    </el-table-column>
    <el-table-column label="账项调整" min-width="110" align="right">
      <template #default="{ row }">
        <el-input-number
          v-if="!readonly && row.rowKey !== 'subtotal'"
          :model-value="row.adjustment"
          size="small"
          :controls="false"
          @change="(v: number) => onUpdate(row.rowKey, 'adjustment', v)"
        />
        <span v-else>{{ fmt(row.adjustment) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="期末审定" min-width="110" align="right">
      <template #default="{ row }">
        <el-tooltip content="公式：未审数 + 账项调整" placement="top">
          <span class="formula-cell">{{ fmt(row.endAudited) }}</span>
        </el-tooltip>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { F2AdjudicationRow, F2BlockKey } from '../../composables/useF2Adjudication'
import { sheetCodeForRowKey } from '../../composables/useF2CrossSheet'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  rows: F2AdjudicationRow[]
  subtotal: F2AdjudicationRow
  block: F2BlockKey
  projectId?: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'update', block: F2BlockKey, rowKey: string, field: string, value: number): void
}>()

const tableData = computed(() => [
  ...(Array.isArray(props.rows) ? props.rows : []),
  props.subtotal,
])

function fmt(n: number) {
  return Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function onUpdate(rowKey: string, field: string, value: number) {
  emit('update', props.block, rowKey, field, value ?? 0)
}
</script>

<style scoped>
.formula-cell { border-bottom: 1px dashed #c0c4cc; cursor: help; }
</style>
