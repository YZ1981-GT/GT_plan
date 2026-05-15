/**
 * useFormulaStatus — 公式状态管理 composable
 *
 * 提供底稿公式状态的加载、筛选、刷新能力。
 * 配合 FormulaStatusPanel.vue / FormulaTooltip.vue / FormulaSourceDrawer.vue 使用。
 */
import { ref, computed } from 'vue'
import { api } from '@/services/apiProxy'

export interface FormulaItem {
  cell_ref: string
  sheet: string
  formula_type: string
  raw_args: string
  status: 'filled' | 'stale' | 'error' | 'waiting'
  value?: number | string | null
  error?: string
  source_ref?: string
  filled_at?: string
}

export interface FormulaStatusCounts {
  filled: number
  stale: number
  error: number
  waiting: number
  total: number
}

export function useFormulaStatus(projectId: string, wpId: string) {
  const formulas = ref<FormulaItem[]>([])
  const loading = ref(false)
  const filterStatus = ref<string>('all')

  const filteredFormulas = computed(() => {
    if (filterStatus.value === 'all') return formulas.value
    return formulas.value.filter(f => f.status === filterStatus.value)
  })

  const counts = computed<FormulaStatusCounts>(() => {
    const c: FormulaStatusCounts = { filled: 0, stale: 0, error: 0, waiting: 0, total: 0 }
    for (const f of formulas.value) {
      c[f.status] = (c[f.status] || 0) + 1
      c.total++
    }
    return c
  })

  const hasStale = computed(() => counts.value.stale > 0)
  const hasError = computed(() => counts.value.error > 0)

  async function loadFormulas() {
    loading.value = true
    try {
      const data = await api.get(
        `/api/projects/${projectId}/workpapers/${wpId}/formulas`
      )
      formulas.value = data?.formulas || []
    } catch {
      formulas.value = []
    } finally {
      loading.value = false
    }
  }

  async function refreshFormulas() {
    loading.value = true
    try {
      await api.post(
        `/api/projects/${projectId}/workpapers/${wpId}/prefill`
      )
      await loadFormulas()
    } catch {
      // silent
    } finally {
      loading.value = false
    }
  }

  function getFormulaAt(sheet: string, cellRef: string): FormulaItem | undefined {
    return formulas.value.find(
      f => f.sheet === sheet && f.cell_ref === cellRef
    )
  }

  function setFilter(status: string) {
    filterStatus.value = filterStatus.value === status ? 'all' : status
  }

  return {
    formulas,
    filteredFormulas,
    counts,
    loading,
    filterStatus,
    hasStale,
    hasError,
    loadFormulas,
    refreshFormulas,
    getFormulaAt,
    setFilter,
  }
}
