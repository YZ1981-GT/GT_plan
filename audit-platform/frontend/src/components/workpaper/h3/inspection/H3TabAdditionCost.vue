<template>
  <H3TabAdditionCheck
    v-bind="$props"
    measurement-model="cost"
    @navigate-sheet="(s: string) => $emit('navigate-sheet', s)"
  />
</template>

<script setup lang="ts">
/** @deprecated 请使用 H3TabAdditionCheck.vue */
import H3TabAdditionCheck from './H3TabAdditionCheck.vue'

defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

defineEmits<{ (e: 'navigate-sheet', sheetName: string): void }>()
</script>
