/**
 * useF1DisclosureSoe — 预付账款附注披露（国企）
 * 对齐 Excel：账龄列示(账面+坏账) / 超1年大额 / 前五名 + 同步附注八、7
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, calcPercentage } from './useF1FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import type { useF1CrossSheet } from './useF1CrossSheet'
import { computeTop5 } from './useF1Analysis'
import { buildAgingDisclosureRows } from './useF1DisclosureListed'
import { isF1DisclosureApplicable } from './f1NoteSectionMap'
import type { F1SoeSyncSnapshot } from './f1DisclosureSyncPayload'
import { PRESET_SEGMENTS } from '@/composables/useAgingConfig'
import { ADJUDICATION_LABEL_BY_SEGMENT_KEY } from './agingPresets'
import { lookupDisclosureAgingLabel, SOE_AGING_OVERRIDES } from './disclosureAgingLabels'

export interface F1SoeAgingRow {
  rowId: string
  key: string
  label: string
  endAmount: number
  endPct: number
  endBadDebt: number
  priorAmount: number
  priorPct: number
  priorBadDebt: number
}

export interface F1SoeOver1Row {
  rowId: string
  creditorUnit: string
  debtorUnit: string
  endBalance: number
  agingLabel: string
  reason: string
  fromCrossSheet: boolean
}

export interface F1SoeTop5Row {
  rowId: string
  debtorName: string
  endBalance: number
  proportionPct: number
  badDebt: number
}

export interface UseF1DisclosureSoeOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useF1CrossSheet>
  isReadonly: Ref<boolean>
  applicableStandards: Ref<string[]>
  /**
   * 四表库减值准备（render `impairment_prefill`）；`null` = 四表库无
   * 「坏账准备-预付账款」科目。
   *
   * 🔴 国企侧减值准备是**逐账龄段**列，而四表库无账龄维度 → **不按段编造分摊**
   * （宁缺勿造）。此处只做两件事：① 溯源展示；② 勾稽「逐段合计 vs 四表库期末」。
   */
  impairmentPrefill?: Ref<{ end: number; prior: number } | null>
}

const PREFIX = 'F1-note-soe-'
const ITEM_OVER1_ROWS = `${PREFIX}over1-rows`
const ITEM_OVER1_META = `${PREFIX}over1-meta`
const ITEM_AGING_BAD_DEBT = `${PREFIX}aging-bad-debt`
const ITEM_TOP5_BAD_DEBT = `${PREFIX}top5-bad-debt`

/** 国企首档带「（含1年）」；其余档位取共享表（per-section 覆盖范式）。 */
const F1_SOE_AGING_OVERRIDES: Readonly<Record<string, string>> = SOE_AGING_OVERRIDES

type BadDebtPair = { end: number; prior: number }
type Over1Meta = { creditorUnit?: string; reason?: string; agingLabel?: string }

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

