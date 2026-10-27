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
 * projectStore.year        // 当前审计年度（换项目后取到项目信息前、项目没填审计年度时为 null）
 * projectStore.yearStatus  // 年度解析状态：idle / loading / ready / failed
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
import { getProject, type ProjectListItem } from '@/services/auditPlatformApi'
import { parseAuditYear, resolveAuditYearFromProject } from '@/utils/resolveAuditYear'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'

/** 只用于年度下拉选项（今年前后），不当审计年度用 */
const currentYear = new Date().getFullYear()

/**
 * 当前项目审计年度的解析状态（spec post-push-residual-defect-closure 6.5）：
 * - idle：非项目页；
 * - loading：换了项目、路由没带年度，还没取到项目信息（此时 year 为 null，不是「没填」）；
 * - ready：年度已定 —— 路由年度、项目审计年度，或项目没填（year 为 null）；
 * - failed：取项目信息失败、年度未知（与「没填」分开，页面不能据此让用户去填年度）。
 */
export type ProjectYearStatus = 'idle' | 'loading' | 'ready' | 'failed'

// ─── P0-2: ProjectContext 类型定义 ───────────────────────────────────────────
export interface ProjectContextData {
  projectId: string
  projectName: string
  /** 审计年度；年度未定 / 项目没填为 null */
  year: number | null
  applicableStandard: string
  auditScope: 'standalone' | 'consolidated'
  projectStatus: string
  roleInProject: string | null
}

