<template>
  <H10TabDisclosureBase variant="listed" v-bind="$props" />
</template>
<script setup lang="ts">
import H10TabDisclosureBase from './H10TabDisclosureBase.vue'
import type { ChecklistResponse } from '../../composables/useF1FormData'
defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()
</script>
