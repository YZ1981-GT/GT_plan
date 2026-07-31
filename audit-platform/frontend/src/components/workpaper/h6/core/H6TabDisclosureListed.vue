<template>
  <H6TabDisclosure variant="listed" v-bind="$props" />
</template>

<script setup lang="ts">
/** 薄包装：附注披露信息（上市公司）→ H6TabDisclosure variant=listed */
import H6TabDisclosure from './H6TabDisclosure.vue'

defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  sheetName?: string
}>()
</script>
