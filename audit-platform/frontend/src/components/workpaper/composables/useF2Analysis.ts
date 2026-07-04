/**
 * useF2Analysis — F2-18/19/20 分析组 composable
 * Spec: .kiro/specs/f2-inventory-main/ Task 11.1
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcSubtotal,
  calcChangeRate,
  calcChangeAmount,
  isChangeRateExceeding,
} from './useF2InvMaiFormulaEngine'
import { readRowJson, type ChecklistResponse } from './useF2FormData'
import type { useF2CrossSheet } from './useF2CrossSheet'

type CrossSheet = ReturnType<typeof useF2CrossSheet>

// ─── F2-18 总体分析 ───────────────────────────────────────────────────────

const OVERALL_KEY = 'F2-18-conclusion'
const TURNOVER_KEY = 'F2-18-turnover'

export interface F2StructureRow {
  label: string
  sheetCode: string
  currentAmt: number
  priorAmt: number
  sharePct: number
  shareChange: number
  isHighlight: boolean
}

export interface F2AnomalyItem {
  id: string
  type: string
  message: string
  severity: 'warning' | 'danger'
}

export function useF2OverallAnalysis(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  crossSheet: CrossSheet
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, crossSheet, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const analysisConclusion = ref('')
  const turnoverRate = ref(0)
  const turnoverDays = ref(0)
  const cogsAmount = ref(0)

  watch(() => allResponses.value.get(OVERALL_KEY)?.remark, (v) => { analysisConclusion.value = v || '' }, { immediate: true })
  watch(() => allResponses.value.get(TURNOVER_KEY)?.remark, (v) => {
    if (!v) return
    try {
      const d = JSON.parse(v)
      turnoverRate.value = parseNum(d.turnoverRate)
      turnoverDays.value = parseNum(d.turnoverDays)
      cogsAmount.value = parseNum(d.cogsAmount)
    } catch { /* ignore */ }
  }, { immediate: true })

  const structureRows: ComputedRef<F2StructureRow[]> = computed(() => {
    const summaries = crossSheet.categorySummaries.value
    const total = crossSheet.detailGrandTotal.value || 1
    return summaries.map((s) => {
      const prior = s.openingAmt
      const current = s.closingAmt
      const sharePct = total ? (current / total) * 100 : 0
      const priorTotal = crossSheet.detailOpeningTotal.value || 1
      const priorShare = priorTotal ? (prior / priorTotal) * 100 : 0
      const shareChange = sharePct - priorShare
      return {
        label: s.label,
        sheetCode: s.sheetCode,
        currentAmt: current,
        priorAmt: prior,
        sharePct,
        shareChange,
        isHighlight: Math.abs(shareChange) > 5,
      }
    })
  })

  const computedTurnoverRate = computed(() => {
    const avg = (crossSheet.detailGrandTotal.value + crossSheet.detailOpeningTotal.value) / 2
    if (!avg || !cogsAmount.value) return turnoverRate.value
    return cogsAmount.value / avg
  })

  const computedTurnoverDays = computed(() => {
    const rate = computedTurnoverRate.value
    return rate ? 365 / rate : turnoverDays.value
  })

  const anomalies: ComputedRef<F2AnomalyItem[]> = computed(() => {
    const items: F2AnomalyItem[] = []
    if (computedTurnoverRate.value > 0 && turnoverRate.value > 0) {
      const drop = (turnoverRate.value - computedTurnoverRate.value) / turnoverRate.value
      if (drop > 0.2) {
        items.push({
          id: 'turnover-drop',
          type: '周转下降',
          message: `存货周转率下降 ${(drop * 100).toFixed(1)}%`,
          severity: 'warning',
        })
      }
    }
    for (const row of structureRows.value) {
      if (row.isHighlight) {
        items.push({
          id: `share-${row.sheetCode}`,
          type: '结构变动',
          message: `${row.label}占比变动 ${row.shareChange.toFixed(1)}%`,
          severity: 'warning',
        })
      }
    }
    return items
  })

  function flushSave(): void {
    const items = [
      allResponses.value.get(OVERALL_KEY),
      allResponses.value.get(TURNOVER_KEY),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items } }))
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function updateTurnoverInputs(patch: { cogsAmount?: number; turnoverRate?: number; turnoverDays?: number }): void {
    if (readonly.value) return
    if (patch.cogsAmount !== undefined) cogsAmount.value = patch.cogsAmount
    if (patch.turnoverRate !== undefined) turnoverRate.value = patch.turnoverRate
    if (patch.turnoverDays !== undefined) turnoverDays.value = patch.turnoverDays
    allResponses.value.set(TURNOVER_KEY, {
      item_id: TURNOVER_KEY,
      conclusion: null,
      remark: JSON.stringify({
        cogsAmount: cogsAmount.value,
        turnoverRate: turnoverRate.value,
        turnoverDays: turnoverDays.value,
      }),
    })
    debounceSave()
  }

  watch(analysisConclusion, (val) => {
    if (readonly.value) return
    allResponses.value.set(OVERALL_KEY, { item_id: OVERALL_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); flushSave() }
  })

  return {
    structureRows,
    anomalies,
    analysisConclusion,
    cogsAmount,
    turnoverRate,
    turnoverDays,
    computedTurnoverRate,
    computedTurnoverDays,
    updateTurnoverInputs,
  }
}

