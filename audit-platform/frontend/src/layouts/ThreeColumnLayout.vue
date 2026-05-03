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
        <!-- 顶部快捷入口（全局工具） -->
        <el-tooltip content="知识库" placement="bottom">
          <div class="gt-topbar-btn" @click="router.push('/knowledge')">
            <el-icon :size="18"><Reading /></el-icon>
          </div>
        </el-tooltip>
        <el-tooltip content="私人库" placement="bottom">
          <div class="gt-topbar-btn" @click="router.push('/private-storage')">
            <el-icon :size="18"><Suitcase /></el-icon>
          </div>
        </el-tooltip>
        <el-tooltip content="AI 模型" placement="bottom">
          <div class="gt-topbar-btn" @click="router.push('/settings/ai-models')">
            <el-icon :size="18"><Cpu /></el-icon>
          </div>
        </el-tooltip>
        <el-tooltip content="排版模板" placement="bottom">
          <div class="gt-topbar-btn" @click="router.push('/settings/report-format')">
            <el-icon :size="18"><Document /></el-icon>
          </div>
        </el-tooltip>
        <el-tooltip content="吐槽求助" placement="bottom">
          <div class="gt-topbar-btn" @click="router.push('/forum')">
            <el-icon :size="18"><ChatDotSquare /></el-icon>
          </div>
        </el-tooltip>
        <el-tooltip content="公式管理" placement="bottom">
          <div class="gt-topbar-btn" @click="showFormulaManager = true">
            <span style="font-size:16px;font-weight:700;font-style:italic;line-height:18px">ƒx</span>
          </div>
        </el-tooltip>

        <div class="gt-topbar-divider" />

        <!-- 视图切换按钮（三栏/四栏） -->
        <el-tooltip :content="fourColumnMode ? '切换三栏视图' : '切换四栏视图'" placement="bottom">
          <div class="gt-topbar-btn" @click="fourColumnMode = !fourColumnMode">
            <el-icon :size="18"><Grid v-if="!fourColumnMode" /><Menu v-else /></el-icon>
          </div>
        </el-tooltip>
        <el-tooltip content="回收站" placement="bottom">
          <div class="gt-topbar-btn" @click="router.push('/recycle-bin')">
            <el-icon :size="18"><DeleteFilled /></el-icon>
          </div>
        </el-tooltip>
        <el-tooltip content="系统设置" placement="bottom">
          <div class="gt-topbar-btn" @click="router.push('/settings')">
            <el-icon :size="18"><Setting /></el-icon>
          </div>
        </el-tooltip>
        <!-- 后台导入任务指示 -->
        <el-tooltip v-if="bgImportStatus" :content="bgImportStatus.message" placement="bottom">
          <div class="gt-topbar-btn gt-import-indicator" @click="navigateToImport">
            <el-icon :size="18" class="is-loading"><Loading /></el-icon>
            <span class="gt-import-label">导入中</span>
          </div>
        </el-tooltip>

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
              <span v-if="!sidebarCollapsed" class="gt-nav-label">
                {{ item.label }}
                <span v-if="item.maturity === 'pilot'" class="gt-maturity-badge gt-maturity-pilot">试点</span>
                <span v-else-if="item.maturity === 'experimental'" class="gt-maturity-badge gt-maturity-exp">实验</span>
              </span>
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
      <section v-if="!props.hideMiddle && !middleCollapsed" class="gt-middle" :style="{ width: middleWidth + 'px' }" role="main">
        <div class="gt-middle-content">
          <slot name="middle">
            <router-view name="middle" />
          </slot>
        </div>
        <div class="gt-middle-bottom">
          <div class="gt-nav-item" @click="middleCollapsed = true" title="收起列表">
            <el-icon :size="18"><DArrowLeft /></el-icon>
            <span class="gt-nav-label">收起</span>
          </div>
        </div>
      </section>
      <!-- 中间栏收起态 -->
      <div
        v-if="!props.hideMiddle && middleCollapsed"
        class="gt-middle-collapsed"
        @click="middleCollapsed = false"
        title="展开项目列表"
      >
        <div class="gt-middle-collapsed-icon">
          <el-icon :size="18"><DArrowRight /></el-icon>
        </div>
      </div>

      <!-- 右侧拖拽分隔线 -->
      <div v-if="!props.hideMiddle && !middleCollapsed" class="gt-resizer" @mousedown="startResize('right', $event)" />

      <!-- 第3栏：功能目录（四栏模式下显示） -->
      <section
        v-if="fourColumnMode && !catalogCollapsed"
        class="gt-catalog"
        :style="{ width: catalogWidth + 'px' }"
      >
        <slot name="catalog" />
        <div class="gt-catalog-bottom">
          <div class="gt-nav-item" @click="catalogCollapsed = true" title="收起">
            <el-icon :size="18"><DArrowLeft /></el-icon>
            <span class="gt-nav-label">收起</span>
          </div>
        </div>
      </section>
      <!-- 第3栏收起态 -->
      <div
        v-if="fourColumnMode && catalogCollapsed"
        class="gt-catalog-collapsed"
        @click="catalogCollapsed = false"
        title="展开功能目录"
      >
        <div class="gt-catalog-collapsed-icon">
          <el-icon :size="18"><DArrowRight /></el-icon>
        </div>
      </div>

      <!-- 第3/4栏分隔线 -->
      <div v-if="fourColumnMode && !catalogCollapsed" class="gt-resizer" @mousedown="startResize('catalog', $event)" />

      <!-- 右侧栏：项目详情 / 主内容区 -->
      <section class="gt-detail" :role="props.hideMiddle ? 'main' : 'complementary'">
        <slot name="detail">
          <router-view name="detail" />
        </slot>
      </section>
    </div>

    <!-- 全局公式管理弹窗 -->
    <FormulaManagerDialog
      v-model="showFormulaManager"
      :rows="[]"
      :project-id="currentProjectId"
      :year="currentYear"
      @saved="onFormulaSaved"
      @applied="onFormulaApplied"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import {
  Odometer, FolderOpened, User, Reading, Timer, Connection,
  Stamp, Box, Setting, Bell, ArrowDown, SwitchButton,
  DArrowLeft, DArrowRight, Cpu, DeleteFilled, Grid, Menu, Paperclip,
  DataAnalysis, UserFilled, ChatDotSquare, Suitcase, Document, Loading,
} from '@element-plus/icons-vue'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

