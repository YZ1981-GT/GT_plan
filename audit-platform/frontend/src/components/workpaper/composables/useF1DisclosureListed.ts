/**
 * useF1DisclosureListed — 预付账款附注披露（上市公司）
 * 对齐 Excel：账龄分析(+比例) / 超1年重要 / 前五名(汇总+分别) + 同步附注五、7
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, calcPercentage } from './useF1FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import type { useF1CrossSheet } from './useF1CrossSheet'
import { computeTop5 } from './useF1Analysis'
import { PRESET_SEGMENTS, type AgingSegment } from '@/composables/useAgingConfig'
import { isF1DisclosureApplicable } from './f1NoteSectionMap'
import type { F1ListedSyncSnapshot } from './f1DisclosureSyncPayload'

export interface F1AgingDisclosureRow {
  rowId: string
  key: string
  label: string
  endAmount: number
  endPct: number
  priorAmount: number
  priorPct: number
}

export interface F1Over1YearRow {
  rowId: string
  debtorName: string
  endBalance: number
  proportionPct: number
  impairment: number
  reason: string
  fromCrossSheet: boolean
}

export interface F1Top5Row {
  rowId: string
  entityName: string
  endBalance: number
  proportionPct: number
}

export interface UseF1DisclosureListedOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useF1CrossSheet>
  isReadonly: Ref<boolean>
  applicableStandards: Ref<string[]>
}

const PREFIX = 'F1-note-listed-'
const ITEM_OVER1_ROWS = `${PREFIX}over1-rows`
const ITEM_OVER1_REASON_MAP = `${PREFIX}over1-reasons`
const ITEM_IMPAIRMENT = `${PREFIX}impairment-provision`
const ITEM_TOP5_SUMMARY = `${PREFIX}top5-summary`

/** 附注模板账龄标签（1至2年）；与 PRESET 的 1-2年 对齐 */
const NOTE_AGING_LABEL: Record<string, string> = {
  within1: '1年以内',
  y1to2: '1至2年',
  y2to3: '2至3年',
  over3: '3年以上',
}

