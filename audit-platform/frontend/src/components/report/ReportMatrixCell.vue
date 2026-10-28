<script setup lang="ts">
/**
 * ReportMatrixCell — 报表矩阵金额格（权益变动表 / 资产减值准备表）
 *
 * 平时只显示金额文字（GtAmountCell）；可编辑时双击 / F2 / 直接输入才挂数字输入框，提交时发 `commit(新值)`，
 * 由页面写 `/reports/cell`（spec excel-style-table-editing 5.4：替换原先的双击弹输入框）。
 * 经典编辑方式下可编辑格的输入框常驻（与其他表格的经典方式一致）。
 */
import { computed } from 'vue'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import GtGridCell from '@/components/grid/GtGridCell.vue'
import { ElInputNumber } from '@/components/grid/adapters'

defineOptions({ name: 'ReportMatrixCell' })

const props = withDefaults(defineProps<{
  /** 金额（数字或数字字符串；空为未填） */
  value: unknown
  /** 可编辑（默认否：只显示） */
  editable?: boolean
}>(), { editable: false })

const emit = defineEmits<{ (e: 'commit', value: number | null): void }>()

/** 空、非数字 → null（null 表示清空该格） */
function toNumberOrNull(v: unknown): number | null {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

const numeric = computed(() => toNumberOrNull(props.value))

/** 显示用：数字 / 数字字符串原样交给 GtAmountCell，其余按未填 */
const displayValue = computed<number | string | null>(() => {
  const v = props.value
  return typeof v === 'number' || typeof v === 'string' ? v : null
})

function onChange(v: unknown): void {
  emit('commit', toNumberOrNull(v))
}
</script>

<template>
  <GtGridCell :editable="editable" :value="numeric">
    <template #display><GtAmountCell :value="displayValue" /></template>
    <ElInputNumber
      :model-value="numeric ?? undefined"
      :controls="false"
      size="small"
      style="width: 100%"
      @change="onChange"
    />
  </GtGridCell>
</template>
