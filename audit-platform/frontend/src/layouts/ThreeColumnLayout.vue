<template>
  <div class="gt-three-col" :class="{ 'gt-three-col--collapsed': sidebarCollapsed, 'gt-three-col--fullscreen': fullscreen }">
    <!-- 顶部导航栏 -->
    <header class="gt-topbar">
      <div class="gt-topbar-left">
        <div class="gt-logo" @click="sidebarCollapsed = !sidebarCollapsed" title="折叠/展开导航">
          <img src="/gt.png" alt="致同" class="gt-logo-img" />
          <transition name="gt-fade">
            <span v-if="!sidebarCollapsed" class="gt-logo-text">审计平台</span>
          </transition>
        </div>
      </div>
      <div class="gt-topbar-center">
        <el-breadcrumb separator="/">
          <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
          <el-breadcrumb-item v-if="currentModule">{{ currentModule }}</el-breadcrumb-item>
        </el-breadcrumb>
      </div>
      <div class="gt-topbar-right">
        <el-tooltip content="通知" placement="bottom">
          <el-badge :value="0" :hidden="true" class="gt-topbar-btn">
            <el-icon :size="18"><Bell /></el-icon>
          </el-badge>
        </el-tooltip>
        <el-dropdown trigger="click">
          <div class="gt-user-info">
            <el-avatar :size="30" class="gt-avatar">
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
    </header>

    <!-- 三栏主体 -->
    <div class="gt-body">
      <!-- 左侧栏：1级功能导航 -->
      <aside class="gt-sidebar" :style="{ width: sidebarCollapsed ? '56px' : sidebarWidth + 'px' }" role="navigation">
        <nav class="gt-nav">
          <div
            v-for="item in navItems"
            :key="item.key"
            class="gt-nav-item"
            :class="{ 'gt-nav-item--active': activeNav === item.key }"
            @click="onNavClick(item)"
            :title="item.label"
          >
            <el-icon :size="20"><component :is="item.icon" /></el-icon>
            <transition name="gt-fade">
              <span v-if="!sidebarCollapsed" class="gt-nav-label">{{ item.label }}</span>
            </transition>
          </div>
        </nav>
        <div class="gt-sidebar-bottom">
          <div class="gt-nav-item" @click="sidebarCollapsed = !sidebarCollapsed" title="折叠">
            <el-icon :size="18"><DArrowLeft v-if="!sidebarCollapsed" /><DArrowRight v-else /></el-icon>
            <transition name="gt-fade">
              <span v-if="!sidebarCollapsed" class="gt-nav-label">收起</span>
            </transition>
          </div>
        </div>
      </aside>

      <!-- 左侧拖拽分隔线（始终显示，用于调整左侧栏宽度） -->
      <div
        v-if="!sidebarCollapsed"
        class="gt-resizer"
        @mousedown="startResize('left', $event)"
      />

      <!-- 中间栏：2级内容 -->
      <section v-if="!props.hideMiddle" class="gt-middle" :style="{ width: middleWidth + 'px' }" role="main">
        <slot name="middle">
          <router-view name="middle" />
        </slot>
      </section>

      <!-- 右侧拖拽分隔线 -->
      <div v-if="!props.hideMiddle" class="gt-resizer" @mousedown="startResize('right', $event)" />

      <!-- 右侧栏：项目详情 / 主内容区 -->
      <section class="gt-detail" :role="props.hideMiddle ? 'main' : 'complementary'">
        <slot name="detail">
          <router-view name="detail" />
        </slot>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  Odometer, FolderOpened, User, Reading, Timer, Connection,
  Stamp, Box, Setting, Bell, ArrowDown, SwitchButton,
  DArrowLeft, DArrowRight,
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

// ── Props ──
const props = defineProps<{ hideMiddle?: boolean }>()

