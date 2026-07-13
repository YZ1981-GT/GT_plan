<template>
  <!-- 审计目标(objective-alert)/编制提示(guidance-details)/审计说明(-audit-note)/审计结论(-audit-conclusion) 均由 G9TabDisclosureBase 按 variant=listed 统一渲染 -->
  <G9TabDisclosureBase variant="listed" v-bind="$props" />
</template>

<script setup lang="ts">
import G9TabDisclosureBase from './G9TabDisclosureBase.vue'
import type { ChecklistResponse } from '../../composables/useF1FormData'

defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()
</script>
