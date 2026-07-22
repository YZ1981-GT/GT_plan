<template>
  <H6TabDisclosure
    variant="soe"
    :wp-id="wpId"
    :project-id="projectId"
    :all-responses="allResponses"
    :is-readonly="isReadonly"
    :sheet-name="sheetName"
  />
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