// ── Props ──
const props = defineProps<{
  hideMiddle?: boolean
  fourColumn?: boolean
  catalogTitle?: string
}>()

// ── 导航项 ──
const navItems = [
  { key: 'dashboard', label: '仪表盘', icon: Odometer, path: '/', maturity: 'production' },
  { key: 'projects', label: '项目', icon: FolderOpened, path: '/projects', maturity: 'production' },
  { key: 'team', label: '人员', icon: User, path: '/settings/staff', maturity: 'production' },
  { key: 'workhours', label: '工时', icon: Timer, path: '/work-hours', maturity: 'production' },
  { key: 'mgmt-dashboard', label: '看板', icon: DataAnalysis, path: '/dashboard/management', maturity: 'production' },
  { key: 'consolidation', label: '合并', icon: Connection, path: '/consolidation', maturity: 'pilot' },
  { key: 'confirmation', label: '函证', icon: Stamp, path: '/confirmation', maturity: 'pilot' },
  { key: 'archive', label: '归档', icon: Box, path: '/archive', maturity: 'production' },
  { key: 'attachments', label: '附件', icon: Paperclip, path: '/attachments', maturity: 'pilot' },
  { key: 'users', label: '用户', icon: UserFilled, path: '/settings/users', maturity: 'production' },
]

