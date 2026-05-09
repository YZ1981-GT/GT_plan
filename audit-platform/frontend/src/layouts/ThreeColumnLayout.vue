<template>
  <div class="gt-three-col" :class="{ 'gt-three-col--collapsed': sidebarCollapsed, 'gt-three-col--fullscreen': fullscreen }">
    <!-- 顶部导航栏 -->
    <header class="gt-topbar">
      <div class="gt-topbar-left">
        <div class="gt-logo" @click="sidebarCollapsed = !sidebarCollapsed" title="折叠/展开导航">
          <img src="/gt-logo-white.png" alt="Grant Thornton 致同" class="gt-logo-img" />
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
        <!-- 通知铃铛 -->
        <slot name="nav-notifications" />

        <!-- 显示设置 Aa -->
        <el-popover placement="bottom" :width="240" trigger="click">
          <template #reference>
            <el-tooltip content="显示设置" placement="bottom">
              <div class="gt-topbar-btn">
                <span class="gt-topbar-text-icon">Aa</span>
              </div>
            </el-tooltip>
          </template>
          <div class="gt-display-prefs-panel">
            <div class="gt-dp-row">
              <span class="gt-dp-label">金额单位</span>
              <el-radio-group v-model="displayPrefs.amountUnit" size="small" @change="(v: any) => displayPrefs.setUnit(v)">
                <el-radio-button v-for="opt in displayPrefs.unitOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</el-radio-button>
              </el-radio-group>
            </div>
            <div class="gt-dp-row">
              <span class="gt-dp-label">表格字号</span>
              <el-radio-group v-model="displayPrefs.fontSize" size="small" @change="(v: any) => displayPrefs.setFontSize(v)">
                <el-radio-button v-for="opt in displayPrefs.fontOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</el-radio-button>
              </el-radio-group>
            </div>
            <div class="gt-dp-row">
              <span class="gt-dp-label">小数位数</span>
              <el-radio-group v-model="displayPrefs.decimals" size="small" @change="(v: any) => displayPrefs.setDecimals(v)">
                <el-radio-button :value="0">整数</el-radio-button>
                <el-radio-button :value="2">2位</el-radio-button>
                <el-radio-button :value="4">4位</el-radio-button>
              </el-radio-group>
            </div>
            <div class="gt-dp-row">
              <span class="gt-dp-label">零值显示</span>
              <el-switch v-model="displayPrefs.showZero" size="small" active-text="0.00" inactive-text="—" @change="(v: any) => displayPrefs.setShowZero(v)" />
            </div>
            <div class="gt-dp-row">
              <span class="gt-dp-label">负数红色</span>
              <el-switch v-model="displayPrefs.negativeRed" size="small" @change="(v: any) => displayPrefs.setNegativeRed(v)" />
            </div>
            <div class="gt-dp-row">
              <span class="gt-dp-label">变动高亮</span>
              <el-radio-group v-model="displayPrefs.highlightThreshold" size="small" @change="(v: any) => displayPrefs.setHighlightThreshold(v)">
                <el-radio-button :value="0">关</el-radio-button>
                <el-radio-button :value="0.1">10%</el-radio-button>
                <el-radio-button :value="0.2">20%</el-radio-button>
                <el-radio-button :value="0.5">50%</el-radio-button>
              </el-radio-group>
            </div>
          </div>
        </el-popover>

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

        <div class="gt-topbar-divider" />

        <!-- 复核收件箱入口（reviewer/partner/admin 可见） -->
        <slot name="nav-review-inbox" />

        <!-- EQCR 独立复核工作台入口（partner/admin 可见，Round 5） -->
        <slot name="nav-eqcr" />
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
                <span v-else-if="item.maturity === 'developing'" class="gt-maturity-badge gt-maturity-dev">开发中</span>
              </span>
            </transition>
          </div>
        </nav>
        <div class="gt-sidebar-bottom">
          <!-- 工具簇（从顶栏迁移过来，避免顶栏过载） -->
          <div class="gt-sidebar-tools-title" v-if="!sidebarCollapsed">工具</div>
          <div class="gt-nav-item gt-nav-item--tool" :class="{ 'gt-nav-item--active': route.path.startsWith('/knowledge') }" @click="router.push('/knowledge')" title="知识库">
            <el-icon :size="18"><Reading /></el-icon>
            <transition name="gt-fade">
              <span v-if="!sidebarCollapsed" class="gt-nav-label">知识库</span>
            </transition>
          </div>
          <div class="gt-nav-item gt-nav-item--tool" :class="{ 'gt-nav-item--active': activeToolPath === '/private-storage' }" @click="router.push('/private-storage')" title="私人库">
            <el-icon :size="18"><Suitcase /></el-icon>
            <transition name="gt-fade">
              <span v-if="!sidebarCollapsed" class="gt-nav-label">私人库</span>
            </transition>
          </div>
          <div class="gt-nav-item gt-nav-item--tool" :class="{ 'gt-nav-item--active': activeToolPath === '/settings/ai-models' }" @click="router.push('/settings/ai-models')" title="AI 模型">
            <el-icon :size="18"><Cpu /></el-icon>
            <transition name="gt-fade">
              <span v-if="!sidebarCollapsed" class="gt-nav-label">AI 模型</span>
            </transition>
          </div>
          <div class="gt-nav-item gt-nav-item--tool" :class="{ 'gt-nav-item--active': activeToolPath === '/settings/report-format' }" @click="router.push('/settings/report-format')" title="排版模板">
            <el-icon :size="18"><Document /></el-icon>
            <transition name="gt-fade">
              <span v-if="!sidebarCollapsed" class="gt-nav-label">排版模板</span>
            </transition>
          </div>
          <div class="gt-nav-item gt-nav-item--tool" :class="{ 'gt-nav-item--active': activeToolPath === '/forum' }" @click="router.push('/forum')" title="吐槽求助">
            <el-icon :size="18"><ChatDotSquare /></el-icon>
            <transition name="gt-fade">
              <span v-if="!sidebarCollapsed" class="gt-nav-label">吐槽求助</span>
            </transition>
          </div>
          <div class="gt-nav-item gt-nav-item--tool" @click="showFormulaManager = true" title="公式管理">
            <span class="gt-tool-text-icon" style="font-style:italic;font-weight:700">ƒx</span>
            <transition name="gt-fade">
              <span v-if="!sidebarCollapsed" class="gt-nav-label">公式管理</span>
            </transition>
          </div>
          <div class="gt-nav-item gt-nav-item--tool" @click="showCustomQuery = true" title="自定义查询">
            <span class="gt-tool-text-icon">🔍</span>
            <transition name="gt-fade">
              <span v-if="!sidebarCollapsed" class="gt-nav-label">自定义查询</span>
            </transition>
          </div>

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

    <!-- 全局自定义查询弹窗 -->
    <CustomQueryDialog
      v-model="showCustomQuery"
      :project-id="currentProjectId"
      :year="currentYear"
    />

    <!-- 全局快捷键帮助面板 [R7-S2-12] -->
    <ShortcutHelpDialog v-model="showShortcutHelp" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useRoleContextStore } from '@/stores/roleContext'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import {
  Odometer, FolderOpened, User, Reading, Timer, Connection,
  Stamp, Box, Setting, ArrowDown, SwitchButton,
  DArrowLeft, DArrowRight, Cpu, DeleteFilled, Grid, Menu, Paperclip,
  DataAnalysis, UserFilled, ChatDotSquare, Suitcase, Document, Loading,
} from '@element-plus/icons-vue'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'
import CustomQueryDialog from '@/components/query/CustomQueryDialog.vue'
import ShortcutHelpDialog from '@/components/common/ShortcutHelpDialog.vue'
import { eventBus } from '@/utils/eventBus'
import { operationHistory } from '@/utils/operationHistory'
import { createSSE, type SSEConnection } from '@/utils/sse'
import { events as eventPaths } from '@/services/apiPaths'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const displayPrefs = useDisplayPrefsStore()

