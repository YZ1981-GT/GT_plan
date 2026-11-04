<template>
  <div class="citar-root">
    <!-- 项目列表：页面自带顶栏（CITAR ProjectListScreen） -->
    <slot v-if="mode === 'list'" />

    <!-- 新建 / 修改项目：只有顶栏（CITAR ProjectCreateScreen 的 create-topbar） -->
    <div v-else-if="mode === 'create'" class="create-screen">
      <header class="create-topbar">
        <img class="create-topbar__logo" src="/logo-citar-light.png" alt="致同 CITAR" />
        <button class="create-topbar__back" type="button" @click="router.push('/projects')">返回项目列表</button>
      </header>
      <div class="citar-create-body"><slot /></div>
    </div>

    <!-- 项目内（CITAR ProjectShell） -->
    <div v-else class="shell">
      <header class="shell-topbar">
        <img class="shell-topbar__logo" src="/logo-citar-light.png" alt="致同 CITAR" />
        <div class="shell-topbar__user">
          <span>{{ userName }}</span>
          <button v-if="isAdmin" class="shell-topbar__logout" type="button" @click="router.push('/settings/users')">账号权限</button>
          <button class="shell-topbar__logout" type="button" @click="router.push('/projects')">项目列表</button>
          <button class="shell-topbar__logout" type="button" @click="logout">退出登录</button>
        </div>
      </header>

      <div class="shell-projectbar">
        <span class="shell-projectbar__name">{{ projectTitle }}</span>
        <span v-for="f in projectFields" :key="f.label" class="shell-projectbar__field">
          <span class="shell-projectbar__label">{{ f.label }}</span>
          <span class="shell-projectbar__value" :class="{ 'shell-projectbar__value--empty': !f.value }">{{ f.value || '—' }}</span>
        </span>
        <button v-if="segment !== CITAR_HOME_SEGMENT" class="shell-projectbar__back" type="button" @click="goSegment(CITAR_HOME_SEGMENT)">← 返回</button>
      </div>

      <div class="shell-body">
        <!-- 一级栏：按业务分组（用户 2026-11-02 给的分组图），组标题 + 带图标的菜单项 -->
        <!-- 可收起：收起后只留图标（悬停显示菜单名），组标题换成分隔线；开合状态记在本机 -->
        <nav
          class="shell-sidebar citar-nav"
          :class="{ 'citar-nav--collapsed': navCollapsed }"
          aria-label="项目菜单"
        >
          <!-- 栏高 = 窗口高减顶部两行；菜单区放不下时自己滚，开合按钮固定在栏底 -->
          <div class="citar-nav__menu">
            <section v-for="(group, gi) in CITAR_NAV_GROUPS" :key="group.title" class="citar-nav__group">
              <div v-if="!navCollapsed" class="citar-nav__title">{{ group.title }}</div>
              <div v-else-if="gi > 0" class="citar-nav__divider" role="separator" />
              <button
                v-for="item in group.items"
                :key="item.key"
                type="button"
                class="citar-nav__item"
                :class="{ 'citar-nav__item--active': segment === item.segment }"
                :title="navCollapsed ? item.label : undefined"
                :aria-label="navCollapsed ? item.label : undefined"
                :aria-current="segment === item.segment ? 'page' : undefined"
                @click="onNavClick(item)"
              >
                <el-icon class="citar-nav__icon" :size="17"><component :is="NAV_ICONS[item.icon]" /></el-icon>
                <template v-if="!navCollapsed">
                  <span class="citar-nav__label">{{ item.label }}</span>
                  <span v-if="item.badge" class="citar-nav__badge">{{ item.badge }}</span>
                  <span v-if="item.segment === CITAR_WORKPAPER_SEGMENT" class="shell-nav__caret">{{ subnavOpen && segment === item.segment ? '▾' : '▸' }}</span>
                </template>
              </button>
            </section>
          </div>
          <button
            type="button"
            class="citar-nav__toggle"
            :title="navCollapsed ? '展开菜单' : '收起菜单'"
            :aria-label="navCollapsed ? '展开菜单' : '收起菜单'"
            :aria-expanded="!navCollapsed"
            @click="toggleNav"
          >
            <el-icon class="citar-nav__icon" :size="16"><DArrowRight v-if="navCollapsed" /><DArrowLeft v-else /></el-icon>
            <span v-if="!navCollapsed" class="citar-nav__label">收起菜单</span>
          </button>
        </nav>

        <!-- 税务底稿 / 汇算申报表：目录栏由页面自己渲染（底稿目录开合经 CITAR_SUBNAV_OPEN_KEY 下发），内容区不留内边距 -->
        <main class="shell-content" :class="{ 'citar-content--flush': CITAR_FLUSH_SEGMENTS.has(segment || '') }">
          <slot />
        </main>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * CITAR 版式外壳（移植自 CITAR src/screens/shell/ProjectShell.tsx 与 ProjectListScreen / ProjectCreateScreen 的顶栏）。
 * 由 DefaultLayout 在 citarLayoutMode 命中时渲染，路由内容经默认插槽放进来。
 */