// ─── F2-19 产销量变动 ───────────────────────────────────────────────────────

export interface F2ProductionSalesRow {
  rowId: string
  productName: string
  currentProduction: number
  priorProduction: number
  currentSales: number
  priorSales: number
  openingStock: number
  inbound: number
  outbound: number
  closingStock: number
}

const PS_ROWS_KEY = 'F2-19-rows'
const PS_CONCLUSION_KEY = 'F2-19-conclusion'

function psEmptyRow(): F2ProductionSalesRow {
  return {
    rowId: `f2ps-${Date.now().toString(36)}`,
    productName: '',
    currentProduction: 0,
    priorProduction: 0,
    currentSales: 0,
    priorSales: 0,
    openingStock: 0,
    inbound: 0,
    outbound: 0,
    closingStock: 0,
  }
}

function parsePsRows(json: string | null | undefined): F2ProductionSalesRow[] {
  if (!json) return [psEmptyRow()]
  try {
    const arr = JSON.parse(json)
    return Array.isArray(arr) && arr.length ? arr : [psEmptyRow()]
  } catch {
    return [psEmptyRow()]
  }
}

export function useF2ProductionSales(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const activeSegment = ref<'production' | 'sales' | 'inventory'>('production')

  const rows = ref<F2ProductionSalesRow[]>([psEmptyRow()])
  const conclusion = ref('')

  watch(() => allResponses.value.get(PS_ROWS_KEY)?.remark, (v) => { rows.value = parsePsRows(v) }, { immediate: true })
  watch(() => allResponses.value.get(PS_CONCLUSION_KEY)?.remark, (v) => { conclusion.value = v || '' }, { immediate: true })

  function enrichRow(r: F2ProductionSalesRow) {
    const productionRate = r.currentProduction ? (r.currentSales / r.currentProduction) * 100 : 0
    const stockBalanced = Math.abs(r.openingStock + r.inbound - r.outbound - r.closingStock) < 0.01
    const prodChange = calcChangeRate(r.priorProduction, r.currentProduction)
    const salesChange = calcChangeRate(r.priorSales, r.currentSales)
    return { ...r, productionRate, stockBalanced, prodChange, salesChange, isLowSalesRate: productionRate > 0 && productionRate < 80 }
  }

  const enrichedRows = computed(() => rows.value.map(enrichRow))
  const useVirtualScroll = computed(() => rows.value.length > 100)

  function persist(): void {
    allResponses.value.set(PS_ROWS_KEY, { item_id: PS_ROWS_KEY, conclusion: null, remark: JSON.stringify(rows.value) })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      const items = [allResponses.value.get(PS_ROWS_KEY), allResponses.value.get(PS_CONCLUSION_KEY)].filter(Boolean)
      if (items.length) window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items } }))
    }, 2000)
  }

  function addRow(): void {
    if (readonly.value) return
    rows.value = [...rows.value, psEmptyRow()]
    persist()
  }

  function removeRow(rowId: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    persist()
  }

  function updateCell(rowId: string, field: keyof F2ProductionSalesRow, value: any): void {
    if (readonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const row = { ...rows.value[idx] }
    if (field === 'productName') row.productName = String(value ?? '')
    else (row as any)[field] = parseNum(value)
    rows.value.splice(idx, 1, row)
    persist()
  }

  watch(conclusion, (val) => {
    if (readonly.value) return
    allResponses.value.set(PS_CONCLUSION_KEY, { item_id: PS_CONCLUSION_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); debounceSave() } })

  return { activeSegment, enrichedRows, useVirtualScroll, conclusion, addRow, removeRow, updateCell }
}