// ── Props ──
const props = defineProps<{
  hideMiddle?: boolean
  fourColumn?: boolean
  catalogTitle?: string
}>()

// ── 导航项（R7-S2-01：角色感知动态化） ──
const roleStore = useRoleContextStore()

const FALLBACK_NAV = [
  { key: 'dashboard', label: '仪表盘', icon: Odometer, path: '/', maturity: 'production', roles: null },
  { key: 'projects', label: '项目', icon: FolderOpened, path: '/projects', maturity: 'production', roles: null },
  { key: 'team', label: '人员档案', icon: User, path: '/settings/staff', maturity: 'production', roles: ['admin', 'partner', 'manager'] },
  { key: 'workhours', label: '工时', icon: Timer, path: '/work-hours', maturity: 'production', roles: ['admin', 'partner', 'manager', 'auditor', 'eqcr'] },
  { key: 'mgmt-dashboard', label: '看板', icon: DataAnalysis, path: '/dashboard/management', maturity: 'production', roles: ['admin', 'partner', 'manager'] },
  { key: 'consolidation', label: '合并', icon: Connection, path: '/consolidation', maturity: 'production', roles: ['admin', 'partner', 'manager'] },
  { key: 'confirmation', label: '函证', icon: Stamp, path: '/confirmation', maturity: 'developing', roles: null },
  { key: 'archive', label: '归档', icon: Box, path: '/archive', maturity: 'production', roles: ['admin', 'partner', 'manager'] },
  { key: 'attachments', label: '附件', icon: Paperclip, path: '/attachments', maturity: 'production', roles: ['admin', 'partner', 'manager', 'auditor'] },
  { key: 'users', label: '账号权限', icon: UserFilled, path: '/settings/users', maturity: 'production', roles: ['admin'] },
]

