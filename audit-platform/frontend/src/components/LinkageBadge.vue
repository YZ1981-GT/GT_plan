<script setup lang="ts">
/**
 * LinkageBadge — 联动徽章 [enterprise-linkage 3.6]
 *
 * 显示关联数量，0 时隐藏。
 */
defineProps<{
  count: number
  type: 'adjustment' | 'workpaper'
}>()
</script>

<template>
  <el-badge
    v-if="count > 0"
    :value="count"
    :type="type === 'adjustment' ? 'primary' : 'success'"
    class="linkage-badge"
  >
    <el-tag size="small" :type="type === 'adjustment' ? undefined : 'success'" effect="plain">
      {{ type === 'adjustment' ? '分录' : '底稿' }}
    </el-tag>
  </el-badge>
</template>

<style scoped>
.linkage-badge {
  cursor: pointer;
  margin: 0 2px;
}
.linkage-badge :deep(.el-badge__content) {
  font-size: 10px;
}
</style>