export function useF1DisclosureSoe(options: UseF1DisclosureSoeOptions) {
  const {
    allResponses, debouncedSave, crossSheet, isReadonly, applicableStandards,
    impairmentPrefill,
  } = options
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  /** 四表库「坏账准备-预付账款」期末/期初（只读，供溯源与勾稽；不参与录入） */
  const fourTableImpairment: ComputedRef<{ end: number; prior: number } | null> = computed(
    () => impairmentPrefill?.value ?? null,
  )

  const isApplicable: ComputedRef<boolean> = computed(() =>
    isF1DisclosureApplicable('soe', applicableStandards.value),
  )

  // ─── (1) 账龄列示 ───────────────────────────────────────────────────

  const agingBadDebtMap = ref<Record<string, BadDebtPair>>({})
  watch(
    () => allResponses.value.get(ITEM_AGING_BAD_DEBT)?.remark,
    (json) => { agingBadDebtMap.value = safeParseJson(json, {}) },
    { immediate: true },
  )

  const agingRows: ComputedRef<F1SoeAgingRow[]> = computed(() => {
    const agg = crossSheet.agingAggregation?.value ?? {}
    const segs = crossSheet.agingSegments?.value?.length
      ? crossSheet.agingSegments.value
      : PRESET_SEGMENTS.THREE_YEAR
    const buckets = buildAgingDisclosureRows(agg, segs)
    const endTotal = calcSubtotal(buckets.map((b) => b.endAmount))
    const priorTotal = calcSubtotal(buckets.map((b) => b.priorAmount))
    return buckets.map((b) => {
      const bd = agingBadDebtMap.value[b.key] || { end: 0, prior: 0 }
      return {
        rowId: `aging-${b.key}`,
        key: b.key,
        label: lookupDisclosureAgingLabel(b.key, F1_SOE_AGING_OVERRIDES)
          || ADJUDICATION_LABEL_BY_SEGMENT_KEY[b.key]
          || b.label,
        endAmount: b.endAmount,
        endPct: calcPercentage(b.endAmount, endTotal),
        endBadDebt: parseNum(bd.end),
        priorAmount: b.priorAmount,
        priorPct: calcPercentage(b.priorAmount, priorTotal),
        priorBadDebt: parseNum(bd.prior),
      }
    })
  })

  const agingTotal: ComputedRef<F1SoeAgingRow> = computed(() => {
    const endAmount = calcSubtotal(agingRows.value.map((r) => r.endAmount))
    const priorAmount = calcSubtotal(agingRows.value.map((r) => r.priorAmount))
    return {
      rowId: '__subtotal__',
      key: 'subtotal',
      label: '小计',
      endAmount,
      endPct: endAmount ? 100 : 0,
      endBadDebt: calcSubtotal(agingRows.value.map((r) => r.endBadDebt)),
      priorAmount,
      priorPct: priorAmount ? 100 : 0,
      priorBadDebt: calcSubtotal(agingRows.value.map((r) => r.priorBadDebt)),
    }
  })

  /**
   * 「减：减值准备」行：取逐账龄段减值准备列合计（只读派生）。
   * 源 xlsx 国企 sheet 把减值准备做成逐段列，附注模版/F7-7 做成一行 →
   * 底稿保留逐段列作审计明细，此行为投影到附注的聚合口径。
   */
  const agingImpairmentRow = computed(() => ({
    rowId: '__impairment__',
    label: '减：减值准备',
    endAmount: agingTotal.value.endBadDebt,
    priorAmount: agingTotal.value.priorBadDebt,
  }))

  /** 「合计」行 = 小计 − 减：减值准备（期末/期初各独立，F7-7） */
  const agingNet = computed(() => ({
    rowId: '__net__',
    label: '合计',
    endAmount: agingTotal.value.endAmount - agingTotal.value.endBadDebt,
    priorAmount: agingTotal.value.priorAmount - agingTotal.value.priorBadDebt,
  }))

  function updateAgingBadDebt(key: string, field: 'end' | 'prior', val: number) {
    if (isReadonly.value) return
    const prev = agingBadDebtMap.value[key] || { end: 0, prior: 0 }
    agingBadDebtMap.value = {
      ...agingBadDebtMap.value,
      [key]: { ...prev, [field]: parseNum(val) },
    }
    debouncedSave(ITEM_AGING_BAD_DEBT, { remark: JSON.stringify(agingBadDebtMap.value) })
  }

  // ─── (2) 超1年大额 ─────────────────────────────────────────────────

  const over1DynamicRows = ref<F1SoeOver1Row[]>([])
  const over1MetaMap = ref<Record<string, Over1Meta>>({})

  watch(
    () => allResponses.value.get(ITEM_OVER1_ROWS)?.remark,
    (json) => {
      const rows = safeParseJson<Partial<F1SoeOver1Row>[]>(json, [])
      over1DynamicRows.value = rows.map((r) => ({
        rowId: r.rowId || generateRowId(),
        creditorUnit: r.creditorUnit || '',
        debtorUnit: r.debtorUnit || '',
        endBalance: parseNum(r.endBalance),
        agingLabel: r.agingLabel || '',
        reason: r.reason || '',
        fromCrossSheet: false,
      }))
    },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(ITEM_OVER1_META)?.remark,
    (json) => { over1MetaMap.value = safeParseJson(json, {}) },
    { immediate: true },
  )

  const over1YearRows: ComputedRef<F1SoeOver1Row[]> = computed(() => {
    const ltRows = crossSheet.longTermRows?.value ?? []
    const cs = ltRows.map((r) => {
      const name = r.customerName || ''
      const meta = over1MetaMap.value[name] || {}
      return {
        rowId: `cs-lt-${name}`,
        creditorUnit: meta.creditorUnit || '',
        debtorUnit: name,
        endBalance: parseNum(r.endAudited),
        agingLabel: meta.agingLabel || r.agingDescription || '1年以上',
        reason: meta.reason || '',
        fromCrossSheet: true,
      }
    })
    return [...cs, ...over1DynamicRows.value]
  })

  const over1YearTotal = computed(() => ({
    endBalance: calcSubtotal(over1YearRows.value.map((r) => r.endBalance)),
  }))

  function persistOver1Dynamic() {
    debouncedSave(ITEM_OVER1_ROWS, { remark: JSON.stringify(over1DynamicRows.value) })
  }

  function persistOver1Meta() {
    debouncedSave(ITEM_OVER1_META, { remark: JSON.stringify(over1MetaMap.value) })
  }

  function updateOver1Field(
    rowId: string,
    field: 'creditorUnit' | 'debtorUnit' | 'endBalance' | 'agingLabel' | 'reason',
    value: string | number,
  ) {
    if (isReadonly.value) return
    const row = over1YearRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    if (row.fromCrossSheet) {
      const name = row.debtorUnit
      const meta = { ...(over1MetaMap.value[name] || {}) }
      if (field === 'creditorUnit') meta.creditorUnit = String(value)
      else if (field === 'agingLabel') meta.agingLabel = String(value)
      else if (field === 'reason') meta.reason = String(value)
      over1MetaMap.value = { ...over1MetaMap.value, [name]: meta }
      persistOver1Meta()
      return
    }
    over1DynamicRows.value = over1DynamicRows.value.map((r) => {
      if (r.rowId !== rowId) return r
      if (field === 'endBalance') return { ...r, endBalance: parseNum(value) }
      return { ...r, [field]: String(value) }
    })
    persistOver1Dynamic()
  }

  function addOver1Row() {
    if (isReadonly.value) return
    over1DynamicRows.value = [
      ...over1DynamicRows.value,
      {
        rowId: generateRowId(),
        creditorUnit: '',
        debtorUnit: '',
        endBalance: 0,
        agingLabel: '',
        reason: '',
        fromCrossSheet: false,
      },
    ]
    persistOver1Dynamic()
  }

  function removeOver1Row(rowId: string) {
    if (isReadonly.value) return
    over1DynamicRows.value = over1DynamicRows.value.filter((r) => r.rowId !== rowId)
    persistOver1Dynamic()
  }

  // ─── (3) 前五名 ────────────────────────────────────────────────────

  const top5BadDebtMap = ref<Record<string, number>>({})
  watch(
    () => allResponses.value.get(ITEM_TOP5_BAD_DEBT)?.remark,
    (json) => { top5BadDebtMap.value = safeParseJson(json, {}) },
    { immediate: true },
  )

  const top5Rows: ComputedRef<F1SoeTop5Row[]> = computed(() => {
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
      debtorName: r.customerName,
      endBalance: r.endAudited,
      proportionPct: calcPercentage(r.endAudited, total),
      badDebt: parseNum(top5BadDebtMap.value[r.customerName]),
    }))
  })

  const top5Total = computed(() => {
    const endBalance = calcSubtotal(top5Rows.value.map((r) => r.endBalance))
    return {
      endBalance,
      proportionPct: calcPercentage(endBalance, agingTotal.value.endAmount || endBalance),
      badDebt: calcSubtotal(top5Rows.value.map((r) => r.badDebt)),
    }
  })

  function updateTop5BadDebt(debtorName: string, val: number) {
    if (isReadonly.value) return
    top5BadDebtMap.value = { ...top5BadDebtMap.value, [debtorName]: parseNum(val) }
    debouncedSave(ITEM_TOP5_BAD_DEBT, { remark: JSON.stringify(top5BadDebtMap.value) })
  }

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
        // 预付款项 soe → 八、7（note_template_variant_matrix）
        detail: { wpCode: 'F1', accountCode: '1123', section: 'soe-3', sectionIds: ['八、7'], text: val },
      }))
    } catch { /* silent */ }
  })

  const noteUpdateHandler = (e: Event) => {
    const detail = (e as CustomEvent).detail
    if (detail?.wpCode === 'F1' && detail?.section?.startsWith('soe-')) {
      const idx = detail.section.replace('soe-', '')
      if (idx === '1') note1.value = detail.text || ''
      else if (idx === '2') note2.value = detail.text || ''
      else if (idx === '3') note3.value = detail.text || ''
    }
  }
  window.addEventListener('note:section-updated', noteUpdateHandler)
  eventListeners.push({ event: 'note:section-updated', handler: noteUpdateHandler })

  function getSyncSnapshot(): F1SoeSyncSnapshot {
    return {
      agingRows: agingRows.value.map((r) => ({
        label: r.label,
        endAmount: r.endAmount,
        endPct: r.endPct,
        endBadDebt: r.endBadDebt,
        priorAmount: r.priorAmount,
        priorPct: r.priorPct,
        priorBadDebt: r.priorBadDebt,
      })),
      agingTotal: {
        label: agingTotal.value.label,
        endAmount: agingTotal.value.endAmount,
        endPct: agingTotal.value.endPct,
        endBadDebt: agingTotal.value.endBadDebt,
        priorAmount: agingTotal.value.priorAmount,
        priorPct: agingTotal.value.priorPct,
        priorBadDebt: agingTotal.value.priorBadDebt,
      },
      agingNet: {
        label: agingNet.value.label,
        endAmount: agingNet.value.endAmount,
        priorAmount: agingNet.value.priorAmount,
      },
      over1YearRows: over1YearRows.value.map((r) => ({
        creditorUnit: r.creditorUnit,
        debtorUnit: r.debtorUnit,
        endBalance: r.endBalance,
        agingLabel: r.agingLabel,
        reason: r.reason,
      })),
      over1YearTotal: over1YearTotal.value,
      top5Rows: top5Rows.value.map((r) => ({
        debtorName: r.debtorName,
        endBalance: r.endBalance,
        proportionPct: r.proportionPct,
        badDebt: r.badDebt,
      })),
      top5Total: top5Total.value,
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
    agingImpairmentRow,
    agingNet,
    /** 兼容旧模板解构名（重构前 D3 风格 section1Rows） */
    section1Rows: agingRows,
    section1Subtotal: agingTotal,
    fourTableImpairment,
    updateAgingBadDebt,
    over1YearRows,
    over1YearTotal,
    addOver1Row,
    removeOver1Row,
    updateOver1Field,
    top5Rows,
    top5Total,
    updateTop5BadDebt,
    note1,
    note2,
    note3,
    getSyncSnapshot,
  }
}

export default useF1DisclosureSoe
