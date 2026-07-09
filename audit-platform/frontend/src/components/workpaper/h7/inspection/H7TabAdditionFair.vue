<template>
  <div class="h7-tab-addition-fair">
    <el-empty description="H7-6 增加检查（公允价值模式） — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabAdditionFair — H7-6 增加检查（公允） placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
