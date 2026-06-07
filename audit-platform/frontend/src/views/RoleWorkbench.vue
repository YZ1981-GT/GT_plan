<template>
  <div class="role-workbench-page">
    <RoleWorkbenchShell />
  </div>
</template>

<script setup lang="ts">
/**
 * RoleWorkbench.vue — 角色作业台页面入口
 *
 * 路由：/projects/:projectId/workbench
 * 按当前用户角色加载对应的作业台面板。
 */
import RoleWorkbenchShell from '@/components/dashboard/RoleWorkbenchShell.vue'
</script>

<style scoped>
.role-workbench-page {
  padding: 20px;
  min-height: 100vh;
  background: var(--gt-color-bg-page, #f5f5f5);
}
</style>
