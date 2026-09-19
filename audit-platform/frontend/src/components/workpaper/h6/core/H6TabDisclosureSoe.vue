<template>
  <H6TabDisclosure variant="soe" v-bind="$props" />
</template>

<script setup lang="ts">
/** 薄包装：附注披露信息（国有企业）→ H6TabDisclosure variant=soe */
import H6TabDisclosure from './H6TabDisclosure.vue'

defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  sheetName?: string
}>()
</script>
