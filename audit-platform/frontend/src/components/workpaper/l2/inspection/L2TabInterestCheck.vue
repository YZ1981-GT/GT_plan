<template>
  <div class="l2-tab-interest-check">
    <el-empty description="L2-4 应付利息检查表 — 待实现" />
  </div>
</template>

<script setup lang="ts">
/**
 * L2TabInterestCheck.vue — L2-4 应付利息检查表
 * 计提核对 + 审计结论 + AI辅助按钮
 * Phase 4+ 实现
 */
defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()
</script>

<style scoped>
.l2-tab-interest-check {
  padding: 16px;
}
</style>
