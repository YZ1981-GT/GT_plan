/**
 * useF2CostComparison — F2-20 产成品单位成本年度比较分析表
 *
 * 对齐 xlsx：本年/上年单位成本（材料/人工/制造/合计）+ 波动比例 + 是否异常 + 索引
 * + 审计说明 / 审计结论
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { parseNum, calcChangeRate, isChangeRateExceeding } from './useF2InvMaiFormulaEngine'
import type { ChecklistResponse } from './useF2FormData'

export type F2YesNo = '是' | '否' | ''

export interface F2CostRow {
  rowId: string
  productName: string
  /** 本年单位成本 */
  currentMaterial: number
  currentLabor: number
  currentOverhead: number
  /** 上年单位成本 */
  priorMaterial: number
  priorLabor: number
  priorOverhead: number
  /** 是否存在异常波动（可人工覆盖；空则按阈值自动提示） */
  abnormal: F2YesNo
  indexRef: string
  /** legacy */
  currentQty?: number
  priorQty?: number
  anomalyNote?: string
}

export interface F2CostPack {
  version: 2
  rows: F2CostRow[]
  auditNote: string
  auditConclusion: string
  /** 波动异常阈值（默认 20%） */
  anomalyThreshold: number
}

const STORAGE_KEY = 'F2-20-pack'
const LEGACY_ROWS_KEY = 'F2-20-rows'
const LEGACY_CONCLUSION_KEY = 'F2-20-conclusion'
const LEGACY_NOTE_KEY = 'F2-cost-comparison-audit-note'
const LEGACY_AUDIT_CONCLUSION_KEY = 'F2-cost-comparison-audit-conclusion'

