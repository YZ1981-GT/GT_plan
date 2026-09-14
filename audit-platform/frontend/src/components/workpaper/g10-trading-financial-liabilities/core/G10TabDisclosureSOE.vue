<template>
  <G10TabDisclosureBase variant="soe" v-bind="$props" @imported="emit('imported')" />
</template>
<script setup lang="ts">
import G10TabDisclosureBase from './G10TabDisclosureBase.vue'
import type { ChecklistResponse } from '../../composables/useF1FormData'
defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()
const emit = defineEmits<{ imported: [] }>()
</script>
