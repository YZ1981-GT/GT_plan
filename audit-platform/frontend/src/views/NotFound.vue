<template>
  <div class="gt-not-found">
    <h1 class="gt-text-primary">404</h1>
    <p>页面不存在</p>
    <el-button type="primary" @click="$router.push('/')">返回首页</el-button>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.gt-not-found {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  gap: var(--gt-space-4);
}

.gt-not-found h1 {
  font-size: 72px /* allow-px: special */;
}
</style>
