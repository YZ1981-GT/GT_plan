<template>
  <div class="l2-tab-disclosure-soe">
    <el-empty description="L2 附注披露（国有企业） — 待实现" />
  </div>
</template>

<script setup lang="ts">
/**
 * L2TabDisclosureSoe.vue — L2 附注披露信息（国有企业）
 * subscribe 'substantive:adjudicated' 刷新
 * Phase 5+ 实现
 */
defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()
</script>

<style scoped>
.l2-tab-disclosure-soe {
  padding: 16px;
}
</style>
