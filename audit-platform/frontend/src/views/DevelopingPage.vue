<template>
  <div class="developing-page">
    <div class="developing-content">
      <div class="developing-icon">🚧</div>
      <h2 class="developing-title">功能开发中</h2>
      <p class="developing-desc">该功能正在开发中，敬请期待</p>
      <el-button type="primary" @click="router.back()">返回上一页</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<style scoped>
.developing-page {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 400px;
}

.developing-content {
  text-align: center;
  padding: 48px;
}

.developing-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.developing-title {
  font-size: 24px;
  font-weight: 600;
  color: #333;
  margin: 0 0 8px;
}

.developing-desc {
  font-size: 14px;
  color: #999;
  margin: 0 0 24px;
}
</style>
