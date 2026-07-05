<template>
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
