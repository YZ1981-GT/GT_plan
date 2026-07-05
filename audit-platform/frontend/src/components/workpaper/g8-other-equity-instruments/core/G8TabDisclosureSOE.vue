<template>
  <G8TabDisclosureBase variant="soe" v-bind="$props" />
</template>

<script setup lang="ts">
import G8TabDisclosureBase from './G8TabDisclosureBase.vue'
import type { ChecklistResponse } from '../../composables/useF1FormData'

defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()
</script>