/**
 * 按角色过滤 + 覆盖路径
 * - roles=null 表示所有角色可见
 * - 按角色覆盖"看板"默认路径
 */
function buildNavForRole(nav: typeof FALLBACK_NAV, role: string) {
  return nav
    .filter(item => !item.roles || item.roles.includes(role))
    .map(item => {
      if (item.key === 'mgmt-dashboard') {
        if (role === 'manager') return { ...item, path: '/dashboard/manager' }
        if (role === 'partner') return { ...item, path: '/dashboard/partner' }
      }
      return item
    })
}

const navItems = computed(() => buildNavForRole(FALLBACK_NAV, roleStore.effectiveRole || 'auditor'))

const activeNav = computed(() => {
  const p = route.path
  if (p === '/') return 'dashboard'
  // 顶部栏路由不高亮左侧导航
  const topBarPaths = ['/recycle-bin', '/settings']
  if (topBarPaths.some(tp => p === tp || (tp !== '/settings' && p.startsWith(tp)))) return ''
  // 合并项目详情页（/projects/:id/consolidation）高亮"合并"而非"项目"
  if (p.match(/^\/projects\/[^/]+\/consolidation/)) return 'consolidation'
  for (const item of navItems.value) {
    if (item.path !== '/' && p.startsWith(item.path)) return item.key
  }
  if (p.startsWith('/projects')) return 'projects'
  return 'dashboard'
})

const currentModule = computed(() => {
  const item = navItems.value.find(n => n.key === activeNav.value)
  return item?.label || ''
})

// 工具区 active 判断
const activeToolPath = computed(() => {
  const p = route.path
  const toolPaths = ['/knowledge', '/private-storage', '/settings/ai-models', '/settings/report-format', '/forum']
  return toolPaths.find(tp => p.startsWith(tp)) || ''
})

const emit = defineEmits<{
  (e: 'nav-change', key: string): void
  (e: 'view-change', mode: 'three' | 'four'): void
}>()