const activeNav = computed(() => {
  const p = route.path
  if (p === '/') return 'dashboard'
  // 顶部栏路由不高亮左侧导航
  const topBarPaths = ['/knowledge', '/private-storage', '/settings/ai-models', '/settings/report-format', '/forum', '/recycle-bin', '/settings']
  if (topBarPaths.some(tp => p === tp || (tp !== '/settings' && p.startsWith(tp)))) return ''
  // 合并项目详情页（/projects/:id/consolidation）高亮"合并"而非"项目"
  if (p.match(/^\/projects\/[^/]+\/consolidation/)) return 'consolidation'
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

const emit = defineEmits<{
  (e: 'nav-change', key: string): void
  (e: 'view-change', mode: 'three' | 'four'): void
}>()

function onNavClick(item: typeof navItems[0]) {
  emit('nav-change', item.key)
  router.push(item.path)
}

// ── 布局状态 ──
const STORAGE_KEY = 'gt-layout-prefs'
const sidebarCollapsed = ref(false)
const sidebarWidth = ref(220)
const middleWidth = ref(340)
const middleCollapsed = ref(false)
const catalogWidth = ref(280)
const catalogCollapsed = ref(false)
const fourColumnMode = ref(false)
const fullscreen = ref(false)
const showFormulaManager = ref(false)
const currentProjectId = computed(() => (route.params.projectId as string) || '')
const currentYear = computed(() => Number(route.query.year) || new Date().getFullYear() - 1)

// 四栏模式由 props 或用户切换控制
watch(() => props.fourColumn, (v) => {
  if (v !== undefined) fourColumnMode.value = v
}, { immediate: true })

// 视图模式变化时通知父组件
watch(fourColumnMode, (v) => {
  if (v) catalogCollapsed.value = false  // 切换到四栏时自动展开 catalog
  emit('view-change', v ? 'four' : 'three')
})

// 监听折叠状态变化自动保存
watch([sidebarCollapsed, middleCollapsed, catalogCollapsed], () => savePrefs())

function loadPrefs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const prefs = JSON.parse(raw)
      sidebarCollapsed.value = prefs.collapsed ?? false
      sidebarWidth.value = prefs.sidebarWidth ?? 220
      middleWidth.value = prefs.middleWidth ?? 340
      middleCollapsed.value = prefs.middleCollapsed ?? false
      catalogWidth.value = prefs.catalogWidth ?? 280
      catalogCollapsed.value = prefs.catalogCollapsed ?? false
    }
  } catch { /* ignore */ }
}

function savePrefs() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    collapsed: sidebarCollapsed.value,
    sidebarWidth: sidebarWidth.value,
    middleWidth: middleWidth.value,
    middleCollapsed: middleCollapsed.value,
    catalogWidth: catalogWidth.value,
    catalogCollapsed: catalogCollapsed.value,
  }))
}

// ── 拖拽调整宽度 ──
let resizing: 'left' | 'right' | 'catalog' | null = null
let startX = 0
let startW = 0

function startResize(side: 'left' | 'right' | 'catalog', e: MouseEvent) {
  resizing = side
  startX = e.clientX
  startW = side === 'left' ? sidebarWidth.value : side === 'right' ? middleWidth.value : catalogWidth.value
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
  } else if (resizing === 'right') {
    middleWidth.value = Math.max(250, Math.min(500, startW + dx))
  } else if (resizing === 'catalog') {
    catalogWidth.value = Math.max(200, Math.min(450, startW + dx))
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

// ── 移动端手势支持 ──
let touchStartX = 0
let touchStartY = 0
const SWIPE_THRESHOLD = 60

function onTouchStart(e: TouchEvent) {
  const touch = e.touches[0]
  touchStartX = touch.clientX
  touchStartY = touch.clientY
}

function onTouchEnd(e: TouchEvent) {
  const touch = e.changedTouches[0]
  const dx = touch.clientX - touchStartX
  const dy = touch.clientY - touchStartY

  // 只处理水平滑动（水平位移 > 垂直位移）
  if (Math.abs(dx) < SWIPE_THRESHOLD || Math.abs(dx) < Math.abs(dy)) return

  if (dx > 0) {
    // 右滑：展开导航
    sidebarCollapsed.value = false
  } else {
    // 左滑：收起导航
    sidebarCollapsed.value = true
  }
}

// ── 后台导入任务全局轮询 ──
const bgImportStatus = ref<{ projectId: string; message: string; progress: number } | null>(null)
let importPollTimer: ReturnType<typeof setInterval> | null = null

async function pollImportQueue() {
  const projectId = route.params.projectId as string
  if (!projectId) {
    bgImportStatus.value = null
    return
  }
  try {
    const { data: statusData } = await http.get(`/api/data-lifecycle/import-queue/${projectId}`, {
      validateStatus: (s: number) => s < 600,
    })
    const status = statusData.data ?? statusData
    if (status && status.status === 'processing') {
      bgImportStatus.value = {
        projectId,
        message: `[${status.progress ?? 0}%] ${status.message || '后台导入中...'}`,
        progress: status.progress ?? 0,
      }
    } else if (bgImportStatus.value) {
      const prev = bgImportStatus.value
      bgImportStatus.value = null
      if (prev.progress >= 0 && status?.status !== 'failed') {
        ElMessage.success(status?.message || '后台导入已完成')
      } else if (status?.status === 'failed') {
        ElMessage.error(status?.message || '后台导入失败')
      }
    }
  } catch {
    // ignore
  }
}

function navigateToImport() {
  const pid = bgImportStatus.value?.projectId || route.params.projectId
  if (pid) {
    router.push({ path: `/projects/${pid}/ledger`, query: { import: '1' } })
  }
}

watch(() => route.params.projectId, (newId) => {
  if (importPollTimer) { clearInterval(importPollTimer); importPollTimer = null }
  bgImportStatus.value = null
  if (newId) {
    pollImportQueue()
    importPollTimer = setInterval(pollImportQueue, 10000)
  }
}, { immediate: true })

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}

