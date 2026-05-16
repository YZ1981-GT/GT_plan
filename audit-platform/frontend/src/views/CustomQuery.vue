<!--
  CustomQuery.vue — 自定义查询独立页面 [template-library-coordination Sprint 6 Task 6.4]

  路由：/custom-query
  侧栏入口：与模板库管理 Tab 保持一致功能，独立访问入口
  权限：所有审计角色可访问（auditor / manager / qc / partner / eqcr / admin）
-->
<template>
  <div class="gt-cq-view gt-fade-in">
    <div class="gt-cq-header">
      <div class="gt-cq-title-block">
        <h2 class="gt-cq-title">自定义查询</h2>
        <span class="gt-cq-subtitle">跨模块灵活检索 · 模板保存 · Excel 导出</span>
      </div>
    </div>
    <div class="gt-cq-body">
      <CustomQueryTab />
    </div>
  </div>
</template>

<script setup lang="ts">
import CustomQueryTab from '@/components/template-library/CustomQueryTab.vue'
</script>

<style scoped>
.gt-cq-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: var(--gt-space-3, 12px);
  overflow: hidden;
  background: var(--gt-color-bg, #f5f5f7);
}
.gt-cq-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  margin-bottom: 12px;
}
.gt-cq-title-block { display: flex; align-items: baseline; gap: 12px; }
.gt-cq-title { margin: 0; font-size: 16px; font-weight: 700; color: #4b2d77; }
.gt-cq-subtitle { font-size: 12px; color: #909399; }
.gt-cq-body {
  flex: 1;
  display: flex;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  padding: 12px;
  overflow: hidden;
  min-height: 0;
}
.gt-cq-body > :deep(*) { flex: 1; min-height: 0; }
</style>
