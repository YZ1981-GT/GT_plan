/**
 * CITAR 各页共用的项目上下文：项目 id、审计年度、跳转到别的菜单。
 *
 * 年度口径与全平台一致：路由 ?year= > 项目审计年度 > null（不按日历猜）。
 * 年度为 null 时各页显示「未设置审计年度」空态，不发请求。
 */
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getProjectAuditYear } from '@/services/auditPlatformApi'
import { resolveEffectiveAuditYear } from '@/utils/resolveAuditYear'
import { CITAR_PROJECT_KEY } from './citarRoutes'

export function useCitarProject() {
  const route = useRoute()
  const router = useRouter()
  const project = inject(CITAR_PROJECT_KEY, ref(null))

  const projectId = computed(() => String(route.params.projectId || ''))
  /** 报表表头「编制单位」 */
  const entityName = computed(() => project.value?.client_name || project.value?.name || '')
  const projectAuditYear = ref<number | null>(null)
  /** 项目年度读取中（读完之前不能判定「没设年度」） */
  const yearLoading = ref(false)

  const year = computed<number | null>(() =>
    resolveEffectiveAuditYear({ routeYear: route.query.year, storeAuditYear: projectAuditYear.value }),
  )

  watch(
    projectId,
    async (pid) => {
      projectAuditYear.value = null
      if (!pid || route.query.year) return
      yearLoading.value = true
      try {
        projectAuditYear.value = await getProjectAuditYear(pid)
      } catch {
        projectAuditYear.value = null
      } finally {
        yearLoading.value = false
      }
    },
    { immediate: true },
  )

  /** 跳到本项目另一个菜单，带上年度 */
  function goSegment(segment: string, query: Record<string, string> = {}) {
    const y = year.value
    router.push({
      path: `/projects/${projectId.value}/${segment}`,
      query: { ...(y ? { year: String(y) } : {}), ...query },
    })
  }

  return { projectId, year, yearLoading, entityName, goSegment }
}

/** 借正贷负金额 → 方向 + 绝对值（余额表的「方向 / 余额」两列） */
export function splitDirection(value: number | string | null | undefined): { dir: string; amount: number } {
  const n = Number(value ?? 0) || 0
  if (Math.abs(n) < 0.005) return { dir: '平', amount: 0 }
  return n > 0 ? { dir: '借', amount: n } : { dir: '贷', amount: -n }
}

/** 千分位两位小数；空 / 0 显示短横（CITAR 会计专用格式：零显示为「-」） */
export function fmtMoney(value: number | string | null | undefined, zeroAs = '-'): string {
  if (value === null || value === undefined || value === '') return ''
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value)
  if (Math.abs(n) < 0.005) return zeroAs
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