import { computed, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { refreshCurrentUser } from '@/composables/useManualEditPermission'
import { getProject } from '@/services/auditPlatformApi'
import { api } from '@/services/apiProxy'
import type { Component } from 'vue'
import {
  Connection, DArrowLeft, DArrowRight, Document, DocumentChecked, EditPen, Grid, Notebook, Search, Tickets, Upload,
} from '@element-plus/icons-vue'
import {
  CITAR_FLUSH_SEGMENTS,
  CITAR_HOME_SEGMENT,
  CITAR_NAV_GROUPS,
  CITAR_PROJECT_KEY,
  CITAR_SUBNAV_OPEN_KEY,
  CITAR_WORKPAPER_SEGMENT,
  citarLayoutMode,
  citarSegment,
  type CitarNavItem,
} from './citarRoutes'
import './styles/citar-tokens.css'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const mode = computed(() => citarLayoutMode(route.path) ?? 'project')
const segment = computed(() => citarSegment(route.path))
const projectId = computed(() => (mode.value === 'project' ? String(route.params.projectId || '') : ''))

const userName = computed(() => authStore.username || authStore.user?.username || '')
const isAdmin = computed(() => authStore.user?.role === 'admin')

// ── 项目信息行 ──
const project = ref<Record<string, any> | null>(null)
provide(CITAR_PROJECT_KEY, project)
/** 账号 id → 用户名（签字合伙人 / 项目经理存的是 users 表 id） */
const userNames = ref<Record<string, string>>({})
let usersLoaded = false

async function loadUserNames() {
  if (usersLoaded) return
  usersLoaded = true
  try {
    const list = await api.get('/api/users/', { _silent: true } as any)
    const names: Record<string, string> = {}
    for (const u of (Array.isArray(list) ? list : []) as any[]) names[u.id] = u.full_name || u.username
    userNames.value = names
  } catch {
    // 非管理员可能无权读账号列表：人员显示「—」，不影响进入项目
  }
}

watch(
  projectId,
  async (pid) => {
    project.value = null
    if (!pid) return
    void loadUserNames()
    // 账号权限「允许修改」可能被管理员改过：进入项目时重读，不必重新登录（spec citar-manual-edit-permission R5）
    void refreshCurrentUser()
    try {
      const p = await getProject(pid)
      if (projectId.value === pid) project.value = p as any
    } catch {
      // 读不到项目：信息行显示占位，菜单仍可用
    }
  },
  { immediate: true },
)

const projectTitle = computed(() => project.value?.short_name || project.value?.name || '项目')
const projectFields = computed(() => {
  const p = project.value
  const nameOf = (id?: string | null) => (id ? userNames.value[id] || '' : '')
  return [
    { label: '审核年度', value: p?.audit_year ? String(p.audit_year) : '' },
    { label: '签字合伙人', value: nameOf(p?.signing_partner_id) },
    { label: '项目经理', value: nameOf(p?.manager_id) },
    // 本平台项目没有现场负责人字段
    { label: '现场负责人', value: '' },
  ]
})

// ── 一级栏 ──
/** 菜单图标：citarRoutes 里按名字登记，这里映射到组件 */
const NAV_ICONS: Record<string, Component> = {
  Upload, Search, Grid, EditPen, Tickets, DocumentChecked, Connection, Notebook, Document,
}

/** 一级栏收起状态：记在本机（localStorage），换页 / 刷新后保持 */
const NAV_COLLAPSED_STORAGE_KEY = 'citar.nav.collapsed'

function readNavCollapsed(): boolean {
  try {
    return localStorage.getItem(NAV_COLLAPSED_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

const navCollapsed = ref(readNavCollapsed())

function toggleNav() {
  navCollapsed.value = !navCollapsed.value
  try {
    localStorage.setItem(NAV_COLLAPSED_STORAGE_KEY, navCollapsed.value ? '1' : '0')
  } catch {
    // 隐私模式等写不进本地存储：只影响记忆，不影响本次开合
  }
}

const subnavOpen = ref(false)
provide(CITAR_SUBNAV_OPEN_KEY, subnavOpen)

function goSegment(seg: string) {
  const year = route.query.year ? String(route.query.year) : undefined
  router.push({ path: `/projects/${projectId.value}/${seg}`, query: year ? { year } : {} })
}

function onNavClick(item: CitarNavItem) {
  if (item.segment === CITAR_WORKPAPER_SEGMENT) {
    // 税务底稿：已在本页时只开合目录，否则进入并展开
    if (segment.value === item.segment) {
      subnavOpen.value = !subnavOpen.value
      return
    }
    subnavOpen.value = true
  }
  goSegment(item.segment)
}

async function logout() {
  await authStore.logout()
  router.push('/login')
}
</script>

<style scoped src="./styles/project-shell.css"></style>
<style scoped src="./styles/create-topbar.css"></style>

<style scoped>
/* 页面滚动交给本容器：全局 body 不一定可滚 */
.citar-root {
  height: 100vh;
  overflow-y: auto;
}

/*
 * 税务底稿自带目录栏与内边距：内容区不留边距，改成 flex 容器让 TaxWorkpaperView 铺满
 * （目录栏紧贴一级栏，即 CITAR 的 shell-subnav 位置）。
 */
.citar-content--flush {
  display: flex;
  padding: 0;
}

.citar-create-body {
  padding: 16px 24px 24px;
}

/*
 * 项目内框架定高一屏，一级栏与内容区各自滚动。
 * 原为整页滚动：长页面（如税审底稿）把一级栏撑成整页高，往下滚左侧只剩一条空白，收起按钮也被挤到页面最底。
 */
.shell {
  height: 100vh;
  min-height: 0;
}

/* ── 一级栏分组（按分组图：组标题小字灰、选中项浅紫圆角底 + 紫色加粗） ── */
.citar-nav {
  flex-basis: 196px;
  padding: 8px 10px 0;
  overflow: hidden;
  transition: flex-basis 0.2s ease, padding 0.2s ease;
}

/* 菜单区占满栏高，放不下（窗口矮）时自己滚；开合按钮在其下方固定于栏底 */
.citar-nav__menu {
  flex: 1 1 auto;
  min-height: 0;
  padding-bottom: 8px;
  overflow-x: hidden;
  overflow-y: auto;
  scrollbar-width: thin;
}

/* 收起后组标题换成分隔线，保留分组层次 */
.citar-nav__divider {
  margin: 8px 6px;
  border-top: 1px solid #e8e8ec;
}

/* 开合按钮固定在栏底，与菜单项同款，字色更浅以示次要 */
.citar-nav__toggle {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 10px;
  width: 100%;
  margin-bottom: 4px;
  padding: 10px 10px;
  border: none;
  border-top: 1px solid #f0eef4;
  border-radius: 0;
  background: none;
  font: inherit;
  font-size: var(--citar-fs-13);
  color: var(--citar-c-8a8a96);
  text-align: left;
  cursor: pointer;
}

.citar-nav__toggle:hover {
  color: var(--citar-c-6e0ba6);
}

.citar-nav__group + .citar-nav__group {
  margin-top: 6px;
}

/*
 * 行距随窗口高度放宽，菜单尽量铺满栏高、不在底部留一大块白：
 * 菜单原样（组标题 14px / 菜单项 10px）连同顶部两行和栏底按钮约需 850px 高；
 * 窗口每多出 28px，组标题上边距与菜单项上下边距（共 28 处）各加 1px，上限 20px / 16px。
 * 矮于约 870px 时保持原行距，放不下由菜单区自己滚动。
 */
.citar-nav__title {
  padding: clamp(14px, 14px + (100vh - 870px) / 28, 20px) 10px 6px;
  font-size: var(--citar-fs-12);
  color: var(--citar-c-9a9aa4);
}

.citar-nav__item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: clamp(10px, 10px + (100vh - 870px) / 28, 16px) 10px;
  border: none;
  border-radius: 8px;
  background: none;
  font: inherit;
  font-size: var(--citar-fs-14);
  color: var(--citar-c-3f3f4a);
  text-align: left;
  cursor: pointer;
}

.citar-nav__item:hover {
  background: var(--citar-c-faf6ff);
  color: var(--citar-c-6e0ba6);
}

.citar-nav__item--active {
  background: var(--citar-c-f3edfa);
  color: var(--citar-c-4c1273);
  font-weight: 700;
}

.citar-nav__icon {
  flex: 0 0 auto;
  color: var(--citar-c-6b6b76);
}

.citar-nav__item--active .citar-nav__icon,
.citar-nav__item:hover .citar-nav__icon {
  color: var(--citar-c-6e0ba6);
}

/* 不折行：展开动画过程中宽度逐步变大，折行会让菜单上下跳动 */
.citar-nav__label,
.citar-nav__title {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.citar-nav__toggle:hover .citar-nav__icon {
  color: var(--citar-c-6e0ba6);
}

/* 菜单名后的「智能」角标：不参与压缩，菜单名过长时先省略菜单名 */
.citar-nav__badge {
  flex: 0 0 auto;
  padding: 0 6px;
  border-radius: 8px;
  background: var(--citar-c-f3e9fd);
  font-size: var(--citar-fs-11);
  font-weight: 400;
  line-height: 16px;
  color: var(--citar-c-6e0ba6);
}

.citar-nav__item--active .citar-nav__badge {
  background: var(--citar-c-ffffff);
}

/* 收起：只留图标列，宽度与平台三栏布局收起后一致（56px） */
.citar-nav--collapsed {
  flex-basis: 56px;
  padding: 8px 8px 0;
}

.citar-nav--collapsed .citar-nav__item,
.citar-nav--collapsed .citar-nav__toggle {
  justify-content: center;
  padding-right: 0;
  padding-left: 0;
}

/* 键盘聚焦可见（收起后只剩图标，更需要焦点框） */
.citar-nav__item:focus-visible,
.citar-nav__toggle:focus-visible {
  outline: 2px solid #8b3fd0;
  outline-offset: -2px;
}
</style>
