/**
 * useF2ValuationMonthlySheet — F2-38/39/40 多产品×月度计价测试基座
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import type { SamplingParams } from './useF2ValuationTestFormulas'
import {
  defaultFourProjects,
  enrichProductProject,
  calcProductTotals,
  calcBundleVariance,
  migrateLegacyValuationRows,
  emptyProductProject,
  type ValuationProductProject,
  type ValuationMonthlyMethod,
  type ValuationMonthLine,
  type ValuationMonthKey,
} from './useF2ValuationMonthlyFormulas'

export interface ValuationMonthlySheetDef {
  sheetCode: 'F2-38'
  method: ValuationMonthlyMethod
  thresholdRate: number
}

function absRate(variance: number, book: number): number {
  if (!book) return variance ? 100 : 0
  return Math.abs(variance / book) * 100
}

export function useF2ValuationMonthlySheet(
  def: ValuationMonthlySheetDef,
  opts: {
    allResponses: Ref<Map<string, ChecklistResponse>>
    isReadonly?: Ref<boolean>
  },
) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const rowsKey = `${def.sheetCode}-rows`
  const paramsKey = `${def.sheetCode}-sampling`
  const conclusionKey = `${def.sheetCode}-conclusion`
  const objectiveKey = `${def.sheetCode}-objective`
  const samplingTextKey = `${def.sheetCode}-sampling-text`

  const projects = ref<ValuationProductProject[]>(defaultFourProjects())
  const samplingParams = ref<SamplingParams>({
    population: '',
    sampleSize: 4,
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
        const migrated = migrateLegacyValuationRows(parsed)
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

  const enrichedProjects = computed(() =>
    projects.value.map((p) => enrichProductProject(p, def.method)),
  )

  const bundleVariance = computed(() => calcBundleVariance(enrichedProjects.value))

  const exceedCount = computed(() => {
    let n = 0
    for (const p of enrichedProjects.value) {
      for (const m of p.months) {
        if (m.key === 'opening') continue
        if (absRate(m.variance, m.saleAmt) > def.thresholdRate && Math.abs(m.variance) > 0.005) n += 1
      }
    }
    return n
  })

  function projectTotals(p: ValuationProductProject) {
    return calcProductTotals(enrichProductProject(p, def.method).months)
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
        detail: { wpCode: 'F2', sheetCode: def.sheetCode, exceedCount: exceedCount.value },
      }))
    } catch { /* silent */ }
  }

  function updateProject(id: string, patch: Partial<ValuationProductProject>): void {
    if (readonly.value) return
    projects.value = projects.value.map((p) => (p.id === id ? { ...p, ...patch } : p))
    persist()
  }

  function updateMonth(
    projectId: string,
    monthKey: ValuationMonthKey,
    patch: Partial<ValuationMonthLine>,
  ): void {
    if (readonly.value) return
    projects.value = projects.value.map((p) => {
      if (p.id !== projectId) return p
      return {
        ...p,
        months: p.months.map((m) => {
          if (m.key !== monthKey) return m
          const next = { ...m, ...patch }
          // 数量/单价变动且未显式改金额时，回填金额（贴近 Excel）
          if (('prodQty' in patch || 'prodPrice' in patch) && !('prodAmt' in patch)) {
            if (next.prodQty && next.prodPrice) next.prodAmt = next.prodQty * next.prodPrice
          }
          if (('saleQty' in patch || 'salePrice' in patch) && !('saleAmt' in patch)) {
            if (next.saleQty && next.salePrice) next.saleAmt = next.saleQty * next.salePrice
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
    projects.value = [...projects.value, emptyProductProject(seq)]
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
    sheetCode: def.sheetCode,
    method: def.method,
    thresholdRate: def.thresholdRate,
    projects,
    enrichedProjects,
    samplingParams,
    testConclusion,
    testObjective,
    samplingCriteria,
    exceedCount,
    bundleVariance,
    projectTotals,
    updateProject,
    updateMonth,
    addProject,
    removeProject,
    setObjective: (v: string) => persistText(objectiveKey, v, testObjective),
    setSamplingCriteria: (v: string) => persistText(samplingTextKey, v, samplingCriteria),
  }
}

export function useF2WeightedAvgMonthly(opts: Parameters<typeof useF2ValuationMonthlySheet>[1]) {
  return useF2ValuationMonthlySheet(
    { sheetCode: 'F2-38', method: 'weighted-avg', thresholdRate: 1 },
    opts,
  )
}

export function useF2FifoMonthly(opts: Parameters<typeof useF2ValuationMonthlySheet>[1]) {
  return useF2ValuationMonthlySheet(
    { sheetCode: 'F2-39', method: 'fifo', thresholdRate: 1 },
    opts,
  )
}

export default useF2ValuationMonthlySheet
