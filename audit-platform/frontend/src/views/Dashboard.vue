<template>
  <div class="gt-dashboard">
    <h1 class="gt-text-primary">仪表盘</h1>
    <p class="gt-dashboard-desc">欢迎使用 GT 审计作业平台</p>
    <div class="gt-dashboard-cards">
      <div class="gt-card gt-dashboard-stat">
        <h3>项目总数</h3>
        <span class="gt-stat-value gt-text-primary">—</span>
      </div>
      <div class="gt-card gt-dashboard-stat">
        <h3>进行中</h3>
        <span class="gt-stat-value gt-text-teal">—</span>
      </div>
      <div class="gt-card gt-dashboard-stat">
        <h3>待复核</h3>
        <span class="gt-stat-value gt-text-coral">—</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.gt-dashboard-desc {
  color: #666;
  margin: var(--gt-space-2) 0 var(--gt-space-6);
}

.gt-dashboard-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--gt-space-4);
}

.gt-dashboard-stat {
  text-align: center;
  padding: var(--gt-space-6);
}

.gt-stat-value {
  font-size: 32px;
  font-weight: bold;
  display: block;
  margin-top: var(--gt-space-2);
}
</style>
