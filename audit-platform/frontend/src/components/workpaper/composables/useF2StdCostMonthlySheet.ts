/**
 * useF2StdCostMonthlySheet — F2-40 标准成本差异测试
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import type { SamplingParams } from './useF2ValuationTestFormulas'
import {
  defaultThreeStdCostProjects,
  enrichStdCostProject,
  calcStdCostProjectTotals,
  calcStdCostBundleDiff,
  migrateToStdCostProjects,
  emptyStdCostProject,
  type StdCostProductProject,
  type StdCostMonthLine,
  type StdCostMonthKey,
} from './useF2StdCostMonthlyFormulas'

function isExceedDiff(diff: number, base: number): boolean {
  if (Math.abs(diff) < 0.005) return false
  if (!base) return Math.abs(diff) > 0.005
  return Math.abs(diff / base) * 100 > 5
}

export function useF2StdCostMonthlySheet(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const sheetCode = 'F2-40'
  const rowsKey = `${sheetCode}-rows`
  const paramsKey = `${sheetCode}-sampling`
  const conclusionKey = `${sheetCode}-conclusion`
  const objectiveKey = `${sheetCode}-objective`
  const samplingTextKey = `${sheetCode}-sampling-text`

  const thresholdRate = 5
  const projects = ref<StdCostProductProject[]>(defaultThreeStdCostProjects())
  const samplingParams = ref<SamplingParams>({
    population: '',
    sampleSize: 3,
    method: '选取代表性存货品种',
    confidence: '95%',
    tolerableError: '5%',
    conclusion: '',
  })
  const testConclusion = ref('')
  const testObjective = ref('')
  const samplingCriteria = ref('')

  function load(): void {
    const raw = readValRowJson(opts.allResponses.value.get(rowsKey))
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateToStdCostProjects(parsed)
        if (migrated?.length) projects.value = migrated
      } catch { /* ignore */ }
    }
    const sp = readValRowJson(opts.allResponses.value.get(paramsKey))
    if (sp) {
      try {
        samplingParams.value = { ...samplingParams.value, ...JSON.parse(sp) }
      } catch { /* ignore */ }
    }
    testConclusion.value = opts.allResponses.value.get(conclusionKey)?.remark || ''
    testObjective.value = opts.allResponses.value.get(objectiveKey)?.remark || ''
    samplingCriteria.value = opts.allResponses.value.get(samplingTextKey)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(rowsKey)?.remark, load, { immediate: true })

  const enrichedProjects = computed(() => projects.value.map((p) => enrichStdCostProject(p)))

  const bundleDiff = computed(() => calcStdCostBundleDiff(enrichedProjects.value))

  const exceedCount = computed(() => {
    let count = 0
    for (const p of enrichedProjects.value) {
      for (const m of p.months) {
        if (isExceedDiff(m.diffStdCost, m.expEndStdCost)) count += 1
      }
    }
    return count
  })

  function projectTotals(p: StdCostProductProject) {
    return calcStdCostProjectTotals(enrichStdCostProject(p).months)
  }

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(rowsKey),
      opts.allResponses.value.get(paramsKey),
      opts.allResponses.value.get(conclusionKey),
      opts.allResponses.value.get(objectiveKey),
      opts.allResponses.value.get(samplingTextKey),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items } }))
  }

  function persist(): void {
    if (readonly.value) return
    opts.allResponses.value.set(rowsKey, {
      item_id: rowsKey,
      conclusion: null,
      remark: JSON.stringify(projects.value),
    })
    opts.allResponses.value.set(paramsKey, {
      item_id: paramsKey,
      conclusion: null,
      remark: JSON.stringify(samplingParams.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
    try {
      window.dispatchEvent(new CustomEvent('valuation:tested', {
        detail: { wpCode: 'F2', sheetCode, exceedCount: exceedCount.value },
      }))
    } catch { /* silent */ }
  }

  function updateProject(id: string, patch: Partial<StdCostProductProject>): void {
    if (readonly.value) return
    projects.value = projects.value.map((p) => (p.id === id ? { ...p, ...patch } : p))
    persist()
  }

  function updateMonth(
    projectId: string,
    monthKey: StdCostMonthKey,
    patch: Partial<StdCostMonthLine>,
  ): void {
    if (readonly.value) return
    projects.value = projects.value.map((p) => {
      if (p.id !== projectId) return p
      return {
        ...p,
        months: p.months.map((m) => {
          if (m.key !== monthKey) return m
          const next = { ...m, ...patch }
          if (('prodQty' in patch || 'stdUnitPrice' in patch) && !('prodStdCost' in patch)) {
            if (next.prodQty && next.stdUnitPrice) {
              next.prodStdCost = next.prodQty * next.stdUnitPrice
            }
          }
          if (('saleQty' in patch || 'stdUnitPrice' in patch) && !('saleStdCost' in patch)) {
            if (next.saleQty && next.stdUnitPrice) {
              next.saleStdCost = next.saleQty * next.stdUnitPrice
            }
          }
          return next
        }),
      }
    })
    persist()
  }

  function addProject(): void {
    if (readonly.value) return
    const seq = projects.value.length + 1
    projects.value = [...projects.value, emptyStdCostProject(seq)]
    samplingParams.value = { ...samplingParams.value, sampleSize: projects.value.length }
    persist()
  }

  function removeProject(id: string): void {
    if (readonly.value || projects.value.length <= 1) return
    projects.value = projects.value
      .filter((p) => p.id !== id)
      .map((p, i) => ({ ...p, seq: i + 1 }))
    samplingParams.value = { ...samplingParams.value, sampleSize: projects.value.length }
    persist()
  }

  function persistText(key: string, val: string, target: Ref<string>): void {
    if (readonly.value) return
    target.value = val
    opts.allResponses.value.set(key, { item_id: key, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  watch(testConclusion, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(conclusionKey, { item_id: conclusionKey, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  })

  watch(samplingParams, () => {
    if (readonly.value) return
    opts.allResponses.value.set(paramsKey, {
      item_id: paramsKey,
      conclusion: null,
      remark: JSON.stringify(samplingParams.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }, { deep: true })

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      flushSave()
    }
  })

  return {
    sheetCode,
    thresholdRate,
    projects,
    enrichedProjects,
    samplingParams,
    testConclusion,
    testObjective,
    samplingCriteria,
    exceedCount,
    bundleDiff,
    projectTotals,
    updateProject,
    updateMonth,
    addProject,
    removeProject,
    setObjective: (v: string) => persistText(objectiveKey, v, testObjective),
    setSamplingCriteria: (v: string) => persistText(samplingTextKey, v, samplingCriteria),
  }
}

export default useF2StdCostMonthlySheet
