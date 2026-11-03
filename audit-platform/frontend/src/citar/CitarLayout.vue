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
        <nav class="shell-sidebar citar-nav">
          <section v-for="group in CITAR_NAV_GROUPS" :key="group.title" class="citar-nav__group">
            <div class="citar-nav__title">{{ group.title }}</div>
            <button
              v-for="item in group.items"
              :key="item.key"
              type="button"
              class="citar-nav__item"
              :class="{ 'citar-nav__item--active': segment === item.segment }"
              @click="onNavClick(item)"
            >
              <el-icon class="citar-nav__icon" :size="17"><component :is="NAV_ICONS[item.icon]" /></el-icon>
              <span class="citar-nav__label">{{ item.label }}</span>
              <span v-if="item.segment === CITAR_WORKPAPER_SEGMENT" class="shell-nav__caret">{{ subnavOpen && segment === item.segment ? '▾' : '▸' }}</span>
            </button>
          </section>
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
import { getProject } from '@/services/auditPlatformApi'
import { api } from '@/services/apiProxy'
import type { Component } from 'vue'
import {
  Connection, Document, DocumentChecked, EditPen, Grid, Notebook, Search, Tickets, Upload,
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

/* ── 一级栏分组（按分组图：组标题小字灰、选中项浅紫圆角底 + 紫色加粗） ── */
.citar-nav {
  flex-basis: 196px;
  padding: 8px 10px 16px;
}

.citar-nav__group + .citar-nav__group {
  margin-top: 6px;
}

.citar-nav__title {
  padding: 14px 10px 6px;
  font-size: var(--citar-fs-12);
  color: var(--citar-c-9a9aa4);
}

.citar-nav__item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 10px;
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

.citar-nav__label {
  min-width: 0;
}
</style>
