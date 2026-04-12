<template>
  <el-container class="gt-layout">
    <!-- Sidebar -->
    <el-aside :width="sidebarCollapsed ? '64px' : '220px'" class="gt-sidebar">
      <div class="gt-sidebar-logo" @click="sidebarCollapsed = !sidebarCollapsed">
        <transition name="gt-logo" mode="out-in">
          <div v-if="!sidebarCollapsed" key="full" class="logo-full">
            <img src="/gt.png" alt="致同" class="logo-img" />
            <span class="logo-text">审计平台</span>
          </div>
          <div v-else key="mini" class="logo-mini">
            <img src="/gt.png" alt="致同" class="logo-img-mini" />
          </div>
        </transition>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="sidebarCollapsed"
        router
        class="gt-nav-menu"
      >
        <el-menu-item index="/">
          <el-icon><Odometer /></el-icon>
          <template #title>仪表盘</template>
        </el-menu-item>
        <el-menu-item index="/projects">
          <el-icon><FolderOpened /></el-icon>
          <template #title>项目列表</template>
        </el-menu-item>
      </el-menu>

      <!-- 底部折叠按钮 -->
      <div class="gt-sidebar-footer" @click="sidebarCollapsed = !sidebarCollapsed">
        <el-icon :size="16"><DArrowLeft v-if="!sidebarCollapsed" /><DArrowRight v-else /></el-icon>
      </div>
    </el-aside>

    <el-container class="gt-content-wrap">
      <!-- Header -->
      <el-header class="gt-header" height="56px">
        <div class="gt-header-left">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item v-if="currentPageTitle">{{ currentPageTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="gt-header-right">
          <img src="/gt.png" alt="致同" class="gt-header-logo" />
          <el-dropdown trigger="click">
            <div class="gt-user-avatar">
              <el-avatar :size="32" class="gt-avatar">
                {{ (authStore.username || 'U').charAt(0).toUpperCase() }}
              </el-avatar>
              <span class="gt-username">{{ authStore.username }}</span>
              <el-icon :size="12"><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="handleLogout">
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- Main content with route transition -->
      <el-main class="gt-main">
        <router-view v-slot="{ Component }">
          <transition name="gt-page" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  Odometer, FolderOpened, DArrowLeft, DArrowRight,
  ArrowDown, SwitchButton,
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const sidebarCollapsed = ref(false)

const activeMenu = computed(() => {
  const p = route.path
  if (p.startsWith('/projects')) return '/projects'
  return '/'
})

const currentPageTitle = computed(() => {
  const name = route.name as string
  const map: Record<string, string> = {
    Projects: '项目列表',
    ProjectWizard: '新建项目',
    Consolidation: '合并报表',
    TrialBalance: '试算表',
    Adjustments: '调整分录',
  }
  return map[name] || ''
})

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.gt-layout {
  height: 100vh;
  overflow: hidden;
}

/* ── Sidebar ── */
.gt-sidebar {
  background: linear-gradient(180deg, var(--gt-color-primary-dark) 0%, #1a1035 100%);
  display: flex;
  flex-direction: column;
  transition: width var(--gt-transition-base);
  overflow: hidden;
  position: relative;
  z-index: 10;
}

.gt-sidebar-logo {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
  transition: all var(--gt-transition-base);
}

.gt-sidebar-logo:hover {
  background: rgba(255, 255, 255, 0.04);
}

.logo-full {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-img {
  height: 32px;
  width: auto;
  object-fit: contain;
  filter: brightness(0) invert(1);
}

.logo-text {
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 1.5px;
  white-space: nowrap;
}

.logo-mini {
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo-img-mini {
  height: 26px;
  width: auto;
  object-fit: contain;
  filter: brightness(0) invert(1);
}

/* Logo 切换动画 */
.gt-logo-enter-active,
.gt-logo-leave-active {
  transition: opacity 0.2s, transform 0.2s;
}
.gt-logo-enter-from { opacity: 0; transform: scale(0.9); }
.gt-logo-leave-to { opacity: 0; transform: scale(0.9); }

/* 导航菜单 */
.gt-nav-menu {
  flex: 1;
  background: transparent !important;
  border-right: none !important;
  padding: var(--gt-space-2) 0;
}

.gt-nav-menu .el-menu-item {
  height: 44px;
  line-height: 44px;
  margin: 2px 8px;
  border-radius: var(--gt-radius-sm);
  color: rgba(255, 255, 255, 0.65) !important;
  transition: all var(--gt-transition-fast);
  font-size: var(--gt-font-size-base);
}

.gt-nav-menu .el-menu-item:hover {
  background: rgba(255, 255, 255, 0.08) !important;
  color: #fff !important;
}

.gt-nav-menu .el-menu-item.is-active {
  background: linear-gradient(135deg, var(--gt-color-primary) 0%, var(--gt-color-primary-light) 100%) !important;
  color: #fff !important;
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.4);
}

.gt-nav-menu .el-menu-item .el-icon {
  font-size: 18px;
  margin-right: 8px;
}

/* 折叠态菜单项居中 */
.gt-nav-menu.el-menu--collapse .el-menu-item {
  padding: 0 !important;
  justify-content: center;
}

.gt-nav-menu.el-menu--collapse .el-menu-item .el-icon {
  margin-right: 0;
}

/* 底部折叠按钮 */
.gt-sidebar-footer {
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: rgba(255, 255, 255, 0.4);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  transition: all var(--gt-transition-fast);
  flex-shrink: 0;
}

.gt-sidebar-footer:hover {
  color: rgba(255, 255, 255, 0.8);
  background: rgba(255, 255, 255, 0.04);
}

/* ── Header ── */
.gt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--gt-color-bg-white);
  border-bottom: 1px solid var(--gt-color-border-light);
  padding: 0 var(--gt-space-6);
  flex-shrink: 0;
}

.gt-header-left {
  display: flex;
  align-items: center;
}

.gt-header-right {
  display: flex;
  align-items: center;
  gap: var(--gt-space-4);
}

.gt-header-logo {
  height: 36px;
  width: auto;
  object-fit: contain;
  transition: opacity var(--gt-transition-fast);
}

.gt-user-avatar {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--gt-radius-sm);
  transition: background var(--gt-transition-fast);
}

.gt-user-avatar:hover {
  background: var(--gt-color-primary-bg);
}

.gt-avatar {
  background: linear-gradient(135deg, var(--gt-color-primary) 0%, var(--gt-color-primary-light) 100%);
  color: #fff;
  font-weight: 600;
  font-size: 14px;
}

.gt-username {
  font-size: var(--gt-font-size-base);
  font-weight: 500;
  color: var(--gt-color-text);
}

/* ── Main ── */
.gt-content-wrap {
  flex-direction: column;
  overflow: hidden;
}

.gt-main {
  background-color: var(--gt-color-bg);
  padding: var(--gt-space-6);
  overflow-y: auto;
}

/* ── 路由过渡 ── */
.gt-page-enter-active {
  animation: gtPageIn 0.35s cubic-bezier(0.22, 1, 0.36, 1) both;
}
.gt-page-leave-active {
  animation: gtPageOut 0.15s ease-in both;
}

@keyframes gtPageIn {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes gtPageOut {
  from { opacity: 1; }
  to   { opacity: 0; }
}
</style>
