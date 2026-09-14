<script setup lang="ts">
/** F1A — 预付账款实质性程序表（对齐 D4A） */
import CycleTabProcedure from '../shared/CycleTabProcedure.vue'

defineProps<{
  wpId: string
  projectId: string
  htmlData?: any
  isReadonly?: boolean
  readonly?: boolean
}>()
</script>

<template>
  <CycleTabProcedure
    sheet-code="F1A"
    :html-data="htmlData"
    :wp-id="wpId"
    :project-id="projectId"
    :is-readonly="isReadonly"
    :readonly="readonly"
  />
</template>
