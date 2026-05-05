<template>
  <div id="app">
    <router-view />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useDictStore } from '@/stores/dict'

const authStore = useAuthStore()
const dictStore = useDictStore()

// 页面刷新后自动恢复用户信息（token 从 localStorage 恢复，但 user 对象需要重新获取）
onMounted(async () => {
  if (authStore.isAuthenticated && !authStore.user) {
    try {
      await authStore.fetchUserProfile()
    } catch {
      // token 过期或无效，不阻断页面加载（路由守卫会处理跳转登录）
    }
  }

  // 加载枚举字典（sessionStorage 缓存，不阻塞页面渲染）
  // 在 fetchUserProfile 之后检查认证状态，防止 token 失效后仍尝试加载字典
  if (authStore.isAuthenticated) {
    dictStore.load()
  }
})
</script>