function rid(): string {
  return `f2c-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

function emptyRow(): F2CostRow {
  return {
    rowId: rid(),
    productName: '',
    currentMaterial: 0,
    currentLabor: 0,
    currentOverhead: 0,
    priorMaterial: 0,
    priorLabor: 0,
    priorOverhead: 0,
    abnormal: '',
    indexRef: '',
  }
}

function defaultPack(): F2CostPack {
  return {
    version: 2,
    rows: [emptyRow()],
    auditNote: '',
    auditConclusion: '',
    anomalyThreshold: 0.2,
  }
}

function ratePct(prior: number, current: number): number | null {
  const r = calcChangeRate(prior, current)
  if (r === '' || r === 'N/A') return null
  return r * 100
}

function normalizeYesNo(v: unknown): F2YesNo {
  if (v === '是' || v === '否') return v
  return ''
}

function migrateLegacy(rowsJson: string | null | undefined, conclusion: string, note: string): F2CostPack {
  const pack = defaultPack()
  pack.auditConclusion = conclusion || ''
  pack.auditNote = note || ''
  if (!rowsJson) return pack
  try {
    const arr = JSON.parse(rowsJson)
    if (!Array.isArray(arr) || !arr.length) return pack
    pack.rows = arr.map((r: any) => ({
      rowId: r.rowId || rid(),
      productName: String(r.productName || ''),
      currentMaterial: parseNum(r.currentMaterial),
      currentLabor: parseNum(r.currentLabor),
      currentOverhead: parseNum(r.currentOverhead),
      priorMaterial: parseNum(r.priorMaterial),
      priorLabor: parseNum(r.priorLabor),
      priorOverhead: parseNum(r.priorOverhead),
      abnormal: normalizeYesNo(r.abnormal) || (r.anomalyNote ? '是' : ''),
      indexRef: String(r.indexRef || ''),
      anomalyNote: r.anomalyNote != null ? String(r.anomalyNote) : '',
    }))
  } catch { /* ignore */ }
  return pack
}

function parsePack(jsonStr: string | null | undefined): F2CostPack | null {
  if (!jsonStr) return null
  try {
    const parsed = JSON.parse(jsonStr)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    const base = defaultPack()
    if (Array.isArray(parsed.rows) && parsed.rows.length) {
      base.rows = parsed.rows.map((r: any) => ({
        rowId: r.rowId || rid(),
        productName: String(r.productName || ''),
        currentMaterial: parseNum(r.currentMaterial),
        currentLabor: parseNum(r.currentLabor),
        currentOverhead: parseNum(r.currentOverhead),
        priorMaterial: parseNum(r.priorMaterial),
        priorLabor: parseNum(r.priorLabor),
        priorOverhead: parseNum(r.priorOverhead),
        abnormal: normalizeYesNo(r.abnormal),
        indexRef: String(r.indexRef || ''),
      }))
    }
    base.auditNote = parsed.auditNote != null ? String(parsed.auditNote) : ''
    base.auditConclusion = parsed.auditConclusion != null ? String(parsed.auditConclusion) : ''
    if (parsed.anomalyThreshold != null) base.anomalyThreshold = parseNum(parsed.anomalyThreshold) || 0.2
    return base
  } catch {
    return null
  }
}

export function useF2CostComparison(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let hydrating = false
  let writing = false

  const pack = ref<F2CostPack>(defaultPack())
  const activeSegment = ref<'current' | 'variance'>('current')

  function hydrate(): void {
    hydrating = true
    const fromPack = parsePack(allResponses.value.get(STORAGE_KEY)?.remark)
    if (fromPack) {
      pack.value = fromPack
    } else {
      pack.value = migrateLegacy(
        allResponses.value.get(LEGACY_ROWS_KEY)?.remark,
        allResponses.value.get(LEGACY_AUDIT_CONCLUSION_KEY)?.remark
          || allResponses.value.get(LEGACY_CONCLUSION_KEY)?.remark
          || '',
        allResponses.value.get(LEGACY_NOTE_KEY)?.remark || '',
      )
    }
    hydrating = false
  }

  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    () => { if (!writing) hydrate() },
    { immediate: true },
  )

  const enrichedRows = computed(() => {
    const thr = pack.value.anomalyThreshold
    return pack.value.rows.map((r) => {
      const currentTotal = r.currentMaterial + r.currentLabor + r.currentOverhead
      const priorTotal = r.priorMaterial + r.priorLabor + r.priorOverhead
      const matRate = ratePct(r.priorMaterial, r.currentMaterial)
      const laborRate = ratePct(r.priorLabor, r.currentLabor)
      const ohRate = ratePct(r.priorOverhead, r.currentOverhead)
      const totalRate = ratePct(priorTotal, currentTotal)
      const autoAnomaly = isChangeRateExceeding(
        totalRate == null ? '' : totalRate / 100,
        thr,
      )
      const isAnomaly = r.abnormal === '是' || (r.abnormal === '' && autoAnomaly)
      return {
        ...r,
        currentTotal,
        priorTotal,
        matRate,
        laborRate,
        ohRate,
        totalRate,
        varianceRate: totalRate == null ? ('' as const) : totalRate / 100,
        isAnomaly,
        autoAnomaly,
      }
    })
  })

  const anomalyCount = computed(() => enrichedRows.value.filter((r) => r.isAnomaly).length)

  const conclusion = computed({
    get: () => pack.value.auditConclusion,
    set: (v: string) => { if (!readonly.value) { pack.value.auditConclusion = v; persist() } },
  })
  const auditNote = computed({
    get: () => pack.value.auditNote,
    set: (v: string) => { if (!readonly.value) { pack.value.auditNote = v; persist() } },
  })

  function flushSave(): void {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null }
    const item = allResponses.value.get(STORAGE_KEY)
    if (item) window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function persist(): void {
    if (hydrating || readonly.value) return
    writing = true
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: JSON.stringify(pack.value),
    })
    allResponses.value.set(LEGACY_CONCLUSION_KEY, {
      item_id: LEGACY_CONCLUSION_KEY,
      conclusion: null,
      remark: pack.value.auditConclusion,
    })
    writing = false
    debounceSave()
  }

  function addRow(): void {
    if (readonly.value) return
    pack.value.rows.push(emptyRow())
    persist()
  }

  function removeRow(rowId: string): void {
    if (readonly.value || pack.value.rows.length <= 1) return
    pack.value.rows = pack.value.rows.filter((r) => r.rowId !== rowId)
    persist()
  }

  function updateCell(rowId: string, field: keyof F2CostRow, value: any): void {
    if (readonly.value) return
    const idx = pack.value.rows.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const row = { ...pack.value.rows[idx] }
    if (field === 'productName' || field === 'indexRef' || field === 'anomalyNote') {
      (row as any)[field] = String(value ?? '')
    } else if (field === 'abnormal') {
      row.abnormal = normalizeYesNo(value)
    } else {
      (row as any)[field] = parseNum(value)
    }
    pack.value.rows.splice(idx, 1, row)
    persist()
  }

  function aiContext(): Record<string, unknown> {
    return {
      rows: enrichedRows.value.map((r) => ({
        productName: r.productName,
        currentTotal: r.currentTotal,
        priorTotal: r.priorTotal,
        totalRate: r.totalRate,
        isAnomaly: r.isAnomaly,
        indexRef: r.indexRef,
      })),
      anomalyCount: anomalyCount.value,
      threshold: pack.value.anomalyThreshold,
    }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); flushSave() }
  })

  return {
    pack,
    enrichedRows,
    anomalyCount,
    conclusion,
    auditNote,
    activeSegment,
    addRow,
    removeRow,
    updateCell,
    aiContext,
    flushSave,
    persist,
  }
}

export default useF2CostComparison