function generateRowId(): string {
  return `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function safeParseJson<T>(jsonStr: string | null | undefined, fallback: T): T {
  if (!jsonStr) return fallback
  try {
    const parsed = JSON.parse(jsonStr)
    return (parsed ?? fallback) as T
  } catch {
    return fallback
  }
}

function fmtMoneyPlain(v: number): string {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPctPlain(v: number): string {
  return `${v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
}

/**
 * 将任意账龄聚合折叠为披露四档（1年以内 / 1至2 / 2至3 / 3年以上）
 */
export function collapseAgingForListedDisclosure(
  agingAgg: Record<string, number> | null | undefined,
  segments: AgingSegment[] = PRESET_SEGMENTS.THREE_YEAR,
): Array<{ key: string; label: string; endAmount: number; priorAmount: number }> {
  const src = agingAgg ?? {}
  const keys = segments.map((s) => s.key)
  const get = (k: string) => parseNum(src[k])
  const getPrior = (k: string) => parseNum(src[`prior_${k}`])

  const within1 = keys.includes('within1') ? 'within1' : keys[0]
  const y1to2 = keys.find((k) => k === 'y1to2') || keys[1]
  const y2to3 = keys.find((k) => k === 'y2to3') || keys[2]
  const restKeys = keys.filter((k) => k !== within1 && k !== y1to2 && k !== y2to3)

  const buckets = [
    { key: 'within1', label: NOTE_AGING_LABEL.within1, endAmount: get(within1), priorAmount: getPrior(within1) },
    { key: 'y1to2', label: NOTE_AGING_LABEL.y1to2, endAmount: get(y1to2), priorAmount: getPrior(y1to2) },
    { key: 'y2to3', label: NOTE_AGING_LABEL.y2to3, endAmount: get(y2to3), priorAmount: getPrior(y2to3) },
    {
      key: 'over3',
      label: NOTE_AGING_LABEL.over3,
      endAmount: calcSubtotal(restKeys.map(get)),
      priorAmount: calcSubtotal(restKeys.map(getPrior)),
    },
  ]
  return buckets
}

export function useF1DisclosureListed(options: UseF1DisclosureListedOptions) {
  const { allResponses, debouncedSave, crossSheet, isReadonly, applicableStandards } = options
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  const isApplicable: ComputedRef<boolean> = computed(() =>
    isF1DisclosureApplicable('listed', applicableStandards.value),
  )

  // ─── (1) 账龄分析 ───────────────────────────────────────────────────

  const impairmentProvision = ref(0)
  watch(
    () => allResponses.value.get(ITEM_IMPAIRMENT)?.remark,
    (v) => { impairmentProvision.value = parseNum(v) },
    { immediate: true },
  )

  const agingRows: ComputedRef<F1AgingDisclosureRow[]> = computed(() => {
    const agg = crossSheet.agingAggregation?.value ?? {}
    const buckets = collapseAgingForListedDisclosure(agg)
    const endTotal = calcSubtotal(buckets.map((b) => b.endAmount))
    const priorTotal = calcSubtotal(buckets.map((b) => b.priorAmount))
    return buckets.map((b) => ({
      rowId: `aging-${b.key}`,
      key: b.key,
      label: b.label,
      endAmount: b.endAmount,
      endPct: calcPercentage(b.endAmount, endTotal),
      priorAmount: b.priorAmount,
      priorPct: calcPercentage(b.priorAmount, priorTotal),
    }))
  })

  const agingTotal: ComputedRef<F1AgingDisclosureRow> = computed(() => {
    const endAmount = calcSubtotal(agingRows.value.map((r) => r.endAmount))
    const priorAmount = calcSubtotal(agingRows.value.map((r) => r.priorAmount))
    return {
      rowId: '__subtotal__',
      key: 'total',
      label: '合计',
      endAmount,
      endPct: endAmount ? 100 : 0,
      priorAmount,
      priorPct: priorAmount ? 100 : 0,
    }
  })

  const agingNet = computed(() => ({
    rowId: '__net__',
    label: '合计（减减值后）',
    endAmount: agingTotal.value.endAmount - impairmentProvision.value,
    priorAmount: agingTotal.value.priorAmount,
  }))

  // ─── (2) 超1年重要 ─────────────────────────────────────────────────

  const over1DynamicRows = ref<F1Over1YearRow[]>([])
  const over1ReasonMap = ref<Record<string, string>>({})

  watch(
    () => allResponses.value.get(ITEM_OVER1_ROWS)?.remark,
    (json) => {
      const rows = safeParseJson<Partial<F1Over1YearRow>[]>(json, [])
      over1DynamicRows.value = rows.map((r) => ({
        rowId: r.rowId || generateRowId(),
        debtorName: r.debtorName || '',
        endBalance: parseNum(r.endBalance),
        proportionPct: 0,
        impairment: parseNum(r.impairment),
        reason: r.reason || '',
        fromCrossSheet: false,
      }))
    },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(ITEM_OVER1_REASON_MAP)?.remark,
    (json) => { over1ReasonMap.value = safeParseJson(json, {}) },
    { immediate: true },
  )

  const over1YearRows: ComputedRef<F1Over1YearRow[]> = computed(() => {
    const total = agingTotal.value.endAmount
    const ltRows = crossSheet.longTermRows?.value ?? []
    const cs = ltRows.map((r) => {
      const name = r.customerName || ''
      return {
        rowId: `cs-lt-${name}`,
        debtorName: name,
        endBalance: parseNum(r.endAudited),
        proportionPct: calcPercentage(r.endAudited, total),
        impairment: 0,
        reason: over1ReasonMap.value[name] || r.agingDescription || '',
        fromCrossSheet: true,
      }
    })
    const dyn = over1DynamicRows.value.map((r) => ({
      ...r,
      proportionPct: calcPercentage(r.endBalance, total),
    }))
    return [...cs, ...dyn]
  })

  const over1YearTotal = computed(() => {
    const endBalance = calcSubtotal(over1YearRows.value.map((r) => r.endBalance))
    const impairment = calcSubtotal(over1YearRows.value.map((r) => r.impairment))
    return {
      endBalance,
      proportionPct: calcPercentage(endBalance, agingTotal.value.endAmount),
      impairment,
    }
  })

  // ─── (3) 前五名 ────────────────────────────────────────────────────

  const top5SummaryOverride = ref('')
  watch(
    () => allResponses.value.get(ITEM_TOP5_SUMMARY)?.remark,
    (v) => { top5SummaryOverride.value = v || '' },
    { immediate: true },
  )

  const top5Rows: ComputedRef<F1Top5Row[]> = computed(() => {
    const detResp = allResponses.value.get('F1-det-rows')?.remark
    const raw = safeParseJson<Array<{ customerName?: string; endAudited?: number; priorAudited?: number }>>(detResp, [])
    const rows = raw.map((r) => ({
      customerName: r.customerName || '',
      endAudited: parseNum(r.endAudited),
      priorAudited: parseNum(r.priorAudited),
    }))
    const { top5 } = computeTop5(rows)
    const total = agingTotal.value.endAmount || calcSubtotal(rows.map((r) => r.endAudited))
    return top5.map((r, i) => ({
      rowId: `top5-${i}`,
      entityName: r.customerName,
      endBalance: r.endAudited,
      proportionPct: calcPercentage(r.endAudited, total),
    }))
  })

  const top5Total = computed(() => {
    const endBalance = calcSubtotal(top5Rows.value.map((r) => r.endBalance))
    return {
      endBalance,
      proportionPct: calcPercentage(endBalance, agingTotal.value.endAmount || endBalance),
    }
  })

  const top5SummaryAuto = computed(() => {
    const t = top5Total.value
    if (!t.endBalance) {
      return '本期按预付对象归集的期末余额前五名预付款项汇总金额——元，占预付款项期末余额合计数的比例——%。'
    }
    return `本期按预付对象归集的期末余额前五名预付款项汇总金额${fmtMoneyPlain(t.endBalance)}元，占预付款项期末余额合计数的比例${fmtPctPlain(t.proportionPct)}。`
  })

  const top5SummaryText = computed(() => top5SummaryOverride.value || top5SummaryAuto.value)

  // ─── Notes ───────────────────────────────────────────────────────────

  const note1 = ref('')
  const note2 = ref('')
  const note3 = ref('')

  watch(() => allResponses.value.get(`${PREFIX}note-1`)?.remark, (v) => { note1.value = v || '' }, { immediate: true })
  watch(() => allResponses.value.get(`${PREFIX}note-2`)?.remark, (v) => { note2.value = v || '' }, { immediate: true })
  watch(() => allResponses.value.get(`${PREFIX}note-3`)?.remark, (v) => { note3.value = v || '' }, { immediate: true })

  watch(() => note1.value, (val) => { debouncedSave(`${PREFIX}note-1`, { remark: val }) })
  watch(() => note2.value, (val) => { debouncedSave(`${PREFIX}note-2`, { remark: val }) })
  watch(() => note3.value, (val) => {
    debouncedSave(`${PREFIX}note-3`, { remark: val })
    try {
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: { wpCode: 'F1', section: 'listed-3', text: val },
      }))
    } catch { /* silent */ }
  })

  const noteUpdateHandler = (e: Event) => {
    const detail = (e as CustomEvent).detail
    if (detail?.wpCode === 'F1' && detail?.section?.startsWith('listed-')) {
      const idx = detail.section.replace('listed-', '')
      if (idx === '1') note1.value = detail.text || ''
      else if (idx === '2') note2.value = detail.text || ''
      else if (idx === '3') note3.value = detail.text || ''
    }
  }
  window.addEventListener('note:section-updated', noteUpdateHandler)
  eventListeners.push({ event: 'note:section-updated', handler: noteUpdateHandler })

  // ─── Mutations ───────────────────────────────────────────────────────

  function persistImpairment(val: number) {
    if (isReadonly.value) return
    impairmentProvision.value = parseNum(val)
    debouncedSave(ITEM_IMPAIRMENT, { remark: String(impairmentProvision.value) })
  }

  function updateOver1Reason(rowId: string, reason: string) {
    if (isReadonly.value) return
    const row = over1YearRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    if (row.fromCrossSheet) {
      over1ReasonMap.value = { ...over1ReasonMap.value, [row.debtorName]: reason }
      debouncedSave(ITEM_OVER1_REASON_MAP, { remark: JSON.stringify(over1ReasonMap.value) })
      return
    }
    over1DynamicRows.value = over1DynamicRows.value.map((r) =>
      r.rowId === rowId ? { ...r, reason } : r,
    )
    debouncedSave(ITEM_OVER1_ROWS, { remark: JSON.stringify(over1DynamicRows.value) })
  }

  function updateOver1Field(rowId: string, field: 'debtorName' | 'endBalance' | 'impairment', value: string | number) {
    if (isReadonly.value) return
    const row = over1YearRows.value.find((r) => r.rowId === rowId)
    if (!row || row.fromCrossSheet) return
    over1DynamicRows.value = over1DynamicRows.value.map((r) => {
      if (r.rowId !== rowId) return r
      if (field === 'endBalance' || field === 'impairment') {
        return { ...r, [field]: parseNum(value) }
      }
      return { ...r, debtorName: String(value) }
    })
    debouncedSave(ITEM_OVER1_ROWS, { remark: JSON.stringify(over1DynamicRows.value) })
  }

  function addOver1Row() {
    if (isReadonly.value) return
    over1DynamicRows.value = [
      ...over1DynamicRows.value,
      {
        rowId: generateRowId(),
        debtorName: '',
        endBalance: 0,
        proportionPct: 0,
        impairment: 0,
        reason: '',
        fromCrossSheet: false,
      },
    ]
    debouncedSave(ITEM_OVER1_ROWS, { remark: JSON.stringify(over1DynamicRows.value) })
  }

  function removeOver1Row(rowId: string) {
    if (isReadonly.value) return
    over1DynamicRows.value = over1DynamicRows.value.filter((r) => r.rowId !== rowId)
    debouncedSave(ITEM_OVER1_ROWS, { remark: JSON.stringify(over1DynamicRows.value) })
  }

  function persistTop5Summary(val: string) {
    if (isReadonly.value) return
    top5SummaryOverride.value = val
    debouncedSave(ITEM_TOP5_SUMMARY, { remark: val })
  }

  function getSyncSnapshot(): F1ListedSyncSnapshot {
    return {
      agingRows: agingRows.value.map((r) => ({
        label: r.label,
        endAmount: r.endAmount,
        endPct: r.endPct,
        priorAmount: r.priorAmount,
        priorPct: r.priorPct,
      })),
      agingTotal: {
        label: agingTotal.value.label,
        endAmount: agingTotal.value.endAmount,
        endPct: agingTotal.value.endPct,
        priorAmount: agingTotal.value.priorAmount,
        priorPct: agingTotal.value.priorPct,
      },
      impairmentProvision: impairmentProvision.value,
      agingNet: {
        label: '合计',
        endAmount: agingNet.value.endAmount,
        priorAmount: agingNet.value.priorAmount,
      },
      over1YearRows: over1YearRows.value.map((r) => ({
        debtorName: r.debtorName,
        endBalance: r.endBalance,
        proportionPct: r.proportionPct,
        impairment: r.impairment,
        reason: r.reason,
      })),
      over1YearTotal: over1YearTotal.value,
      top5Rows: top5Rows.value.map((r) => ({
        entityName: r.entityName,
        endBalance: r.endBalance,
        proportionPct: r.proportionPct,
      })),
      top5Total: top5Total.value,
      top5SummaryText: top5SummaryText.value,
      noteAging: note1.value,
      noteOver1Year: note2.value,
      noteTop5: note3.value,
    }
  }

  onBeforeUnmount(() => {
    for (const { event, handler } of eventListeners) {
      window.removeEventListener(event, handler)
    }
  })

  return {
    isApplicable,
    agingRows,
    agingTotal,
    agingNet,
    /** 兼容旧模板解构名（重构前 D3 风格 section1Rows） */
    section1Rows: agingRows,
    section1Subtotal: agingTotal,
    impairmentProvision,
    persistImpairment,
    over1YearRows,
    over1YearTotal,
    addOver1Row,
    removeOver1Row,
    updateOver1Reason,
    updateOver1Field,
    top5Rows,
    top5Total,
    top5SummaryText,
    top5SummaryAuto,
    persistTop5Summary,
    note1,
    note2,
    note3,
    getSyncSnapshot,
  }
}

export default useF1DisclosureListed
