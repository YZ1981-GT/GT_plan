<!--
  QcClientTrendEmbed — 客户质量趋势嵌入组件 [R7-S3-03]
-->
<template>
  <div class="qc-embed-panel">
    <div class="qc-embed-header">
      <span>客户质量趋势</span>
      <el-button size="small" text type="primary" @click="$router.push('/qc/clients/all/trend')">前往完整页面 →</el-button>
    </div>
    <el-empty description="选择客户查看质量趋势（完整功能请前往独立页面）" />
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.qc-embed-panel { padding: var(--gt-space-2) 0; }
.qc-embed-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); font-weight: 600; }
</style>
