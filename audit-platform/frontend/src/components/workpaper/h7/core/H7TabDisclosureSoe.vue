<template>
  <div class="h7-tab-disclosure-soe">
    <el-empty description="H7 附注披露（国有企业） — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabDisclosureSoe — 附注国企 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
