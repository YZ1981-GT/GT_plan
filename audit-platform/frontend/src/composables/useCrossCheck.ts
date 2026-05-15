/**
 * useCrossCheck — 跨科目校验 composable
 *
 * Sprint 4 Task 4.7: 封装校验执行 / 结果获取 / 规则管理
 */
import { ref, computed } from 'vue'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'

export interface CrossCheckResult {
  id: string
  project_id: string
  year: number
  rule_id: string
  description?: string
  left_amount: number | null
  right_amount: number | null
  difference: number | null
  status: 'pass' | 'fail' | 'skip' | 'error'
  details: Record<string, unknown> | null
  checked_at: string | null
}

export interface CrossCheckRule {
  rule_id: string
  description: string
  formula: string
  tolerance: number
  severity: 'blocking' | 'warning' | 'info'
  applicable_stages: string[]
  applicable_cycles: string[]
  enabled: boolean
}

export interface CheckSummary {
  total: number
  passed: number
  failed: number
  skipped: number
  errors: number
}

export function useCrossCheck(projectId: string) {
  const results = ref<CrossCheckResult[]>([])
  const rules = ref<CrossCheckRule[]>([])
  const loading = ref(false)
  const executing = ref(false)
  const summary = ref<CheckSummary>({ total: 0, passed: 0, failed: 0, skipped: 0, errors: 0 })

  const passRate = computed(() => {
    if (summary.value.total === 0) return 0
    const checkable = summary.value.total - summary.value.skipped - summary.value.errors
    if (checkable === 0) return 100
    return Math.round((summary.value.passed / checkable) * 100)
  })

  const hasBlockingFailures = computed(() => {
    return results.value.some(r => {
      if (r.status !== 'fail') return false
      const rule = rules.value.find(rl => rl.rule_id === r.rule_id)
      return rule?.severity === 'blocking'
    })
  })

  const failedResults = computed(() => results.value.filter(r => r.status === 'fail'))
  const passedResults = computed(() => results.value.filter(r => r.status === 'pass'))

  async function execute(year: number, ruleIds?: string[]) {
    executing.value = true
    try {
      const data = await api.post(
        `/api/projects/${projectId}/cross-check/execute`,
        { year, rule_ids: ruleIds || null, trigger: 'manual' }
      )
      results.value = data.results || []
      summary.value = data.summary || { total: 0, passed: 0, failed: 0, skipped: 0, errors: 0 }
      return data
    } catch (e: unknown) {
      handleApiError(e, '跨科目校验')
      throw e
    } finally {
      executing.value = false
    }
  }

  async function fetchResults(year?: number) {
    loading.value = true
    try {
      const params = year ? `?year=${year}` : ''
      const data = await api.get(`/api/projects/${projectId}/cross-check/results${params}`)
      results.value = data.items || []
    } catch (e: unknown) {
      handleApiError(e, '跨科目校验')
    } finally {
      loading.value = false
    }
  }

  async function fetchRules() {
    try {
      const data = await api.get(`/api/projects/${projectId}/cross-check/rules`)
      rules.value = data.items || []
    } catch (e: unknown) {
      handleApiError(e, '跨科目校验')
    }
  }

  async function addCustomRule(rule: {
    description: string
    formula: string
    tolerance?: number
    severity?: string
  }) {
    try {
      const data = await api.post(
        `/api/projects/${projectId}/cross-check/rules/custom`,
        rule
      )
      // 刷新规则列表
      await fetchRules()
      return data
    } catch (e: unknown) {
      handleApiError(e, '跨科目校验')
      throw e
    }
  }

  return {
    results,
    rules,
    loading,
    executing,
    summary,
    passRate,
    hasBlockingFailures,
    failedResults,
    passedResults,
    execute,
    fetchResults,
    fetchRules,
    addCustomRule,
  }
}
