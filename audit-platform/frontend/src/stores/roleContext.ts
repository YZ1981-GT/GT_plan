/**
 * 角色上下文 Store — 管理用户多角色×多项目身份
 *
 * 登录后自动加载，缓存到 sessionStorage，切换项目时刷新项目角色
 */
import { defineStore } from 'pinia'
import http from '@/utils/http'

export interface ProjectRole {
  project_id: string
  project_name: string
  client_name: string
  role: string
  permission_level: string
}

export interface NavItem {
  key: string
  label: string
  icon: string
  path: string
  badge?: number
}

export interface QuickAction {
  label: string
  path: string
  icon: string
  badge?: number
}

export interface RoleContextState {
  systemRole: string
  effectiveRole: string
  projects: ProjectRole[]
  navItems: NavItem[]
  homepageContent: {
    role: string
    greeting_type: string
    quick_actions: QuickAction[]
    stats: Record<string, number>
  } | null
  currentProjectRole: {
    source: string
    role: string
    permission_level: string
    scope_cycles: any
  } | null
  loaded: boolean
}

export const useRoleContextStore = defineStore('roleContext', {
  state: (): RoleContextState => ({
    systemRole: '',
    effectiveRole: '',
    projects: [],
    navItems: [],
    homepageContent: null,
    currentProjectRole: null,
    loaded: false,
  }),

  getters: {
    isPartner: (state) => ['admin', 'partner'].includes(state.effectiveRole),
    isManager: (state) => ['admin', 'partner', 'manager'].includes(state.effectiveRole),
    isQC: (state) => ['admin', 'qc'].includes(state.effectiveRole),
    isAuditor: (state) => state.effectiveRole === 'auditor',
    canManageUsers: (state) => state.effectiveRole === 'admin',

    /** 当前项目中是否有编辑权限 */
    canEditInProject: (state) => {
      if (!state.currentProjectRole) return false
      return ['edit'].includes(state.currentProjectRole.permission_level)
    },
    /** 当前项目中是否有复核权限 */
    canReviewInProject: (state) => {
      if (!state.currentProjectRole) return false
      return ['edit', 'review'].includes(state.currentProjectRole.permission_level)
    },
  },

  actions: {
    async loadGlobalContext() {
      try {
        const { data } = await http.get('/api/role-context/me')
        this.systemRole = data.system_role || ''
        this.effectiveRole = data.effective_role || ''
        this.projects = data.projects || []
        this.loaded = true
      } catch {
        // 降级：从 auth store 取系统角色
        try {
          const authStore = (await import('./auth')).useAuthStore()
          this.systemRole = authStore.user?.role || 'readonly'
          this.effectiveRole = this.systemRole
        } catch {}
        this.loaded = true
      }
    },

    async loadNavItems() {
      try {
        const { data } = await http.get('/api/role-context/me/nav')
        this.navItems = Array.isArray(data) ? data : []
      } catch {
        // 降级：返回基础导航
        this.navItems = [
          { key: 'dashboard', label: '仪表盘', icon: 'Odometer', path: '/' },
          { key: 'projects', label: '项目情况', icon: 'FolderOpened', path: '/projects' },
        ]
      }
    },

    async loadHomepageContent() {
      try {
        const { data } = await http.get('/api/role-context/me/homepage')
        this.homepageContent = data
      } catch {
        this.homepageContent = null
      }
    },

    async loadProjectRole(projectId: string) {
      try {
        const { data } = await http.get(`/api/role-context/project/${projectId}`)
        this.currentProjectRole = data
      } catch {
        this.currentProjectRole = null
      }
    },

    /**
     * 登录后加载首屏真正要用的角色上下文（只有 `/me`）。
     *
     * 🔴 原来并发拉 3 个端点（`/me`、`/me/nav`、`/me/homepage`），而现算全仓没有任何组件读
     * `navItems` / `homepageContent`：所有 `navItems` 命中都是各底稿 / 布局组件自己的局部常量，
     * `homepageContent` 只在本 store 内部出现（state / action / reset）。两条请求的结果没人消费，
     * 却挡在首屏关键路径上（`DefaultLayout` 是唯一调用方且 `await` 它）。
     * 两个 action 保留为**按需调用**：将来真有消费者时自己取，不回到首屏并发。
     * 判据见 `stores/__tests__/roleContextInitialize.spec.ts`
     * （spec runtime-performance-and-reload-hardening-followup R6.2）。
     */
    async initialize() {
      await this.loadGlobalContext()
    },

    reset() {
      this.systemRole = ''
      this.effectiveRole = ''
      this.projects = []
      this.navItems = []
      this.homepageContent = null
      this.currentProjectRole = null
      this.loaded = false
    },
  },
})
