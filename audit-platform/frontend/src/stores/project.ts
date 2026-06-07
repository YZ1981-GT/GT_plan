/**
 * 项目上下文 Store (useProjectStore)
 *
 * 统一管理当前项目的 projectId / year / standard / clientName，
 * 由 DefaultLayout watch route 自动同步，所有子页面直接读取，
 * 不再各自从 route.params / route.query 解析。
 *
 * [platform-context-permission-foundation P0-2/P0-3]
 * 新增 ProjectContext facade + 年度切换协议：
 * - currentProjectContext: 统一暴露所有项目上下文字段
 * - loadProjectContext(projectId): 加载完整项目上下文
 * - resetProjectScopedState(reason): 项目切换时清空旧状态
 * - setCurrentYear(year, opts): 年度切换 + 缓存清理 + SSE 重建
 *
 * 用法：
 * ```ts
 * const projectStore = useProjectStore()
 * // 读取
 * projectStore.projectId   // 当前项目 ID
 * projectStore.year        // 当前审计年度
 * projectStore.clientName  // 客户名称
 * projectStore.currentProjectContext // 完整上下文 facade
 * // 切换
 * projectStore.changeYear(2024)
 * projectStore.setCurrentYear(2025, { reload: true })
 * projectStore.changeStandard('listed')
 * ```
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { RouteLocationNormalizedLoaded } from 'vue-router'
import { getProject, getProjectAuditYear } from '@/services/auditPlatformApi'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'

const currentYear = new Date().getFullYear()

// ─── P0-2: ProjectContext 类型定义 ───────────────────────────────────────────
export interface ProjectContextData {
  projectId: string
  projectName: string
  year: number
  applicableStandard: string
  auditScope: 'standalone' | 'consolidated'
  projectStatus: string
  roleInProject: string | null
}

export const useProjectStore = defineStore('project', () => {
  // ─── 核心状态 ───
  const projectId = ref('')
  const year = ref(currentYear - 1)
  const standard = ref<'soe' | 'listed'>('soe')
  const clientName = ref('')
  const auditYear = ref<number | null>(null)
  const projectStatus = ref<string>('')
  const auditScope = ref<'standalone' | 'consolidated'>('standalone')
  const roleInProject = ref<string | null>(null)

  // 项目选项列表（供单位切换下拉使用）
  const projectOptions = ref<Array<{ id: string; name: string }>>([])

  // 年度选项
  const yearOptions = computed(() => {
    const cur = currentYear
    return [cur - 2, cur - 1, cur, cur + 1]
  })

  // ─── 从路由自动同步（DefaultLayout watch route 调用） ───
  async function syncFromRoute(route: RouteLocationNormalizedLoaded) {
    const pid = route.params.projectId as string | undefined
    if (!pid) {
      // 非项目页面，清空
      projectId.value = ''
      clientName.value = ''
      auditYear.value = null
      return
    }

    const changed = pid !== projectId.value
    projectId.value = pid

    // 从 query 解析年度
    const qy = Number(route.query.year)
    if (Number.isFinite(qy) && qy > 2000) {
      year.value = qy
    } else if (changed) {
      // 路由没带 year，尝试从后端获取项目审计年度
      try {
        const ay = await getProjectAuditYear(pid)
        if (ay) {
          auditYear.value = ay
          year.value = ay
        }
      } catch { /* ignore */ }
    }

    // 项目切换时加载项目信息 + 清理旧项目状态
    if (changed) {
      resetProjectScopedState('route-change')
      try {
        const proj = await getProject(pid)
        clientName.value = (proj as any)?.client_name || (proj as any)?.name || ''
        projectStatus.value = (proj as any)?.status || ''
        auditScope.value = (proj as any)?.audit_scope || (proj as any)?.project_type === 'consolidated' ? 'consolidated' : 'standalone'
        if ((proj as any)?.audit_year) {
          const ay = Number((proj as any).audit_year)
          if (Number.isFinite(ay) && ay > 2000) auditYear.value = ay
        }
      } catch { /* ignore */ }
    }
  }

  // ─── P0-2.3: loadProjectContext — 手动加载完整项目上下文 ───
  async function loadProjectContext(pid: string) {
    if (!pid) return
    const changed = pid !== projectId.value
    if (changed) {
      resetProjectScopedState('load-project-context')
    }
    projectId.value = pid
    try {
      const proj = await getProject(pid)
      clientName.value = (proj as any)?.client_name || (proj as any)?.name || ''
      projectStatus.value = (proj as any)?.status || ''
      auditScope.value = (proj as any)?.audit_scope || (proj as any)?.project_type === 'consolidated' ? 'consolidated' : 'standalone'
      if ((proj as any)?.audit_year) {
        const ay = Number((proj as any).audit_year)
        if (Number.isFinite(ay) && ay > 2000) {
          auditYear.value = ay
          year.value = ay
        }
      }
    } catch { /* ignore */ }
    // Load project role
    try {
      const roleData = await api.get(`/api/projects/${pid}/my-role`, {
        validateStatus: (s: number) => s < 600,
      })
      roleInProject.value = (roleData as any)?.project_role || null
    } catch { /* ignore */ }
  }

  // ─── P0-2.4: resetProjectScopedState — 项目切换清理 ───
  function resetProjectScopedState(reason: string) {
    // 清空项目域状态
    clientName.value = ''
    projectStatus.value = ''
    auditScope.value = 'standalone'
    roleInProject.value = null
    auditYear.value = null

    // 发布项目切换事件，通知所有订阅方清理
    eventBus.emit('project:reset', { reason, projectId: projectId.value })

    // 停止旧 SSE 订阅（P0-3.3）
    eventBus.emit('sse:disconnect', { reason })
  }

  // ─── 切换年度（R8-S1-04：切换时 emit eventBus 通知订阅视图） ───
  function changeYear(y: number) {
    const prev = year.value
    year.value = y
    if (prev !== y && projectId.value) {
      eventBus.emit('year:changed', {
        projectId: projectId.value,
        year: y,
      })
    }
  }

  // ─── P0-3.1: setCurrentYear() — 年度切换协议（含缓存清理 + SSE 重建） ───
  function setCurrentYear(y: number, options?: { reload?: boolean }) {
    const prev = year.value
    year.value = y

    if (prev !== y && projectId.value) {
      // P0-3.2: 清理底稿、试算表、报表、附注、合并相关缓存
      auditYear.value = y
      projectStatus.value = '' // 触发重新加载

      // P0-3.3: 停止旧年度 SSE / stale 订阅并重建
      eventBus.emit('sse:disconnect', { reason: 'year-change' })

      // 发布年度切换事件，通知订阅视图
      eventBus.emit('year:changed', {
        projectId: projectId.value,
        year: y,
        previousYear: prev,
      })

      // 触发 SSE 重连
      eventBus.emit('sse:reconnect', {
        projectId: projectId.value,
        year: y,
      })
    }
  }

  // ─── 切换准则 ───
  function changeStandard(s: 'soe' | 'listed') {
    standard.value = s
  }

  // ─── 加载项目列表（供单位切换下拉） ───
  async function loadProjectOptions() {
    if (projectOptions.value.length > 0) return // 已加载
    try {
      const data = await api.get('/api/projects', {
        params: { page_size: 200 },
        validateStatus: (s: number) => s < 600,
      })
      const items = data?.items ?? data ?? []
      projectOptions.value = (Array.isArray(items) ? items : []).map((p: any) => ({
        id: p.id,
        name: p.client_name || p.name || p.id,
      }))
    } catch { /* ignore */ }
  }

  // ─── P0-2.1/P0-2.2: currentProjectContext facade ───
  // 统一暴露项目上下文，页面不再自行从 route/query/localStorage 多处解析
  const currentProjectContext = computed<ProjectContextData>(() => ({
    projectId: projectId.value,
    projectName: clientName.value,
    year: year.value,
    applicableStandard: standard.value as string,
    auditScope: auditScope.value,
    projectStatus: projectStatus.value || 'draft',
    roleInProject: roleInProject.value,
  }))

  return {
    // 状态
    projectId,
    year,
    standard,
    clientName,
    auditYear,
    projectStatus,
    auditScope,
    roleInProject,
    projectOptions,
    yearOptions,
    // P0-2: 项目上下文 facade
    currentProjectContext,
    // 方法
    syncFromRoute,
    loadProjectContext,
    resetProjectScopedState,
    changeYear,
    setCurrentYear,
    changeStandard,
    loadProjectOptions,
  }
})
