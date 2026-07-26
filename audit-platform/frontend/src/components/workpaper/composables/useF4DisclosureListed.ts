/**
 * useF4DisclosureListed — F4 附注披露信息（上市公司）
 *
 * 对齐源表两个区块：
 * 1. 按性质披露期末余额/上年年末余额：固定项目联动审定表F4-1
 *    （期末=F4-1期末审定数、上年年末=F4-1期初审定数），支持无限量添加手工行；
 * 2. 账龄超过1年的重要应付账款：联动长期挂账检查表F4-5
 *    （债权人/期末余额/未偿还或未结转的原因），支持同步与手工行。
 */
import { computed, onBeforeUnmount, ref, watch, type ComputedRef, type Ref } from 'vue'
import { parseNum, calcSubtotal, calcOutstandingDays } from './useF4AccPayFormulaEngine'
import {
  aggregateF4Detail,
  computeF4AdjudicationRow,
  migrateF4AdjRows,
  F4_NATURE_DEFAULTS,
} from './useF4Adjudication'
import type { ChecklistResponse } from './useF4FormData'
import { PRESET_SEGMENTS, type AgingSegment } from '@/composables/useAgingConfig'
import { f4AgingLabel } from './f4AgingModel'

export interface UseF4DisclosureListedOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export interface F4DisclosureNatureRow {
  rowId: string
  /** F4-1 按性质 rowKey；空字符串表示手工行 */
  sourceKey: string
  label: string
  closingBalance: number
  priorBalance: number
  linked: boolean
}

export interface F4DisclosureAgingRow {
  rowId: string
  /** F4-5 行 rowId；空字符串表示手工行 */
  sourceRowId: string
  creditor: string
  amount: number
  reason: string
  linked: boolean
}

interface StoredNatureRow {
  rowId: string
  sourceKey: string
  label: string
  closingBalance: number
  priorBalance: number
}

interface StoredAgingRow {
  rowId: string
  sourceRowId: string
  creditor: string
  amount: number
  reason: string
}

const NATURE_ROWS_KEY = 'F4-disclosure-listed-nature-rows'
const AGING_ROWS_KEY = 'F4-disclosure-listed-aging-rows'
const TEXT_KEY = 'F4-disclosure-listed'
const ADJ_NATURE_KEY = 'F4-1-adj-nature-rows'
const DETAIL_KEY = 'F4-2-rows'
const LONG_OUTSTANDING_KEY = 'F4-5-rows'
const OVER_ONE_YEAR_DAYS = 365
const TOLERANCE = 0.005

