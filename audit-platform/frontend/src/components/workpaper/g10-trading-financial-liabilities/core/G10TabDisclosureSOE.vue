<template>
  <!-- 审计目标(objective-alert)/编制提示(guidance-details)/审计说明(-audit-note)/审计结论(-audit-conclusion) 均由 G10TabDisclosureBase 按 variant=soe 统一渲染 -->
  <G10TabDisclosureBase variant="soe" v-bind="$props" />
</template>
<script setup lang="ts">
import G10TabDisclosureBase from './G10TabDisclosureBase.vue'
import type { ChecklistResponse } from '../../composables/useF1FormData'
defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()
</script>
