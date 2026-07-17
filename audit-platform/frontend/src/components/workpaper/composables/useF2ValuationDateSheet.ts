/**
 * useF2ValuationDateSheet — F2-39 按日期多产品计价测试
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import type { SamplingParams } from './useF2ValuationTestFormulas'
import {
  defaultThreeDateProjects,
  enrichDateProject,
  calcDateProjectTotals,
  calcDateBundleVariance,
  migrateToDateProjects,
  emptyDateProject,
  emptyTxnLine,
  type ValuationDateProject,
  type ValuationDateLine,
  type DateCostingMode,
} from './useF2ValuationDateFormulas'

function absRate(variance: number, book: number): number {
  if (!book) return variance ? 100 : 0
  return Math.abs(variance / book) * 100
}

export function useF2ValuationDateSheet(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const sheetCode = 'F2-39'
  const rowsKey = `${sheetCode}-rows`
  const paramsKey = `${sheetCode}-sampling`
  const conclusionKey = `${sheetCode}-conclusion`
  const objectiveKey = `${sheetCode}-objective`
  const samplingTextKey = `${sheetCode}-sampling-text`
  const costingModeKey = `${sheetCode}-costing-mode`

  const thresholdRate = 1
  const projects = ref<ValuationDateProject[]>(defaultThreeDateProjects())
  const costingMode = ref<DateCostingMode>('fifo')
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
        const migrated = migrateToDateProjects(parsed)
        if (migrated?.length) projects.value = migrated
      } catch { /* ignore */ }
    }
    const modeRaw = readValRowJson(opts.allResponses.value.get(costingModeKey))
    if (modeRaw === 'fifo' || modeRaw === 'moving-wa') costingMode.value = modeRaw
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
    projects.value.map((p) => enrichDateProject(p, costingMode.value)),
  )

  const bundleVariance = computed(() => calcDateBundleVariance(enrichedProjects.value))

  const exceedCount = computed(() => {
    let count = 0
    for (const p of enrichedProjects.value) {
      for (const l of p.lines) {
        if (l.kind === 'opening') continue
        if (absRate(l.variance, l.saleAmt) > thresholdRate && Math.abs(l.variance) > 0.005) count += 1
      }
    }
    return count
  })

  function projectTotals(p: ValuationDateProject) {
    return calcDateProjectTotals(enrichDateProject(p, costingMode.value).lines)
  }

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(rowsKey),
      opts.allResponses.value.get(paramsKey),
      opts.allResponses.value.get(conclusionKey),
      opts.allResponses.value.get(objectiveKey),
      opts.allResponses.value.get(samplingTextKey),
      opts.allResponses.value.get(costingModeKey),
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
    opts.allResponses.value.set(costingModeKey, {
      item_id: costingModeKey,
      conclusion: null,
      remark: costingMode.value,
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

  function updateProject(id: string, patch: Partial<ValuationDateProject>): void {
    if (readonly.value) return
    projects.value = projects.value.map((p) => (p.id === id ? { ...p, ...patch } : p))
    persist()
  }

  function updateLine(
    projectId: string,
    lineId: string,
    patch: Partial<ValuationDateLine>,
  ): void {
    if (readonly.value) return
    projects.value = projects.value.map((p) => {
      if (p.id !== projectId) return p
      return {
        ...p,
        lines: p.lines.map((l) => {
          if (l.id !== lineId) return l
          const next = { ...l, ...patch }
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

  function addTxnLine(projectId: string): void {
    if (readonly.value) return
    projects.value = projects.value.map((p) =>
      p.id === projectId ? { ...p, lines: [...p.lines, emptyTxnLine()] } : p,
    )
    persist()
  }

  function removeTxnLine(projectId: string, lineId: string): void {
    if (readonly.value) return
    projects.value = projects.value.map((p) => {
      if (p.id !== projectId) return p
      const target = p.lines.find((l) => l.id === lineId)
      if (!target || target.kind === 'opening') return p
      return { ...p, lines: p.lines.filter((l) => l.id !== lineId) }
    })
    persist()
  }

  function addProject(): void {
    if (readonly.value) return
    const seq = projects.value.length + 1
    projects.value = [...projects.value, emptyDateProject(seq)]
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

  function setCostingMode(mode: DateCostingMode): void {
    if (readonly.value) return
    costingMode.value = mode
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
    costingMode,
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
    updateLine,
    addTxnLine,
    removeTxnLine,
    addProject,
    removeProject,
    setCostingMode,
    setObjective: (v: string) => persistText(objectiveKey, v, testObjective),
    setSamplingCriteria: (v: string) => persistText(samplingTextKey, v, samplingCriteria),
  }
}

export default useF2ValuationDateSheet
