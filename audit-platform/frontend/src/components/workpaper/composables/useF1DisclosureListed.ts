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
import type { F1ListedSyncSnapshot, F1Top5Mode } from './f1DisclosureSyncPayload'
import { F1_TOP5_MODE_DEFAULT, normalizeF1Top5Mode } from './f1DisclosureSyncPayload'
import { ADJUDICATION_LABEL_BY_SEGMENT_KEY } from './agingPresets'
import { lookupDisclosureAgingLabel } from './disclosureAgingLabels'

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
  /**
   * 四表库减值准备预填（render `impairment_prefill`）；`null` = 四表库无
   * 「坏账准备-预付账款」科目 → 保持手工录入（宁缺勿造）。**手工值优先**。
   */
  impairmentPrefill?: Ref<{ end: number; prior: number } | null>
}

const PREFIX = 'F1-note-listed-'
const ITEM_OVER1_ROWS = `${PREFIX}over1-rows`
const ITEM_OVER1_REASON_MAP = `${PREFIX}over1-reasons`
/** 跨 sheet 带入行（F1-5 长期挂款）的减值准备，按债务人名称键 */
const ITEM_OVER1_IMPAIRMENT_MAP = `${PREFIX}over1-impairments`
const ITEM_IMPAIRMENT = `${PREFIX}impairment-provision`
/** 上年年末减值准备（F7-7 要求期末/上年年末各独立校验） */
const ITEM_IMPAIRMENT_PRIOR = `${PREFIX}impairment-provision-prior`
const ITEM_TOP5_SUMMARY = `${PREFIX}top5-summary`
/** ③前五名披露格式（源模板「汇总或分别披露」二选一） */
const ITEM_TOP5_MODE = `${PREFIX}top5-mode`


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
 * 附注披露口径标签；缺省时回退审定表口径 / segment.label。
 * 映射表已收敛到共享模块 `disclosureAgingLabels`（原 per-cycle `NOTE_AGING_LABEL`
 * 与共享表逐项同值），避免同一口径两处维护。
 */
function disclosureAgingLabel(seg: AgingSegment): string {
  return lookupDisclosureAgingLabel(seg.key)
    || ADJUDICATION_LABEL_BY_SEGMENT_KEY[seg.key]
    || seg.label
}

/**
 * 按项目账龄枚举段生成附注账龄行（3年段/5年段/自定义，不再强制折四档）
 */
export function buildAgingDisclosureRows(
  agingAgg: Record<string, number> | null | undefined,
  segments: AgingSegment[] = PRESET_SEGMENTS.THREE_YEAR,
): Array<{ key: string; label: string; endAmount: number; priorAmount: number }> {
  const src = agingAgg ?? {}
  const segs = segments.length ? segments : PRESET_SEGMENTS.THREE_YEAR
  return segs.map((seg) => ({
    key: seg.key,
    label: disclosureAgingLabel(seg),
    endAmount: parseNum(src[seg.key]),
    priorAmount: parseNum(src[`prior_${seg.key}`]),
  }))
}

/** @deprecated 使用 buildAgingDisclosureRows；保留别名兼容旧测试名 */
export function collapseAgingForListedDisclosure(
  agingAgg: Record<string, number> | null | undefined,
  segments: AgingSegment[] = PRESET_SEGMENTS.THREE_YEAR,
): Array<{ key: string; label: string; endAmount: number; priorAmount: number }> {
  return buildAgingDisclosureRows(agingAgg, segments)
}

