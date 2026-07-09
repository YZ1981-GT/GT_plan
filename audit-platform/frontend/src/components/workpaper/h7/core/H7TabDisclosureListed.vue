<template>
  <div class="h7-tab-disclosure-listed">
    <el-empty description="H7 附注披露（上市公司） — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabDisclosureListed — 附注上市 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