function generateRowId(): string {
  return `f4dl-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function safeJsonArray(value: string | null | undefined): any[] {
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function defaultNatureRows(): StoredNatureRow[] {
  return F4_NATURE_DEFAULTS.map((row) => ({
    rowId: `f4dl-nature-${row.rowKey}`,
    sourceKey: row.rowKey,
    label: row.label,
    closingBalance: 0,
    priorBalance: 0,
  }))
}

function parseNatureRows(value: string | null | undefined): StoredNatureRow[] {
  const parsed = safeJsonArray(value)
  if (!parsed.length) return defaultNatureRows()
  return parsed.map((raw: any, index) => ({
    rowId: String(raw?.rowId || generateRowId()),
    sourceKey: String(raw?.sourceKey ?? ''),
    label: String(raw?.label ?? `项目${index + 1}`),
    closingBalance: parseNum(raw?.closingBalance),
    priorBalance: parseNum(raw?.priorBalance),
  }))
}

function parseAgingRows(value: string | null | undefined): StoredAgingRow[] {
  return safeJsonArray(value).map((raw: any) => ({
    rowId: String(raw?.rowId || generateRowId()),
    sourceRowId: String(raw?.sourceRowId ?? ''),
    creditor: String(raw?.creditor ?? ''),
    amount: parseNum(raw?.amount),
    reason: String(raw?.reason ?? ''),
  }))
}

/**
 * F4-5 中账龄超过1年的行（含实时计算的挂账天数）。
 * 账龄文本 → 天数推定按**生效段** label/dayFrom 派生（兼容迁移前固定 3 档文案）。
 */
export function extractOverOneYearRows(
  value: string | null | undefined,
  segments?: readonly AgingSegment[],
): Array<{
  rowId: string
  creditor: string
  amount: number
  reason: string
  outstandingDays: number
}> {
  const segs = (segments?.length ? segments : PRESET_SEGMENTS.THREE_YEAR) as AgingSegment[]
  const longSegs = segs.filter((seg) => Number(seg.dayFrom) >= 366)
  return safeJsonArray(value)
    .map((raw: any) => {
      let outstandingDays = 0
      const startDate = String(raw?.startDate ?? '')
      if (startDate) {
        const start = new Date(startDate)
        if (!Number.isNaN(start.getTime())) {
          outstandingDays = calcOutstandingDays(new Date(), start)
        }
      }
      // F4-5新源表直接记录账龄而非挂账起始日；保留推定天数仅用于兼容既有接口。
      const aging = String(raw?.aging ?? '')
      if (!outstandingDays && aging) {
        // 段驱动：命中的超 1 年段中取 dayFrom 最大者
        let best = 0
        for (const seg of longSegs) {
          const label = f4AgingLabel(seg)
          if (label && aging.includes(label)) best = Math.max(best, Number(seg.dayFrom) || 0)
          else if (seg.label && aging.includes(seg.label)) best = Math.max(best, Number(seg.dayFrom) || 0)
        }
        // 兼容迁移前固定 4 档文案（1～2年/2～3年/3年以上）
        if (!best) {
          if (aging.includes('3年以上')) best = 1096
          else if (aging.includes('2～3年')) best = 731
          else if (aging.includes('1～2年')) best = 366
        }
        outstandingDays = best
      }
      return {
        rowId: String(raw?.rowId ?? ''),
        creditor: String(raw?.creditor ?? ''),
        amount: parseNum(raw?.auditedAmount ?? raw?.closingBalance ?? raw?.amount),
        reason: String(raw?.unsettledReason ?? raw?.reason ?? raw?.hangReason ?? ''),
        outstandingDays,
      }
    })
    .filter((row) => (row.creditor || row.amount) && row.outstandingDays > OVER_ONE_YEAR_DAYS)
}

export function useF4DisclosureListed(options: UseF4DisclosureListedOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const natureStored = ref<StoredNatureRow[]>([])
  const agingStored = ref<StoredAgingRow[]>([])
  const disclosureText = ref('')

  function loadRows(): void {
    natureStored.value = parseNatureRows(allResponses.value.get(NATURE_ROWS_KEY)?.remark)
    agingStored.value = parseAgingRows(allResponses.value.get(AGING_ROWS_KEY)?.remark)
  }

  watch(
    () => [
      allResponses.value.get(NATURE_ROWS_KEY)?.remark,
      allResponses.value.get(AGING_ROWS_KEY)?.remark,
    ],
    () => {
      if (!natureStored.value.length) loadRows()
    },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(TEXT_KEY)?.remark,
    (value) => { disclosureText.value = value || '' },
    { immediate: true },
  )

  // ─── F4-1 审定数联动（期末=期末审定、上年年末=期初审定） ─────────────────
  const adjudicationByKey = computed(() => {
    const detail = aggregateF4Detail(allResponses.value.get(DETAIL_KEY)?.remark)
    const rows = migrateF4AdjRows(allResponses.value.get(ADJ_NATURE_KEY)?.remark, F4_NATURE_DEFAULTS)
    return new Map(rows.map((stored) => [
      stored.rowKey,
      computeF4AdjudicationRow(stored, detail.hasData ? detail.nature[stored.rowKey] : undefined),
    ]))
  })

  const natureRows: ComputedRef<F4DisclosureNatureRow[]> = computed(() =>
    natureStored.value.map((stored) => {
      const linked = adjudicationByKey.value.get(stored.sourceKey)
      return {
        ...stored,
        closingBalance: linked ? linked.closingAdjusted : stored.closingBalance,
        priorBalance: linked ? linked.openingAdjusted : stored.priorBalance,
        linked: !!linked,
      }
    }),
  )

  const natureClosingTotal = computed(() => calcSubtotal(natureRows.value.map((row) => row.closingBalance)))
  const naturePriorTotal = computed(() => calcSubtotal(natureRows.value.map((row) => row.priorBalance)))

  const adjClosingTotal = computed(() =>
    calcSubtotal([...adjudicationByKey.value.values()].map((row) => row.closingAdjusted)),
  )
  const adjPriorTotal = computed(() =>
    calcSubtotal([...adjudicationByKey.value.values()].map((row) => row.openingAdjusted)),
  )
  const closingMatchesAdjudication = computed(() =>
    Math.abs(natureClosingTotal.value - adjClosingTotal.value) < TOLERANCE,
  )
  const priorMatchesAdjudication = computed(() =>
    Math.abs(naturePriorTotal.value - adjPriorTotal.value) < TOLERANCE,
  )

  // ─── F4-5 长期挂账联动 ────────────────────────────────────────────────────
  const overOneYearSource = computed(() =>
    extractOverOneYearRows(allResponses.value.get(LONG_OUTSTANDING_KEY)?.remark),
  )

  const agingRows: ComputedRef<F4DisclosureAgingRow[]> = computed(() =>
    agingStored.value.map((stored) => {
      const source = stored.sourceRowId
        ? overOneYearSource.value.find((row) => row.rowId === stored.sourceRowId)
        : undefined
      return {
        ...stored,
        creditor: source ? source.creditor : stored.creditor,
        amount: source ? source.amount : stored.amount,
        // 披露表中补充的原因优先；未填写时默认取F4-5挂账原因
        reason: stored.reason || source?.reason || '',
        linked: !!source,
      }
    }),
  )

  const agingTotal = computed(() => calcSubtotal(agingRows.value.map((row) => row.amount)))

  /** F4-5 中账龄超1年但尚未纳入披露的行数 */
  const pendingSyncCount = computed(() => {
    const usedIds = new Set(agingStored.value.map((row) => row.sourceRowId).filter(Boolean))
    return overOneYearSource.value.filter((row) => !usedIds.has(row.rowId)).length
  })

  // ─── 行操作 ────────────────────────────────────────────────────────────────
  function addNatureRow(): void {
    if (readonly.value) return
    natureStored.value.push({
      rowId: generateRowId(),
      sourceKey: '',
      label: '',
      closingBalance: 0,
      priorBalance: 0,
    })
    persistNature()
  }

  function removeNatureRow(rowId: string): void {
    if (readonly.value) return
    const index = natureStored.value.findIndex((row) => row.rowId === rowId)
    if (index === -1) return
    natureStored.value.splice(index, 1)
    persistNature()
  }

  function updateNatureCell(rowId: string, field: 'label' | 'closingBalance' | 'priorBalance', value: unknown): void {
    if (readonly.value) return
    const row = natureStored.value.find((item) => item.rowId === rowId)
    if (!row) return
    if (field === 'label') row.label = String(value ?? '')
    else row[field] = parseNum(value as string | number | null | undefined)
    persistNature()
  }

  function addAgingRow(): void {
    if (readonly.value) return
    agingStored.value.push({
      rowId: generateRowId(),
      sourceRowId: '',
      creditor: '',
      amount: 0,
      reason: '',
    })
    persistAging()
  }

  function removeAgingRow(rowId: string): void {
    if (readonly.value) return
    const index = agingStored.value.findIndex((row) => row.rowId === rowId)
    if (index === -1) return
    agingStored.value.splice(index, 1)
    persistAging()
  }

  function updateAgingCell(rowId: string, field: 'creditor' | 'amount' | 'reason', value: unknown): void {
    if (readonly.value) return
    const row = agingStored.value.find((item) => item.rowId === rowId)
    if (!row) return
    if (field === 'amount') row.amount = parseNum(value as string | number | null | undefined)
    else row[field] = String(value ?? '')
    persistAging()
  }

  /** 同步F4-5账龄超1年的行（跳过已同步项），返回新增条数 */
  function syncFromLongOutstanding(): number {
    if (readonly.value) return 0
    const usedIds = new Set(agingStored.value.map((row) => row.sourceRowId).filter(Boolean))
    const pending = overOneYearSource.value.filter((row) => !usedIds.has(row.rowId))
    for (const source of pending) {
      agingStored.value.push({
        rowId: generateRowId(),
        sourceRowId: source.rowId,
        creditor: source.creditor,
        amount: source.amount,
        // 原因留空表示实时跟随F4-5；用户填写后以披露表为准
        reason: '',
      })
    }
    if (pending.length) persistAging()
    return pending.length
  }

  // ─── 持久化 ────────────────────────────────────────────────────────────────
  function setItem(key: string, remark: string): void {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark })
    debounceSave()
  }

  function persistNature(): void {
    setItem(NATURE_ROWS_KEY, JSON.stringify(natureStored.value))
  }

  function persistAging(): void {
    setItem(AGING_ROWS_KEY, JSON.stringify(agingStored.value))
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 1500)
  }

  function flushSave(): void {
    const items = [NATURE_ROWS_KEY, AGING_ROWS_KEY, TEXT_KEY]
      .map((key) => allResponses.value.get(key))
      .filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items } }))
    }
  }

  watch(disclosureText, (value) => {
    setItem(TEXT_KEY, value)
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      // 应付账款 listed → 五、37（note_template_variant_matrix）→ useNoteRefresh 定向刷新
      detail: { wpCode: 'F4', accountCode: '2202', type: 'listed', sectionIds: ['五、37'], text: value },
    }))
  })

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    natureRows,
    natureClosingTotal,
    naturePriorTotal,
    adjClosingTotal,
    adjPriorTotal,
    closingMatchesAdjudication,
    priorMatchesAdjudication,
    agingRows,
    agingTotal,
    overOneYearSource,
    pendingSyncCount,
    addNatureRow,
    removeNatureRow,
    updateNatureCell,
    addAgingRow,
    removeAgingRow,
    updateAgingCell,
    syncFromLongOutstanding,
    disclosureText,
  }
}

export default useF4DisclosureListed