export function useF1DisclosureListed(options: UseF1DisclosureListedOptions) {
  const {
    allResponses, debouncedSave, crossSheet, isReadonly, applicableStandards,
    impairmentPrefill,
  } = options
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  const isApplicable: ComputedRef<boolean> = computed(() =>
    isF1DisclosureApplicable('listed', applicableStandards.value),
  )

  // ─── (1) 账龄分析 ───────────────────────────────────────────────────

  /** 是否存在手工录入（键存在且非空串；`0` 视为有效手工值） */
  function hasManual(itemId: string): boolean {
    const raw = allResponses.value.get(itemId)?.remark
    return raw !== undefined && raw !== null && String(raw).trim() !== ''
  }

  // 减值准备：手工优先，无持久化时用四表库预填（坏账准备-预付账款 1231-04）
  const impairmentProvision = ref(0)
  watch(
    [
      () => allResponses.value.get(ITEM_IMPAIRMENT)?.remark,
      () => impairmentPrefill?.value?.end ?? null,
    ],
    ([v, seed]) => {
      impairmentProvision.value = hasManual(ITEM_IMPAIRMENT) ? parseNum(v) : parseNum(seed)
    },
    { immediate: true },
  )

  const impairmentPrior = ref(0)
  watch(
    [
      () => allResponses.value.get(ITEM_IMPAIRMENT_PRIOR)?.remark,
      () => impairmentPrefill?.value?.prior ?? null,
    ],
    ([v, seed]) => {
      impairmentPrior.value = hasManual(ITEM_IMPAIRMENT_PRIOR) ? parseNum(v) : parseNum(seed)
    },
    { immediate: true },
  )

  const agingRows: ComputedRef<F1AgingDisclosureRow[]> = computed(() => {
    const agg = crossSheet.agingAggregation?.value ?? {}
    const segs = crossSheet.agingSegments?.value?.length
      ? crossSheet.agingSegments.value
      : PRESET_SEGMENTS.THREE_YEAR
    const buckets = buildAgingDisclosureRows(agg, segs)
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
      key: 'subtotal',
      label: '小计',
      endAmount,
      endPct: endAmount ? 100 : 0,
      priorAmount,
      priorPct: priorAmount ? 100 : 0,
    }
  })

  /** 「减：减值准备」行（表内行，非表外控件；源模版/F7-7 口径） */
  const agingImpairmentRow = computed(() => ({
    rowId: '__impairment__',
    label: '减：减值准备',
    endAmount: impairmentProvision.value,
    priorAmount: impairmentPrior.value,
  }))

  /** 「合计」行 = 小计 − 减：减值准备（期末/上年年末各独立） */
  const agingNet = computed(() => ({
    rowId: '__net__',
    label: '合计',
    endAmount: agingTotal.value.endAmount - impairmentProvision.value,
    priorAmount: agingTotal.value.priorAmount - impairmentPrior.value,
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

  const over1ImpairmentMap = ref<Record<string, number>>({})
  watch(
    () => allResponses.value.get(ITEM_OVER1_IMPAIRMENT_MAP)?.remark,
    (json) => { over1ImpairmentMap.value = safeParseJson(json, {}) },
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
        impairment: parseNum(over1ImpairmentMap.value[name]),
        // 只用人工录入的「未及时结算的原因」；不再回退 agingDescription（账龄不是原因）
        reason: over1ReasonMap.value[name] || '',
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

  /**
   * ③前五名披露格式（源模板 A23「汇总**或**分别披露」→ 二选一）。
   * 默认「分别披露格式」= 与改造前推③表的行为一致（升级零回归）。
   * 切换只改推送口径，两种格式的录入数据各自保留（切回即复原）。
   */
  const top5Mode = ref<F1Top5Mode>(F1_TOP5_MODE_DEFAULT)
  watch(
    () => allResponses.value.get(ITEM_TOP5_MODE)?.remark,
    (v) => { top5Mode.value = normalizeF1Top5Mode(v) },
    { immediate: true },
  )

  function setTop5Mode(mode: F1Top5Mode) {
    if (isReadonly.value) return
    const next = normalizeF1Top5Mode(mode)
    if (next === top5Mode.value) return
    top5Mode.value = next
    debouncedSave(ITEM_TOP5_MODE, { remark: next })
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
        // sectionIds=附注章节号（权威 note_template_variant_matrix：预付款项 listed 五、7）
        // → useNoteRefresh 定向刷新当前查看的附注节
        detail: { wpCode: 'F1', accountCode: '1123', section: 'listed-3', sectionIds: ['五、7'], text: val },
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

  function persistImpairmentPrior(val: number) {
    if (isReadonly.value) return
    impairmentPrior.value = parseNum(val)
    debouncedSave(ITEM_IMPAIRMENT_PRIOR, { remark: String(impairmentPrior.value) })
  }

  /**
   * 把各债务人「未及时结算原因」汇编进 (2) 的说明文本框。
   * 上市版源模板 ② 表无「未结算的原因」列（F7-9 listed），原因以说明段落披露。
   */
  function composeOver1Note(): string {
    const parts = over1YearRows.value
      .filter((r) => r.debtorName && r.reason)
      .map((r) => `${r.debtorName}：${r.reason}`)
    if (!parts.length) return ''
    return `账龄超过1年的重要预付款项未及时结算的原因：${parts.join('；')}。`
  }

  function applyComposedOver1Note(): boolean {
    if (isReadonly.value) return false
    const text = composeOver1Note()
    if (!text) return false
    note2.value = text
    return true
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
    if (!row) return
    if (row.fromCrossSheet) {
      // 跨 sheet 行的名称/余额来自 F1-5，只允许补录减值准备（按债务人名称键持久化）
      if (field !== 'impairment') return
      over1ImpairmentMap.value = {
        ...over1ImpairmentMap.value,
        [row.debtorName]: parseNum(value),
      }
      debouncedSave(ITEM_OVER1_IMPAIRMENT_MAP, { remark: JSON.stringify(over1ImpairmentMap.value) })
      return
    }
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
      impairmentPrior: impairmentPrior.value,
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
      top5Mode: top5Mode.value,
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
    impairmentProvision,
    impairmentPrior,
    persistImpairment,
    persistImpairmentPrior,
    composeOver1Note,
    applyComposedOver1Note,
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
    top5Mode,
    setTop5Mode,
    note1,
    note2,
    note3,
    getSyncSnapshot,
  }
}

export default useF1DisclosureListed