// ─── F2-20 成本比较 ───────────────────────────────────────────────────────

export interface F2CostRow {
  rowId: string
  productName: string
  currentQty: number
  currentMaterial: number
  currentLabor: number
  currentOverhead: number
  priorQty: number
  priorMaterial: number
  priorLabor: number
  priorOverhead: number
  anomalyNote: string
}

const COST_ROWS_KEY = 'F2-20-rows'
const COST_CONCLUSION_KEY = 'F2-20-conclusion'

function costEmptyRow(): F2CostRow {
  return {
    rowId: `f2c-${Date.now().toString(36)}`,
    productName: '',
    currentQty: 0,
    currentMaterial: 0,
    currentLabor: 0,
    currentOverhead: 0,
    priorQty: 0,
    priorMaterial: 0,
    priorLabor: 0,
    priorOverhead: 0,
    anomalyNote: '',
  }
}

export function useF2CostComparison(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const activeSegment = ref<'current' | 'variance'>('current')
  const conclusion = ref('')

  const rows = ref<F2CostRow[]>([costEmptyRow()])

  watch(() => allResponses.value.get(COST_CONCLUSION_KEY)?.remark, (v) => { conclusion.value = v || '' }, { immediate: true })
  watch(() => allResponses.value.get(COST_ROWS_KEY)?.remark, (v) => {
    if (!v) { rows.value = [costEmptyRow()]; return }
    try {
      const arr = JSON.parse(v)
      rows.value = Array.isArray(arr) && arr.length ? arr : [costEmptyRow()]
    } catch { rows.value = [costEmptyRow()] }
  }, { immediate: true })

  function enrichCostRow(r: F2CostRow) {
    const currentTotal = r.currentMaterial + r.currentLabor + r.currentOverhead
    const priorTotal = r.priorMaterial + r.priorLabor + r.priorOverhead
    const variance = calcChangeAmount(currentTotal, priorTotal)
    const varianceRate = calcChangeRate(priorTotal, currentTotal)
    const isAnomaly = isChangeRateExceeding(varianceRate, 0.2)
    return { ...r, currentTotal, priorTotal, variance, varianceRate, isAnomaly }
  }

  const enrichedRows = computed(() => rows.value.map(enrichCostRow))
  const anomalyCount = computed(() => enrichedRows.value.filter((r) => r.isAnomaly).length)

  function persist(): void {
    allResponses.value.set(COST_ROWS_KEY, { item_id: COST_ROWS_KEY, conclusion: null, remark: JSON.stringify(rows.value) })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      const item = allResponses.value.get(COST_ROWS_KEY)
      if (item) window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
    }, 2000)
  }

  function addRow(): void {
    if (readonly.value) return
    rows.value = [...rows.value, costEmptyRow()]
    persist()
  }

  function removeRow(rowId: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    persist()
  }

  function updateCell(rowId: string, field: keyof F2CostRow, value: any): void {
    if (readonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const row = { ...rows.value[idx] }
    if (field === 'productName' || field === 'anomalyNote') (row as any)[field] = String(value ?? '')
    else (row as any)[field] = parseNum(value)
    rows.value.splice(idx, 1, row)
    persist()
  }

  onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); persist() } })

  watch(conclusion, (val) => {
    allResponses.value.set(COST_CONCLUSION_KEY, { item_id: COST_CONCLUSION_KEY, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      const item = allResponses.value.get(COST_CONCLUSION_KEY)
      if (item) window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
    }, 2000)
  })

  return { activeSegment, enrichedRows, anomalyCount, conclusion, addRow, removeRow, updateCell }
}

export default useF2OverallAnalysis
