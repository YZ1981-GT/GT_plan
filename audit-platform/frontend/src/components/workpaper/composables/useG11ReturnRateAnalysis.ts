/**
 * useG11ReturnRateAnalysis — G11-4 收益率分析
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  G11_RETURN_RATE_ITEMS,
  G11_RETURN_RATE_CHANGE_THRESHOLD,
} from './g11Constants'
import {
  parseNum,
  calcAverageBalance,
  calcReturnRate,
  calcReturnRateChange,
  isReturnRateChangeExceeding,
} from './useG11FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface G11ReturnRateRow {
  id: string
  itemName: string
  currentIncome: number
  currentOpening: number
  currentClosing: number
  currentAvgBalance: number
  currentReturnRate: number | null
  priorAudited: number
  priorOpening: number
  priorClosing: number
  priorAvgBalance: number
  priorReturnRate: number | null
  returnRateChange: number | null
  abnormalNote: string
  abnormalHighlight: boolean
}

const ITEM_ID_ROWS = 'G11-return-rate-rows'
const ITEM_ID_CONCLUSION = 'G11-return-rate-conclusion'

function generateId(): string {
  return `g11rr-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

function defaultRows(): G11ReturnRateRow[] {
  return G11_RETURN_RATE_ITEMS.map((def) => enrichRow({
    id: generateId(),
    itemName: def.label,
    currentIncome: 0,
    currentOpening: 0,
    currentClosing: 0,
    priorAudited: 0,
    priorOpening: 0,
    priorClosing: 0,
    abnormalNote: '',
  }))
}

function enrichRow(raw: Partial<G11ReturnRateRow> & { itemName: string }): G11ReturnRateRow {
  const currentIncome = parseNum(raw.currentIncome)
  const currentOpening = parseNum(raw.currentOpening)
  const currentClosing = parseNum(raw.currentClosing)
  const currentAvgBalance = calcAverageBalance(currentOpening, currentClosing)
  const priorAudited = parseNum(raw.priorAudited)
  const priorOpening = parseNum(raw.priorOpening)
  const priorClosing = parseNum(raw.priorClosing)
  const priorAvgBalance = calcAverageBalance(priorOpening, priorClosing)
  const currentReturnRate = calcReturnRate(currentIncome, currentAvgBalance)
  const priorReturnRate = calcReturnRate(priorAudited, priorAvgBalance)
  const returnRateChange = calcReturnRateChange(currentReturnRate, priorReturnRate)
  return {
    id: raw.id ?? generateId(),
    itemName: raw.itemName,
    currentIncome,
    currentOpening,
    currentClosing,
    currentAvgBalance,
    currentReturnRate,
    priorAudited,
    priorOpening,
    priorClosing,
    priorAvgBalance,
    priorReturnRate,
    returnRateChange,
    abnormalNote: raw.abnormalNote ?? '',
    abnormalHighlight: isReturnRateChangeExceeding(returnRateChange, G11_RETURN_RATE_CHANGE_THRESHOLD),
  }
}

function parseRows(json: string | null | undefined): G11ReturnRateRow[] {
  if (!json) return defaultRows()
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed) || parsed.length === 0) return defaultRows()
    return parsed.map((r) => enrichRow(r))
  } catch {
    return defaultRows()
  }
}

export function useG11ReturnRateAnalysis(opts: {
  wpId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G11ReturnRateRow[]>(defaultRows())
  const conclusion = ref('')
  const aiLoading = ref(false)

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => { rows.value = parseRows(json) },
    { immediate: true },
  )
  watch(
    () => opts.allResponses.value.get(ITEM_ID_CONCLUSION)?.conclusion,
    (v) => { conclusion.value = v ?? '' },
    { immediate: true },
  )

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  function updateRow(id: string, patch: Partial<G11ReturnRateRow> & Record<string, unknown>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrichRow({ ...r, ...patch }) : r))
    persist()
  }

  function updateBalance(
    id: string,
    field: 'currentOpening' | 'currentClosing' | 'priorOpening' | 'priorClosing',
    value: number,
  ): void {
    if (opts.isReadonly.value) return
    updateRow(id, { [field]: value } as Partial<G11ReturnRateRow>)
  }

  function reloadFromStore(): void {
    const json = opts.allResponses.value.get(ITEM_ID_ROWS)?.remark
    rows.value = parseRows(json)
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入投资项目名称', '新增收益率分析行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      })
      if (!value?.trim()) return
      rows.value = [...rows.value, enrichRow({ itemName: value.trim() })]
      persist()
    } catch { /* cancelled */ }
  }

  function removeRow(id: string): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.id !== id)
    persist()
  }

  function updateConclusion(value: string): void {
    if (opts.isReadonly.value) return
    conclusion.value = value
    opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: value })
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value) return
    aiLoading.value = true
    try {
      const res = await api.post(`/api/workpapers/${opts.wpId.value}/g11/ai/return-rate-conclusion`, {
        rows: rows.value.filter((r) => r.abnormalHighlight),
      }, { _silent: true } as any)
      const text = res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
      if (text) updateConclusion(text)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  const abnormalCount = computed(() => rows.value.filter((r) => r.abnormalHighlight).length)

  return {
    rows,
    conclusion,
    aiLoading,
    abnormalCount,
    updateRow,
    updateBalance,
    addRow,
    removeRow,
    updateConclusion,
    generateAiConclusion,
    reloadFromStore,
  }
}