// 监听子组件打开公式管理的自定义事件
function onOpenFormulaEvent(e: Event) {
  const detail = (e as CustomEvent).detail
  showFormulaManager.value = true
  // 如果有 nodeKey，后续 FormulaManagerDialog 可以通过 props 或 watch 定位到对应节点
  if (detail?.nodeKey) {
    // 存储到 sessionStorage 供 FormulaManagerDialog 读取
    sessionStorage.setItem('gt-formula-target-node', detail.nodeKey)
  }
}

// 公式保存/应用后广播通知所有表刷新
function onFormulaSaved() {
  document.dispatchEvent(new CustomEvent('gt-formula-changed', { detail: { action: 'saved' } }))
}
function onFormulaApplied() {
  document.dispatchEvent(new CustomEvent('gt-formula-changed', { detail: { action: 'applied' } }))
}

function onSwitchFourCol(e: Event) {
  const detail = (e as CustomEvent).detail
  // Only handle the initial dispatch (from ConsolidationIndex), not re-dispatches
  if (detail?._redispatched) return
  fourColumnMode.value = true
  catalogCollapsed.value = false
  // Re-dispatch once after catalog mounts so it can switch to the right tab
  if (detail?.tab) {
    setTimeout(() => {
      window.dispatchEvent(new CustomEvent('gt-switch-four-col', { detail: { ...detail, _redispatched: true } }))
    }, 150)
  }
}

