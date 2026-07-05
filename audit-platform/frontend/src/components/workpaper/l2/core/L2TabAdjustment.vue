<template>
  <div class="l2-tab-adjustment">
    <el-empty description="L2-3 调整分录汇总 — 待实现" />
  </div>
</template>

<script setup lang="ts">
/**
 * L2TabAdjustment.vue — L2-3 应付利息调整分录汇总
 * 借贷平衡校验 + EventBus + 双向同步L2-1
 * Phase 4+ 实现
 */
defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()
</script>

<style scoped>
.l2-tab-adjustment {
  padding: 16px;
}
</style>