function onNavClick(item: (typeof FALLBACK_NAV)[0]) {
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
const showCustomQuery = ref(false)
const showShortcutHelp = ref(false)
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
    // S7: 改轮询 import_jobs 表（持久化），不再依赖 ImportQueueService 内存态
    // 后端重启后仍能看到正在运行的 job
    const statusData = await api.get(`/api/projects/${projectId}/ledger-import/jobs/latest`, {
      validateStatus: (s: number) => s < 600,
    })
    const status = statusData
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

// ── SSE 全局连接 ──
let sseConnection: SSEConnection | null = null

function connectSSE(projectId: string) {
  // 关闭旧连接
  if (sseConnection) {
    sseConnection.close()
    sseConnection = null
  }
  if (!projectId) return

  const url = eventPaths.stream(projectId)
  sseConnection = createSSE(url, { maxRetries: 5, retryInterval: 3000 })

  sseConnection.onOpen(() => {
    eventBus.emit('sse:connected')
  })

  sseConnection.onMessage((data, _event) => {
    if (!data || !data.event_type) return
    if (data.event_type === 'sync.failed') {
      eventBus.emit('sse:sync-failed', data)
    } else {
      eventBus.emit('sse:sync-event', data)
    }
  })

  sseConnection.onError(() => {
    eventBus.emit('sse:disconnected')
  })
}

// 监听项目切换，自动重连 SSE
watch(() => route.params.projectId, (newId) => {
  connectSSE(newId as string || '')
}, { immediate: true })

// 监听子组件打开公式管理的自定义事件
function onOpenFormulaEvent(payload: { nodeKey?: string }) {
  showFormulaManager.value = true
  // 如果有 nodeKey，后续 FormulaManagerDialog 可以通过 props 或 watch 定位到对应节点
  if (payload?.nodeKey) {
    // 存储到 sessionStorage 供 FormulaManagerDialog 读取
    sessionStorage.setItem('gt-formula-target-node', payload.nodeKey)
  }
}

// 公式保存/应用后广播通知所有表刷新
function onFormulaSaved() {
  eventBus.emit('formula-changed', { action: 'saved' })
}
function onFormulaApplied() {
  eventBus.emit('formula-changed', { action: 'applied' })
}

function onSwitchFourCol(payload: { tab?: string }) {
  fourColumnMode.value = true
  catalogCollapsed.value = false
  // mitt 不需要 _redispatched 补丁：直接延迟通知 catalog 切换 tab
  if (payload?.tab) {
    setTimeout(() => {
      eventBus.emit('four-col-switch', payload)
    }, 150)
  }
}

/** 全局快捷键撤销 */
function onShortcutUndo() {
  operationHistory.undo()
}

onMounted(() => {
  loadPrefs()
  document.addEventListener('keydown', onKeydown)
  eventBus.on('open-formula-manager', onOpenFormulaEvent)
  eventBus.on('four-col-switch', onSwitchFourCol)
  eventBus.on('shortcut:undo', onShortcutUndo)
  eventBus.on('shortcut:help', () => { showShortcutHelp.value = true })
  // 移动端手势
  document.addEventListener('touchstart', onTouchStart, { passive: true })
  document.addEventListener('touchend', onTouchEnd, { passive: true })
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('touchstart', onTouchStart)
  eventBus.off('open-formula-manager', onOpenFormulaEvent)
  eventBus.off('four-col-switch', onSwitchFourCol)
  eventBus.off('shortcut:undo', onShortcutUndo)
  document.removeEventListener('touchend', onTouchEnd)
  if (importPollTimer) { clearInterval(importPollTimer); importPollTimer = null }
  // 关闭 SSE 连接
  if (sseConnection) { sseConnection.close(); sseConnection = null }
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

/* ── 顶部导航栏（致同品牌深紫） ── */
.gt-topbar {
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--gt-space-4);
  background: var(--gt-color-primary);
  border-bottom: none;
  flex-shrink: 0;
  z-index: 100;
}

.gt-topbar-left { display: flex; align-items: center; }
.gt-topbar-center { flex: 1; padding: 0 var(--gt-space-4); }
.gt-topbar-center :deep(.el-breadcrumb__inner),
.gt-topbar-center :deep(.el-breadcrumb__separator) { color: rgba(255, 255, 255, 0.7); }
.gt-topbar-center :deep(.el-breadcrumb__inner.is-link) { color: #fff; }
.gt-topbar-right { display: flex; align-items: center; gap: 4px; }
.gt-topbar-right > * { display: inline-flex; align-items: center; }

.gt-logo {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--gt-radius-sm);
  transition: background var(--gt-transition-fast);
}
.gt-logo:hover { background: rgba(255, 255, 255, 0.1); }
.gt-logo-img { height: 40px; width: auto; }
.gt-logo-text {
  font-size: 14px;
  font-weight: 700;
  color: #fff;
  white-space: nowrap;
}

.gt-topbar-btn {
  cursor: pointer;
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: rgba(255, 255, 255, 0.9);
  font-size: 14px;
  transition: background 0.15s ease;
}
.gt-topbar-btn:hover { background: rgba(255, 255, 255, 0.12); }
.gt-topbar-text-icon {
  font-size: 14px;
  font-weight: 600;
  line-height: 1;
}

/* 顶栏内所有 el-button text / el-badge 适配深紫背景 */
.gt-topbar-right :deep(.el-button--text) { color: rgba(255, 255, 255, 0.85); }
.gt-topbar-right :deep(.el-button--text:hover) { color: #fff; background: rgba(255, 255, 255, 0.1); }
.gt-topbar-right :deep(.el-icon) { color: rgba(255, 255, 255, 0.9); }
.gt-topbar-right :deep(.el-icon svg) { fill: currentColor; }
.gt-topbar-right :deep(.el-dropdown) { color: #fff; }

.gt-topbar-divider {
  width: 1px;
  height: 20px;
  background: rgba(255, 255, 255, 0.2);
  margin: 0 8px;
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
.gt-user-info:hover { background: rgba(255, 255, 255, 0.15); }
.gt-avatar {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
  font-weight: 600;
  font-size: 13px;
  border: 1px solid rgba(255, 255, 255, 0.3);
}
.gt-username {
  font-size: var(--gt-font-size-sm);
  font-weight: 500;
  color: #fff;
}

/* ── 三栏主体 ── */
.gt-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

/* ── 左侧栏（致同风格：浅灰底 + 紫色激活） ── */
.gt-sidebar {
  display: flex;
  flex-direction: column;
  background: #f8f7fc;
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
  min-height: 0; /* 允许 flex 子项收缩以触发滚动 */
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
.gt-maturity-dev { background: #e8eaed; color: #909399; }

.gt-sidebar-bottom {
  border-top: 1px solid var(--gt-color-border-light);
  padding: var(--gt-space-1);
  flex-shrink: 0; /* 工具区不被压缩，主导航区滚动 */
  max-height: 45vh; /* 窗口极小时工具区也不能占满，留空间给主导航 */
  overflow-y: auto;
}

/* 工具簇（侧栏底部） */
.gt-sidebar-tools-title {
  font-size: 11px;
  color: var(--gt-color-text-tertiary, #909399);
  padding: 8px 14px 4px;
  letter-spacing: 0.5px;
}
.gt-nav-item--tool {
  font-size: 13px;
  color: var(--gt-color-text-secondary, #606266);
}
.gt-nav-item--tool:hover {
  background: rgba(75, 45, 119, 0.05);
  color: var(--gt-color-primary);
}
.gt-tool-text-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  font-size: 14px;
  line-height: 1;
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

/* ── 显示设置面板 ── */
.gt-display-prefs-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.gt-dp-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-dp-label {
  font-size: 12px;
  color: #666;
  min-width: 56px;
  flex-shrink: 0;
}
.gt-dp-row :deep(.el-radio-button__inner) {
  padding: 4px 10px;
  font-size: 11px;
}
</style>
