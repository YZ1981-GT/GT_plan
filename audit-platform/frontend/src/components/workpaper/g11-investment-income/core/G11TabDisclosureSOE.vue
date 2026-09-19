<template>
  <!--
    G11 附注披露（国企）委托壳：六项标准要素——审计目标 objective-alert、编制提示
    guidance-details、审计说明、审计结论——均由 G11TabDisclosureBase 按 variant="soe"
    统一渲染并持久化（item_id 携带 -soe 后缀区分变体）。本组件仅做 variant 委托。
  -->
  <G11TabDisclosureBase variant="soe" v-bind="$props" @imported="emit('imported')" />
</template>
<script setup lang="ts">
import G11TabDisclosureBase from './G11TabDisclosureBase.vue'
import type { ChecklistResponse } from '../../composables/useF1FormData'
defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  applicableStandards?: string[]
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()
const emit = defineEmits<{ imported: [] }>()
</script>