// ── 导航项 ──
const navItems = [
  { key: 'dashboard', label: '仪表盘', icon: Odometer, path: '/' },
  { key: 'projects', label: '项目情况', icon: FolderOpened, path: '/projects' },
  { key: 'team', label: '人员委派', icon: User, path: '/team' },
  { key: 'knowledge', label: '知识库', icon: Reading, path: '/knowledge' },
  { key: 'workhours', label: '工时管理', icon: Timer, path: '/workhours' },
  { key: 'consolidation', label: '合并项目', icon: Connection, path: '/consolidation' },
  { key: 'confirmation', label: '函证管理', icon: Stamp, path: '/confirmation' },
  { key: 'archive', label: '归档管理', icon: Box, path: '/archive' },
  { key: 'settings', label: '系统设置', icon: Setting, path: '/settings' },
]

const activeNav = computed(() => {
  const p = route.path
  if (p === '/') return 'dashboard'
  for (const item of navItems) {
    if (item.path !== '/' && p.startsWith(item.path)) return item.key
  }
  if (p.startsWith('/projects')) return 'projects'
  return 'dashboard'
})

const currentModule = computed(() => {
  const item = navItems.find(n => n.key === activeNav.value)
  return item?.label || ''
})

const emit = defineEmits<{ (e: 'nav-change', key: string): void }>()

function onNavClick(item: typeof navItems[0]) {
  emit('nav-change', item.key)
  router.push(item.path)
}

// ── 布局状态 ──
const STORAGE_KEY = 'gt-layout-prefs'
const sidebarCollapsed = ref(false)
const sidebarWidth = ref(220)
const middleWidth = ref(340)
const fullscreen = ref(false)

// 监听折叠状态变化自动保存
watch(sidebarCollapsed, () => savePrefs())

function loadPrefs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const prefs = JSON.parse(raw)
      sidebarCollapsed.value = prefs.collapsed ?? false
      sidebarWidth.value = prefs.sidebarWidth ?? 220
      middleWidth.value = prefs.middleWidth ?? 340
    }
  } catch { /* ignore */ }
}

function savePrefs() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    collapsed: sidebarCollapsed.value,
    sidebarWidth: sidebarWidth.value,
    middleWidth: middleWidth.value,
  }))
}

// ── 拖拽调整宽度 ──
let resizing: 'left' | 'right' | null = null
let startX = 0
let startW = 0

function startResize(side: 'left' | 'right', e: MouseEvent) {
  resizing = side
  startX = e.clientX
  startW = side === 'left' ? sidebarWidth.value : middleWidth.value
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onResize)
  document.addEventListener('mouseup', stopResize)
}

function onResize(e: MouseEvent) {
  if (!resizing) return
  const dx = e.clientX - startX
  if (resizing === 'left') {
    sidebarWidth.value = Math.max(180, Math.min(300, startW + dx))
  } else {
    middleWidth.value = Math.max(250, Math.min(500, startW + dx))
  }
}

function stopResize() {
  resizing = null
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
  savePrefs()
}

// ── 键盘快捷键 ──
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && fullscreen.value) {
    fullscreen.value = false
  }
}

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}

onMounted(() => {
  loadPrefs()
  document.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
/* ═══════════════════════════════════════════════════════════════
   三栏布局 — 整体结构
   ═══════════════════════════════════════════════════════════════ */
.gt-three-col {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--gt-color-bg);
}

/* ── 顶部导航栏 ── */
.gt-topbar {
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--gt-space-4);
  background: var(--gt-color-bg-white);
  border-bottom: 1px solid var(--gt-color-border-light);
  flex-shrink: 0;
  z-index: 100;
}

.gt-topbar-left { display: flex; align-items: center; }
.gt-topbar-center { flex: 1; padding: 0 var(--gt-space-4); }
.gt-topbar-right { display: flex; align-items: center; gap: var(--gt-space-3); }

.gt-logo {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--gt-radius-sm);
  transition: background var(--gt-transition-fast);
}
.gt-logo:hover { background: var(--gt-color-primary-bg); }
.gt-logo-img { height: 28px; width: auto; }
.gt-logo-text {
  font-size: var(--gt-font-size-lg);
  font-weight: 700;
  color: var(--gt-color-primary);
  white-space: nowrap;
}

