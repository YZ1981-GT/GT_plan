<template>
  <CutoffCrossCheck
    title="双表交叉核对（I6-5 ↔ I6-6）"
    forward-label="I6-5"
    backward-label="I6-6"
    :summary="summary"
  />
</template>

<script setup lang="ts">
import CutoffCrossCheck from '../../shared/CutoffCrossCheck.vue'
import type { CutoffCrossCheckSummary } from '../../composables/cutoffCrossCheck'

defineProps<{ summary: CutoffCrossCheckSummary }>()
</script>
