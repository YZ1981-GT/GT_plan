/**
 * 项目上下文 Store (useProjectStore)
 *
 * 统一管理当前项目的 projectId / year / standard / clientName，
 * 由 DefaultLayout watch route 自动同步，所有子页面直接读取，
 * 不再各自从 route.params / route.query 解析。
 *
 * 用法：
 * ```ts
 * const projectStore = useProjectStore()
 * // 读取
 * projectStore.projectId   // 当前项目 ID
 * projectStore.year        // 当前审计年度
 * projectStore.clientName  // 客户名称
 * // 切换
 * projectStore.changeYear(2024)
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

export const useProjectStore = defineStore('project', () => {
  // ─── 核心状态 ───
  const projectId = ref('')
  const year = ref(currentYear - 1)
  const standard = ref<'soe' | 'listed'>('soe')
  const clientName = ref('')
  const auditYear = ref<number | null>(null)
  const projectStatus = ref<string>('')

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

    // 项目切换时加载项目信息
    if (changed) {
      try {
        const proj = await getProject(pid)
        clientName.value = (proj as any)?.client_name || (proj as any)?.name || ''
        projectStatus.value = (proj as any)?.status || ''
        if ((proj as any)?.audit_year) {
          const ay = Number((proj as any).audit_year)
          if (Number.isFinite(ay) && ay > 2000) auditYear.value = ay
        }
      } catch { /* ignore */ }
    }
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

  // ─── MVP-1: currentProjectContext facade ───
  // 统一暴露项目上下文，页面不再自行从 route/query/localStorage 多处解析
  const currentProjectContext = computed(() => ({
    projectId: projectId.value,
    projectName: clientName.value,
    year: year.value,
    applicableStandard: standard.value as string,
    auditScope: 'standalone' as 'standalone' | 'consolidated', // placeholder: 后续从项目数据获取
    projectStatus: projectStatus.value || 'draft',
    roleInProject: null as string | null, // placeholder: 后续从 project assignment 获取
  }))

  // ─── MVP-2: setCurrentYear() 触发核心缓存清理 ───
  function setCurrentYear(y: number, options?: { reload?: boolean }) {
    const prev = year.value
    year.value = y

    if (prev !== y && projectId.value) {
      // 清理项目域缓存（MVP: 重置本地响应式状态）
      auditYear.value = y
      projectStatus.value = '' // 触发重新加载

      // 发布年度切换事件，通知订阅视图
      eventBus.emit('year:changed', {
        projectId: projectId.value,
        year: y,
      })
    }
  }

  return {
    // 状态
    projectId,
    year,
    standard,
    clientName,
    auditYear,
    projectStatus,
    projectOptions,
    yearOptions,
    // MVP-1: 项目上下文 facade
    currentProjectContext,
    // 方法
    syncFromRoute,
    changeYear,
    setCurrentYear,
    changeStandard,
    loadProjectOptions,
  }
})
