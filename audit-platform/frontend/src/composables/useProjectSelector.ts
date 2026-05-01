/**
 * 项目/年度选择器 composable
 *
 * 6个核心数据页面（试算表/调整分录/未更正错报/重要性/现金流/报表）
 * 共享的单位切换+年度切换逻辑，消除重复代码。
 *
 * 用法：
 * ```ts
 * const { selectedProjectId, projectOptions, selectedYear, yearOptions,
 *         onProjectChange, onYearChange, loadProjectOptions } = useProjectSelector('trial-balance')
 * ```
 */
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import http from '@/utils/http'

export interface ProjectOption {
  id: string
  name: string
}

export function useProjectSelector(pagePath: string) {
  const route = useRoute()
  const router = useRouter()

  const projectId = computed(() => route.params.projectId as string)
  const routeYear = computed(() => {
    const v = Number(route.query.year)
    return Number.isFinite(v) && v > 2000 ? v : null
  })

  const selectedProjectId = ref(projectId.value)
  const projectOptions = ref<ProjectOption[]>([])
  const selectedYear = ref(routeYear.value ?? new Date().getFullYear() - 1)
  const yearOptions = computed(() => {
    const cur = new Date().getFullYear()
    return [cur - 2, cur - 1, cur, cur + 1]
  })

  async function loadProjectOptions() {
    try {
      const { data } = await http.get('/api/projects', {
        params: { page_size: 200 },
        validateStatus: (s: number) => s < 600,
      })
      const items = data?.data?.items ?? data?.items ?? data?.data ?? data ?? []
      projectOptions.value = (Array.isArray(items) ? items : []).map((p: any) => ({
        id: p.id,
        name: p.client_name || p.name || p.id,
      }))
    } catch { /* ignore */ }
  }

  function onProjectChange(pid: string) {
    router.push({
      path: `/projects/${pid}/${pagePath}`,
      query: { year: String(selectedYear.value) },
    })
  }

  function onYearChange(y: number) {
    selectedYear.value = y
    router.push({
      path: `/projects/${projectId.value}/${pagePath}`,
      query: { year: String(y) },
    })
  }

  /** 同步选中值（在 watch/onMounted 中调用） */
  function syncFromRoute() {
    selectedProjectId.value = projectId.value
    if (routeYear.value) {
      selectedYear.value = routeYear.value
    }
  }

  return {
    projectId,
    routeYear,
    selectedProjectId,
    projectOptions,
    selectedYear,
    yearOptions,
    loadProjectOptions,
    onProjectChange,
    onYearChange,
    syncFromRoute,
  }
}