.gt-topbar-btn {
  cursor: pointer;
  padding: 6px;
  border-radius: var(--gt-radius-sm);
  color: var(--gt-color-text-secondary);
  transition: all var(--gt-transition-fast);
}
.gt-topbar-btn:hover { background: var(--gt-color-primary-bg); color: var(--gt-color-primary); }

.gt-user-info {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--gt-radius-sm);
  transition: background var(--gt-transition-fast);
}
.gt-user-info:hover { background: var(--gt-color-primary-bg); }
.gt-avatar {
  background: linear-gradient(135deg, var(--gt-color-primary) 0%, var(--gt-color-primary-light) 100%);
  color: #fff;
  font-weight: 600;
  font-size: 13px;
}
.gt-username {
  font-size: var(--gt-font-size-sm);
  font-weight: 500;
  color: var(--gt-color-text);
}

/* ── 三栏主体 ── */
.gt-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

/* ── 左侧栏 ── */
.gt-sidebar {
  display: flex;
  flex-direction: column;
  background: #f5f7fa;
  border-right: 1px solid var(--gt-color-border-light);
  transition: width var(--gt-transition-base);
  overflow: hidden;
  flex-shrink: 0;
}

.gt-nav {
  flex: 1;
  padding: var(--gt-space-2) var(--gt-space-1);
  overflow-y: auto;
  overflow-x: hidden;
}

.gt-nav-item {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  padding: 10px 12px;
  margin: 2px 4px;
  border-radius: var(--gt-radius-sm);
  cursor: pointer;
  color: var(--gt-color-text-secondary);
  font-size: var(--gt-font-size-sm);
  white-space: nowrap;
  transition: all var(--gt-transition-fast);
}
.gt-nav-item:hover {
  background: rgba(75, 45, 119, 0.05);
  color: var(--gt-color-primary);
}
.gt-nav-item--active {
  background: var(--gt-color-primary) !important;
  color: #fff !important;
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.3);
}
.gt-nav-label { font-weight: 500; }

.gt-sidebar-bottom {
  border-top: 1px solid var(--gt-color-border-light);
  padding: var(--gt-space-1);
}

/* 折叠态 */
.gt-three-col--collapsed .gt-nav-item {
  justify-content: center;
  padding: 10px 0;
}

/* ── 拖拽分隔线 ── */
.gt-resizer {
  width: 4px;
  cursor: col-resize;
  background: transparent;
  flex-shrink: 0;
  position: relative;
  z-index: 10;
  transition: background var(--gt-transition-fast);
}
.gt-resizer:hover,
.gt-resizer:active {
  background: var(--gt-color-primary-lighter);
}
.gt-resizer::after {
  content: '';
  position: absolute;
  top: 0; bottom: 0;
  left: -3px; right: -3px;
}

/* ── 中间栏 ── */
.gt-middle {
  flex-shrink: 0;
  background: var(--gt-color-bg-white);
  border-right: 1px solid var(--gt-color-border-light);
  overflow-y: auto;
  overflow-x: hidden;
}

/* ── 右侧栏 ── */
.gt-detail {
  flex: 1;
  min-width: 0;
  background: var(--gt-color-bg-white);
  overflow-y: auto;
}

/* ── 全屏模式 ── */
.gt-three-col--fullscreen .gt-sidebar,
.gt-three-col--fullscreen .gt-middle,
.gt-three-col--fullscreen .gt-resizer {
  display: none;
}

/* ── 响应式 ── */
@media (max-width: 1200px) {
  .gt-three-col:not(.gt-three-col--collapsed) .gt-sidebar {
    width: 56px !important;
  }
  .gt-three-col:not(.gt-three-col--collapsed) .gt-nav-label {
    display: none;
  }
  .gt-three-col:not(.gt-three-col--collapsed) .gt-nav-item {
    justify-content: center;
    padding: 10px 0;
  }
}

/* ── 过渡动画 ── */
.gt-fade-enter-active, .gt-fade-leave-active {
  transition: opacity 0.15s, transform 0.15s;
}
.gt-fade-enter-from, .gt-fade-leave-to {
  opacity: 0;
  transform: translateX(-4px);
}
</style>
