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

/** ②表行来源（只读展示，不进附注载荷） */
export type F1SoeOver1Source = 'f1-5' | 'f1-2' | 'manual'

export interface F1SoeOver1Row {
  rowId: string
  creditorUnit: string
  debtorUnit: string
  endBalance: number
  agingLabel: string
  reason: string
  fromCrossSheet: boolean
  source: F1SoeOver1Source
}

/** F1-5「账龄1年以上的大额预付账款检查表」持久化行（`F1-lt-rows`）的取用子集 */
export interface F1LongTermSourceRow {
  customerName: string
  endBalance: number
  badDebtProvision: number
  aging: string
  reason: string
}

/** F1-2 明细派生的「超1年」行（`crossSheet.longTermRows`），F1-5 为空时的回退源 */
export interface F1CrossLongTermRow {
  customerName: string
  endAudited: number
  agingDescription: string
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
  /**
   * 被审计单位名称（render `project_context.client_name`）。
   *
   * 源 xlsx `附注披露信息(国企)` A18~A20 是 `=RIGHT($A$3,LEN($A$3)-SEARCH("：",$A$3))`
   * —— 即从底稿目录「被审计单位：XXX」截出的主体名 → ②表「债权单位」列**本就是自动带出**的，
   * 不该让审计师逐行敲。改造前该列恒空，导致校验预设 `F7-9`（soe）恒不通过。
   */
  clientName?: Ref<string>
}

const PREFIX = 'F1-note-soe-'
const ITEM_OVER1_ROWS = `${PREFIX}over1-rows`
const ITEM_OVER1_META = `${PREFIX}over1-meta`
const ITEM_AGING_BAD_DEBT = `${PREFIX}aging-bad-debt`
const ITEM_TOP5_BAD_DEBT = `${PREFIX}top5-bad-debt`
/** F1-5 长期挂款检查表持久化键（②表的权威数据源） */
const ITEM_LONG_TERM_ROWS = 'F1-lt-rows'

/** 账龄缺省描述（源模板②表本身不含账龄枚举，只是一段文字） */
const OVER1_AGING_FALLBACK = '1年以上'

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

/** F1-5 行是否有效（债务人名称非空即算一行，金额可为 0） */
function isValidLongTermRow(r: F1LongTermSourceRow): boolean {
  return String(r?.customerName ?? '').trim() !== ''
}

/**
 * 国企披露②表行集构造（纯函数，零 Vue 依赖）。
 *
 * 🔴 源模板逐格实证（`附注披露信息(国企)` R18）——②表四列**全部**指向 F1-5：
 *
 * | ②表列 | 源公式 | F1-5 列 |
 * |---|---|---|
 * | 债权单位 | `=RIGHT($A$3,…)` | —（被审计单位名） |
 * | 债务单位 | `='长期挂款检查表F1-5'!A6` | A 债务人名称 |
 * | 期末余额 | `='长期挂款检查表F1-5'!J6` | **J 审定余额** = B 期末余额 − I 计提坏账准备 |
 * | 账龄 | `='长期挂款检查表F1-5'!C6` | C 账龄 |
 * | 未结算的原因 | `='长期挂款检查表F1-5'!E6` | E 未偿还或未结转的原因 |
 *
 * 改造前本表读的是 `crossSheet.longTermRows`（由 F1-2 明细**派生**）：
 * 「期末余额」用未扣坏账的 `endAudited`、「账龄」是自动拼接串、「未结算的原因」
 * 另存一份 meta 与 F1-5 已有的 `reason` 列构成**重复录入**。
 *
 * 优先级（三层，逐字段独立）：`metaMap` 手工覆盖 > 源行值 > 缺省值。
 * F1-5 有有效行则用 F1-5，否则回退 F1-2 派生行（升级零回归）。
 */
