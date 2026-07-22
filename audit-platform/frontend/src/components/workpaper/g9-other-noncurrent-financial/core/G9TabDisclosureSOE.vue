<template>
  <!-- 审计目标/编制提示/金额表 由 G9TabDisclosureBase 按 variant=soe 统一渲染 -->
  <G9TabDisclosureBase variant="soe" v-bind="$props" @imported="emit('imported')" />
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

const emit = defineEmits<{ imported: [] }>()
</script>
