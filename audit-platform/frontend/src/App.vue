<template>
  <div id="app">
    <router-view />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

// 页面刷新后自动恢复用户信息（token 从 localStorage 恢复，但 user 对象需要重新获取）
onMounted(async () => {
  if (authStore.isAuthenticated && !authStore.user) {
    try {
      await authStore.fetchUserProfile()
    } catch {
      // token 过期或无效，不阻断页面加载（路由守卫会处理跳转登录）
    }
  }
})
</script>
