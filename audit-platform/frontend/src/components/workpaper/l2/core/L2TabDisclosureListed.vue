<template>
  <div class="l2-tab-disclosure-listed">
    <el-empty description="L2 附注披露（上市公司） — 待实现" />
  </div>
</template>

<script setup lang="ts">
/**
 * L2TabDisclosureListed.vue — L2 附注披露信息（上市公司）
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
.l2-tab-disclosure-listed {
  padding: 16px;
}
</style>
