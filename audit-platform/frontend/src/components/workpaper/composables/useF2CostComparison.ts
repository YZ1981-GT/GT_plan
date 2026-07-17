/**
 * useF2CostComparison — F2-20 产成品单位成本年度比较分析表
 *
 * 功能参照 F2-18：
 * - 可编辑期间标签（本年/上年）
 * - 可配置异常阈值
 * - 表内合计/波动自动计算 + 是否异常（人工覆盖 / 阈值自动）
 * - 分段「审计说明 + 异常原因」+ 总体审计结论
 * - pack v2 持久化 + legacy 迁移
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { parseNum, calcChangeRate, isChangeRateExceeding } from './useF2InvMaiFormulaEngine'
import type { ChecklistResponse } from './useF2FormData'

export type F2YesNo = '是' | '否' | ''

export interface F2SectionNotes {
  note: string
  abnormalReason: string
}

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
  /** 是否存在异常波动（空=按阈值自动） */
  abnormal: F2YesNo
  indexRef: string
  /** legacy */
  currentQty?: number
  priorQty?: number
  anomalyNote?: string
}

export interface F2CostPack {
  version: 2
  yearLabels: [string, string]
  rows: F2CostRow[]
  notes: F2SectionNotes
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

function emptyNotes(): F2SectionNotes {
  return { note: '', abnormalReason: '' }
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
    yearLabels: ['本年', '上年'],
    rows: [emptyRow()],
    notes: emptyNotes(),
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

function normalizeNotes(raw: unknown, fallbackNote = ''): F2SectionNotes {
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    const o = raw as Record<string, unknown>
    return {
      note: o.note != null ? String(o.note) : fallbackNote,
      abnormalReason: o.abnormalReason != null ? String(o.abnormalReason) : '',
    }
  }
  return { note: fallbackNote, abnormalReason: '' }
}

function mapRow(r: any): F2CostRow {
  return {
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
  }
}

function migrateLegacy(rowsJson: string | null | undefined, conclusion: string, note: string): F2CostPack {
  const pack = defaultPack()
  pack.auditConclusion = conclusion || ''
  pack.notes = { note: note || '', abnormalReason: '' }
  if (!rowsJson) return pack
  try {
    const arr = JSON.parse(rowsJson)
    if (!Array.isArray(arr) || !arr.length) return pack
    pack.rows = arr.map(mapRow)
  } catch { /* ignore */ }
  return pack
}

function parsePack(jsonStr: string | null | undefined): F2CostPack | null {
  if (!jsonStr) return null
  try {
    const parsed = JSON.parse(jsonStr)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    const base = defaultPack()
    if (Array.isArray(parsed.yearLabels) && parsed.yearLabels.length >= 2) {
      base.yearLabels = [String(parsed.yearLabels[0] || '本年'), String(parsed.yearLabels[1] || '上年')]
    }
    if (Array.isArray(parsed.rows) && parsed.rows.length) {
      base.rows = parsed.rows.map(mapRow)
    }
    const flatNote = parsed.auditNote != null ? String(parsed.auditNote) : ''
    base.notes = normalizeNotes(parsed.notes, flatNote)
    base.auditConclusion = parsed.auditConclusion != null ? String(parsed.auditConclusion) : ''
    if (parsed.anomalyThreshold != null) {
      const t = parseNum(parsed.anomalyThreshold)
      base.anomalyThreshold = t > 0 ? t : 0.2
    }
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

  const yearLabels = computed(() => pack.value.yearLabels)

  const enrichedRows = computed(() => {
    const thr = pack.value.anomalyThreshold
    const thrPct = thr * 100
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
        thrPct,
        matHot: matRate != null && Math.abs(matRate) > thrPct,
        laborHot: laborRate != null && Math.abs(laborRate) > thrPct,
        ohHot: ohRate != null && Math.abs(ohRate) > thrPct,
      }
    })
  })

  const totals = computed(() => {
    const rows = enrichedRows.value
    return {
      currentMaterial: rows.reduce((s, r) => s + r.currentMaterial, 0),
      currentLabor: rows.reduce((s, r) => s + r.currentLabor, 0),
      currentOverhead: rows.reduce((s, r) => s + r.currentOverhead, 0),
      currentTotal: rows.reduce((s, r) => s + r.currentTotal, 0),
      priorMaterial: rows.reduce((s, r) => s + r.priorMaterial, 0),
      priorLabor: rows.reduce((s, r) => s + r.priorLabor, 0),
      priorOverhead: rows.reduce((s, r) => s + r.priorOverhead, 0),
      priorTotal: rows.reduce((s, r) => s + r.priorTotal, 0),
    }
  })

  const anomalyCount = computed(() => enrichedRows.value.filter((r) => r.isAnomaly).length)

  const notes = computed({
    get: () => pack.value.notes,
    set: (v: F2SectionNotes) => {
      if (readonly.value) return
      pack.value.notes = { note: v.note || '', abnormalReason: v.abnormalReason || '' }
      persist()
    },
  })

  /** 兼容旧 API：审计说明正文 */
  const auditNote = computed({
    get: () => pack.value.notes.note,
    set: (v: string) => {
      if (readonly.value) return
      pack.value.notes = { ...pack.value.notes, note: v }
      persist()
    },
  })

  const conclusion = computed({
    get: () => pack.value.auditConclusion,
    set: (v: string) => {
      if (readonly.value) return
      pack.value.auditConclusion = v
      persist()
    },
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

  function updateYearLabel(idx: 0 | 1, value: string): void {
    if (readonly.value) return
    const next = [...pack.value.yearLabels] as [string, string]
    next[idx] = value || (idx === 0 ? '本年' : '上年')
    pack.value.yearLabels = next
    persist()
  }

  function updateThreshold(value: number): void {
    if (readonly.value) return
    const t = parseNum(value)
    pack.value.anomalyThreshold = t > 0 ? t : 0.2
    persist()
  }

  function updateNotes(field: keyof F2SectionNotes, value: string): void {
    if (readonly.value) return
    pack.value.notes = { ...pack.value.notes, [field]: value }
    persist()
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
      ;(row as any)[field] = String(value ?? '')
    } else if (field === 'abnormal') {
      row.abnormal = normalizeYesNo(value)
    } else {
      ;(row as any)[field] = parseNum(value)
    }
    pack.value.rows.splice(idx, 1, row)
    persist()
  }

  function aiContext(): Record<string, unknown> {
    return {
      yearLabels: pack.value.yearLabels,
      threshold: pack.value.anomalyThreshold,
      thresholdPct: pack.value.anomalyThreshold * 100,
      rows: enrichedRows.value.map((r) => ({
        productName: r.productName,
        current: {
          material: r.currentMaterial,
          labor: r.currentLabor,
          overhead: r.currentOverhead,
          total: r.currentTotal,
        },
        prior: {
          material: r.priorMaterial,
          labor: r.priorLabor,
          overhead: r.priorOverhead,
          total: r.priorTotal,
        },
        rates: {
          material: r.matRate,
          labor: r.laborRate,
          overhead: r.ohRate,
          total: r.totalRate,
        },
        isAnomaly: r.isAnomaly,
        autoAnomaly: r.autoAnomaly,
        abnormal: r.abnormal,
        indexRef: r.indexRef,
      })),
      anomalyCount: anomalyCount.value,
      notes: pack.value.notes,
      totals: totals.value,
    }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); flushSave() }
  })

  return {
    pack,
    yearLabels,
    enrichedRows,
    totals,
    anomalyCount,
    notes,
    auditNote,
    conclusion,
    updateYearLabel,
    updateThreshold,
    updateNotes,
    addRow,
    removeRow,
    updateCell,
    aiContext,
    flushSave,
    persist,
  }
}

export default useF2CostComparison