export const useProjectStore = defineStore('project', () => {
  // ─── 核心状态 ───
  const projectId = ref('')
  // 不给初值：原先初值是去年、换到没填年度的项目也不清，页面就静默按去年 / 上一个项目的年度取数
  const year = ref<number | null>(null)
  const yearStatus = ref<ProjectYearStatus>('idle')
  // 每次换项目 / 重取递增：取项目信息返回时序号已变 ⇒ 期间又换了项目，丢弃这次的结果
  let contextSeq = 0
  const standard = ref<'soe' | 'listed'>('soe')
  const clientName = ref('')
  const auditYear = ref<number | null>(null)
  const projectStatus = ref<string>('')
  const auditScope = ref<'standalone' | 'consolidated'>('standalone')
  const roleInProject = ref<string | null>(null)

  // 项目选项列表（供单位切换下拉使用）
  const projectOptions = ref<Array<{ id: string; name: string }>>([])

  // 项目实际有数据的年份列表（动态从后端获取）
  const dataYears = ref<number[]>([])

  // 年度选项：合并默认范围 + 项目实际有数据的年份
  const yearOptions = computed(() => {
    const cur = currentYear
    const defaults = [cur - 2, cur - 1, cur, cur + 1]
    const all = new Set([...defaults, ...dataYears.value])
    if (auditYear.value) all.add(auditYear.value)
    return [...all].sort((a, b) => b - a)
  })

  /**
   * 取项目详情，失败再取一次（与原先「取年度一次 + 取项目信息一次」同样两次机会）。
   * 不参与 http 层 GET 去重：合并目录等同页组件会发同址 GET，去重会取消这一次，年度就被误判成取失败。
   */
  async function fetchProjectDetail(pid: string): Promise<ProjectListItem | undefined> {
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        return await getProject(pid, { dedupe: false })
      } catch { /* 再取一次 */ }
    }
    return undefined
  }

  function applyProjectInfo(proj: ProjectListItem) {
    const p = proj as any
    clientName.value = p?.client_name || p?.name || ''
    projectStatus.value = p?.status || ''
    auditScope.value = p?.audit_scope || (p?.project_type === 'consolidated' ? 'consolidated' : 'standalone')
  }

  /**
   * 取项目信息并定年度（本次序号 seq）。路由已给年度（status 已是 ready）时只补项目信息、不改年度；
   * 还在等年度（loading）时年度 = 项目审计年度，没填就是 null。期间换了项目 ⇒ 丢弃。
   */
  async function loadProjectInfo(pid: string, seq: number) {
    const proj = await fetchProjectDetail(pid)
    if (seq !== contextSeq || projectId.value !== pid) return
    if (!proj) {
      if (yearStatus.value !== 'ready') yearStatus.value = 'failed'
      return
    }
    applyProjectInfo(proj)
    const resolved = resolveAuditYearFromProject(proj)
    auditYear.value = resolved
    if (yearStatus.value !== 'ready') year.value = resolved
    yearStatus.value = 'ready'
  }

  // ─── 从路由自动同步（路由守卫 + DefaultLayout watch route 调用） ───
  async function syncFromRoute(route: RouteLocationNormalizedLoaded) {
    const pid = route.params.projectId as string | undefined
    if (!pid) {
      // 非项目页面，清空（年度也清：没有项目就没有审计年度，下一个项目页不会先拿到这个年度）
      contextSeq++
      projectId.value = ''
      clientName.value = ''
      auditYear.value = null
      year.value = null
      yearStatus.value = 'idle'
      return
    }

    const changed = pid !== projectId.value
    projectId.value = pid
    // 路由显式带的年度（用户在看哪一年）优先
    const routeYear = parseAuditYear(route.query.year)
    if (routeYear != null) {
      year.value = routeYear
      yearStatus.value = 'ready'
    }

    if (!changed) {
      // 同一项目：路由不带年度时保持当前年度；上次没取到项目信息（failed）⇒ 再导航时重取
      if (yearStatus.value === 'failed') {
        yearStatus.value = 'loading'
        await loadProjectInfo(pid, ++contextSeq)
      }
      return
    }

    // 换项目：路由没带年度 ⇒ 先清掉上一个项目的年度，取到本项目信息前是 loading（页面由 ProjectContextGate 挡住）
    const seq = ++contextSeq
    if (routeYear == null) {
      year.value = null
      yearStatus.value = 'loading'
    }
    resetProjectScopedState('route-change')
    loadDataYears(pid)
    // 只取一次项目详情：年度与项目信息都来自这一次（R16：原先先取一次只为年度、再整份取一次）
    await loadProjectInfo(pid, seq)
  }

  /** 取项目信息失败后重试（ProjectContextGate 的「重试」） */
  async function retryProjectContext() {
    const pid = projectId.value
    if (!pid || yearStatus.value !== 'failed') return
    yearStatus.value = 'loading'
    await loadProjectInfo(pid, ++contextSeq)
  }

  // ─── P0-2.3: loadProjectContext — 手动加载完整项目上下文 ───
  async function loadProjectContext(pid: string) {
    if (!pid) return
    const changed = pid !== projectId.value
    if (changed) {
      resetProjectScopedState('load-project-context')
    }
    projectId.value = pid
    loadDataYears(pid)
    const seq = ++contextSeq
    if (changed) {
      year.value = null
      yearStatus.value = 'loading'
    }
    const proj = await fetchProjectDetail(pid)
    if (seq === contextSeq && projectId.value === pid) {
      if (proj) {
        applyProjectInfo(proj)
        const resolved = resolveAuditYearFromProject(proj)
        auditYear.value = resolved
        // 重载回到项目审计年度（原行为）；换项目且没填年度 ⇒ null，不沿用上一个项目的
        if (resolved != null || changed) year.value = resolved
        yearStatus.value = 'ready'
      } else if (yearStatus.value === 'loading') {
        yearStatus.value = 'failed'
      }
    }
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
    if (projectId.value) yearStatus.value = 'ready' // 显式选了年度：年度已定，晚到的项目信息不再覆盖它
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
    if (projectId.value) yearStatus.value = 'ready'

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
        previousYear: prev ?? undefined, // 年度原先未定（null）时不带
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

  // ─── 加载项目实际有数据的年份列表（供年度选择器） ───
  async function loadDataYears(pid?: string) {
    const id = pid || projectId.value
    if (!id) { dataYears.value = []; return }
    try {
      const data = await api.get(`/api/projects/${id}/ledger/years`, {
        validateStatus: (s: number) => s === 200 || s === 404,
      })
      if (data && !data?.detail) {
        dataYears.value = data?.years ?? (Array.isArray(data) ? data : [])
      } else {
        dataYears.value = []
      }
    } catch { dataYears.value = [] }
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
    yearStatus,
    standard,
    clientName,
    auditYear,
    projectStatus,
    auditScope,
    roleInProject,
    projectOptions,
    yearOptions,
    dataYears,
    // P0-2: 项目上下文 facade
    currentProjectContext,
    // 方法
    syncFromRoute,
    retryProjectContext,
    loadProjectContext,
    resetProjectScopedState,
    changeYear,
    setCurrentYear,
    changeStandard,
    loadProjectOptions,
    loadDataYears,
  }
})
