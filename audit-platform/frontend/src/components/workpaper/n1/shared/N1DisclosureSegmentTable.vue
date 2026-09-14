<template>
  <WpDisclosureSegmentTable
    :label-header="labelHeader"
    :columns="columns"
    :segments="segments"
    :readonly="readonly"
    :allow-add-row="allowAddRow"
    @change-cell="(p) => emit('change-cell', p)"
    @change-label="(p) => emit('change-label', p)"
    @add-row="(s) => emit('add-row', s)"
    @remove-row="(p) => emit('remove-row', p)"
  />
</template>

<script setup lang="ts">
/**
 * @deprecated 组件已提升为平台共用
 * `shared/disclosure/WpDisclosureSegmentTable.vue`
 * （spec `n-cycle-tax-disclosure-alignment` Task 2.1）。
 *
 * 本文件保留为**透传薄壳**，仅为让 N1 既有引用零回归；新代码请直接用 Wp 版本。
 * 🔴 薄壳必须逐个声明 prop 并显式转发 emit —— `v-bind="$props"` 只转发**已声明**的
 * prop，漏声明会静默锁死（平台实测：G9 两壳漏 `projectId` → 同步按钮永久 disabled）。
 */
import WpDisclosureSegmentTable from '../../shared/disclosure/WpDisclosureSegmentTable.vue'
import type {
  WpSegColumn,
  WpSegment,
} from '../../composables/shared/disclosureSegmentTypes'

withDefaults(
  defineProps<{
    labelHeader: string
    columns: WpSegColumn[]
    segments: WpSegment[]
    readonly?: boolean
    allowAddRow?: boolean
  }>(),
  { readonly: false, allowAddRow: true },
)

const emit = defineEmits<{
  (e: 'change-cell', payload: { seg: string; index: number; key: string; value: number | string }): void
  (e: 'add-row', seg: string): void
  (e: 'remove-row', payload: { seg: string; index: number }): void
  (e: 'change-label', payload: { seg: string; index: number; value: string }): void
}>()
</script>