onMounted(() => {
  loadPrefs()
  document.addEventListener('keydown', onKeydown)
  document.addEventListener('gt-open-formula-manager', onOpenFormulaEvent)
  window.addEventListener('gt-switch-four-col', onSwitchFourCol)
  // 移动端手势
  document.addEventListener('touchstart', onTouchStart, { passive: true })
  document.addEventListener('touchend', onTouchEnd, { passive: true })
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('touchstart', onTouchStart)
  document.removeEventListener('gt-open-formula-manager', onOpenFormulaEvent)
  window.removeEventListener('gt-switch-four-col', onSwitchFourCol)
  document.removeEventListener('touchend', onTouchEnd)
  if (importPollTimer) { clearInterval(importPollTimer); importPollTimer = null }
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

.gt-topbar-divider {
  width: 1px;
  height: 20px;
  background: var(--gt-color-border-light);
  margin: 0 2px;
}

.gt-import-indicator {
  color: var(--gt-color-primary);
  background: var(--gt-color-primary-bg);
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: var(--gt-radius-sm);
}
.gt-import-indicator:hover {
  background: var(--gt-color-primary-lighter);
}
.gt-import-label {
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
}

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
.gt-maturity-badge {
  font-size: 10px; font-weight: 600; padding: 1px 4px; border-radius: 3px;
  margin-left: 4px; vertical-align: middle; line-height: 1;
}
.gt-maturity-pilot { background: #fef0e6; color: #e6a23c; }
.gt-maturity-exp { background: #fde2e2; color: #f56c6c; }

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
  z-index: 5;
  transition: background var(--gt-transition-fast);
}
.gt-resizer:hover,
.gt-resizer:active {
  background: var(--gt-color-primary-lighter);
}

/* ── 中间栏 ── */
.gt-middle {
  flex-shrink: 0;
  background: var(--gt-color-bg-white);
  border-right: 1px solid var(--gt-color-border-light);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.gt-middle-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}
.gt-middle-bottom {
  border-top: 1px solid var(--gt-color-border-light);
  padding: var(--gt-space-1);
  flex-shrink: 0;
}
.gt-middle-collapsed {
  width: 24px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  background: #f5f7fa;
  border-right: 1px solid var(--gt-color-border-light);
  cursor: pointer;
  color: var(--gt-color-text-tertiary);
  transition: all var(--gt-transition-fast);
}
.gt-middle-collapsed:hover {
  background: var(--gt-color-primary-bg);
  color: var(--gt-color-primary);
}
.gt-middle-collapsed-icon {
  padding: 12px 0;
  display: flex;
  justify-content: center;
  border-top: 1px solid var(--gt-color-border-light);
}

/* ── 右侧栏 ── */
.gt-detail {
  flex: 1;
  min-width: 0;
  background: var(--gt-color-bg-white);
  overflow-y: auto;
}

/* ── 第3栏：功能目录（四栏模式） ── */
.gt-catalog {
  flex-shrink: 0;
  background: var(--gt-color-bg-white);
  border-right: 1px solid var(--gt-color-border-light);
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.gt-catalog-bottom {
  border-top: 1px solid var(--gt-color-border-light);
  padding: var(--gt-space-1);
  flex-shrink: 0;
}

.gt-catalog-collapsed {
  width: 24px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  background: #f5f7fa;
  border-right: 1px solid var(--gt-color-border-light);
  cursor: pointer;
  color: var(--gt-color-text-tertiary);
  transition: all var(--gt-transition-fast);
}
.gt-catalog-collapsed:hover {
  background: var(--gt-color-primary-bg);
  color: var(--gt-color-primary);
}
.gt-catalog-collapsed-icon {
  padding: 12px 0;
  display: flex;
  justify-content: center;
  border-top: 1px solid var(--gt-color-border-light);
}

/* ── 全屏模式 ── */
.gt-three-col--fullscreen .gt-sidebar,
.gt-three-col--fullscreen .gt-middle,
.gt-three-col--fullscreen .gt-resizer {
  display: none;
}

/* ── 响应式 ── */

/* Desktop: > 1280px — default layout */

/* Tablet: 768px - 1280px */
@media (max-width: 1280px) {
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

/* Tablet: 768px - 1024px — hide middle column */
@media (max-width: 1024px) {
  .gt-middle {
    display: none !important;
  }
  .gt-catalog {
    display: none !important;
  }
}

/* Mobile: < 768px — single column layout */
@media (max-width: 768px) {
  .gt-three-col {
    flex-direction: column;
  }
  .gt-sidebar {
    position: fixed;
    z-index: 1000;
    height: auto;
    width: 100% !important;
    flex-direction: row;
    overflow-x: auto;
    border-right: none;
    border-bottom: 1px solid var(--gt-border, #e4e7ed);
  }
  .gt-sidebar .gt-nav-list {
    flex-direction: row;
    gap: 0;
  }
  .gt-sidebar .gt-nav-item {
    padding: 8px 12px;
    flex-direction: column;
    font-size: 11px;
  }
  .gt-sidebar .gt-nav-label {
    display: block;
    font-size: 10px;
  }
  .gt-middle {
    display: none !important;
  }
  .gt-catalog {
    display: none !important;
  }
  .gt-main-area {
    margin-top: 56px;
    width: 100%;
  }
  .gt-topbar {
    font-size: 14px;
  }
  .gt-topbar .gt-logo-text {
    display: none;
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
