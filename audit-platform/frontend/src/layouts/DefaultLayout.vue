<template>
  <el-container class="gt-layout">
    <!-- Sidebar -->
    <el-aside width="220px" class="gt-sidebar">
      <div class="gt-sidebar-logo">
        <span class="gt-logo-text">GT 审计平台</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        background-color="var(--gt-color-primary-dark)"
        text-color="#ccc"
        active-text-color="#fff"
      >
        <el-menu-item index="/">
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/projects">
          <span>项目列表</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <!-- Header -->
      <el-header class="gt-header">
        <span class="gt-header-user">{{ authStore.username }}</span>
        <el-button type="danger" size="small" @click="handleLogout">登出</el-button>
      </el-header>

      <!-- Main content -->
      <el-main class="gt-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const activeMenu = computed(() => route.path)

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.gt-layout {
  height: 100vh;
}

.gt-sidebar {
  background-color: var(--gt-color-primary-dark);
  overflow-y: auto;
}

.gt-sidebar-logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.gt-logo-text {
  color: #fff;
  font-size: 18px;
  font-weight: bold;
  letter-spacing: 2px;
}

.gt-header {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--gt-space-3);
  background: #fff;
  box-shadow: var(--gt-shadow-sm);
  padding: 0 var(--gt-space-4);
}

.gt-header-user {
  color: var(--gt-color-primary);
  font-weight: 500;
}

.gt-main {
  background-color: #f5f5f5;
  padding: var(--gt-space-6);
}
</style>