export function buildSoeOver1Rows(input: {
  longTermSheetRows: readonly F1LongTermSourceRow[]
  crossSheetRows: readonly F1CrossLongTermRow[]
  dynamicRows: readonly F1SoeOver1Row[]
  metaMap: Readonly<Record<string, Over1Meta>>
  defaultCreditorUnit: string
}): F1SoeOver1Row[] {
  const {
    longTermSheetRows = [],
    crossSheetRows = [],
    dynamicRows = [],
    metaMap = {},
    defaultCreditorUnit = '',
  } = input
  const fallbackCreditor = String(defaultCreditorUnit ?? '').trim()
  const metaOf = (name: string): Over1Meta => metaMap[name] || {}
  const pickCreditor = (meta: Over1Meta, own?: string): string =>
    String(meta.creditorUnit ?? '').trim()
    || String(own ?? '').trim()
    || fallbackCreditor

  const ltRows = longTermSheetRows.filter(isValidLongTermRow)

  const sourced: F1SoeOver1Row[] = ltRows.length
    ? ltRows.map((r) => {
        const name = String(r.customerName).trim()
        const meta = metaOf(name)
        return {
          rowId: `lt-${name}`,
          creditorUnit: pickCreditor(meta),
          debtorUnit: name,
          // 源 J 列 = B − I（不信任持久化的 auditedBalance，按定义现算）
          endBalance: parseNum(r.endBalance) - parseNum(r.badDebtProvision),
          agingLabel:
            String(meta.agingLabel ?? '').trim()
            || String(r.aging ?? '').trim()
            || OVER1_AGING_FALLBACK,
          reason:
            String(meta.reason ?? '').trim() || String(r.reason ?? '').trim(),
          fromCrossSheet: true,
          source: 'f1-5' as const,
        }
      })
    : crossSheetRows.map((r) => {
        const name = String(r.customerName ?? '').trim()
        const meta = metaOf(name)
        return {
          rowId: `cs-lt-${name}`,
          creditorUnit: pickCreditor(meta),
          debtorUnit: name,
          endBalance: parseNum(r.endAudited),
          agingLabel:
            String(meta.agingLabel ?? '').trim()
            || String(r.agingDescription ?? '').trim()
            || OVER1_AGING_FALLBACK,
          reason: String(meta.reason ?? '').trim(),
          fromCrossSheet: true,
          source: 'f1-2' as const,
        }
      })

  const manual: F1SoeOver1Row[] = dynamicRows.map((r) => ({
    ...r,
    creditorUnit: pickCreditor({}, r.creditorUnit),
    fromCrossSheet: false,
    source: 'manual' as const,
  }))

  return [...sourced, ...manual]
}

export function useF1DisclosureSoe(options: UseF1DisclosureSoeOptions) {
  const {
    allResponses, debouncedSave, crossSheet, isReadonly, applicableStandards,
    impairmentPrefill, clientName,
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
        source: 'manual' as const,
      }))
    },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(ITEM_OVER1_META)?.remark,
    (json) => { over1MetaMap.value = safeParseJson(json, {}) },
    { immediate: true },
  )

  /** F1-5 持久化行（②表权威数据源；只读，披露表永不回写 F1-5） */
  const longTermSheetRows: ComputedRef<F1LongTermSourceRow[]> = computed(() => {
    const raw = safeParseJson<Array<Record<string, unknown>>>(
      allResponses.value.get(ITEM_LONG_TERM_ROWS)?.remark,
      [],
    )
    if (!Array.isArray(raw)) return []
    return raw.map((r) => ({
      customerName: String((r as any)?.customerName ?? ''),
      endBalance: parseNum((r as any)?.endBalance),
      badDebtProvision: parseNum((r as any)?.badDebtProvision),
      aging: String((r as any)?.aging ?? ''),
      reason: String((r as any)?.reason ?? (r as any)?.unsettledReason ?? ''),
    }))
  })

  /** ②表是否已由 F1-5 驱动（UI 用于提示口径来源） */
  const over1FromLongTermSheet: ComputedRef<boolean> = computed(
    () => longTermSheetRows.value.some(isValidLongTermRow),
  )

  const over1YearRows: ComputedRef<F1SoeOver1Row[]> = computed(() =>
    buildSoeOver1Rows({
      longTermSheetRows: longTermSheetRows.value,
      crossSheetRows: crossSheet.longTermRows?.value ?? [],
      dynamicRows: over1DynamicRows.value,
      metaMap: over1MetaMap.value,
      defaultCreditorUnit: clientName?.value ?? '',
    }),
  )

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
        source: 'manual',
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
    over1FromLongTermSheet,
    longTermSheetRows,
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
