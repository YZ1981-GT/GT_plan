/**
 * useF2DisclosureSoe — F2 附注披露（国企）
 * 对齐源模板「附注披露信息（国企）」与 F2SoeSyncSnapshot
 * Spec: .kiro/specs/f2-inventory-main/ Task 15.6
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, calcNetValue, calcAuditedEnd } from './useF2InvMaiFormulaEngine'
import type { ChecklistResponse } from './useF2FormData'
import { isF2DisclosureApplicable } from './f2NoteSectionMap'
import type { F2SoeSyncSnapshot } from './f2DisclosureSyncPayload'

/** kind: normal 计入合计；detail=「其中」子集，防双计 */
export type F2SoeRowKind = 'normal' | 'detail'

export const F2_SOE_DISCLOSURE_CATEGORIES: ReadonlyArray<{
  rowKey: string
  label: string
  kind: F2SoeRowKind
  sourceKeys: readonly string[]
}> = [
  { rowKey: 'raw-combined', label: '原材料', kind: 'normal', sourceKeys: ['raw-materials', 'material-in-transit'] },
  {
    rowKey: 'wip-combined',
    label: '自制半成品及在产品',
    kind: 'normal',
    sourceKeys: ['work-in-progress', 'semi-finished', 'dev-costs'],
  },
  { rowKey: 'dev-costs', label: '其中：开发成本', kind: 'detail', sourceKeys: ['dev-costs'] },
  { rowKey: 'outsourced-processing', label: '委托加工物资', kind: 'normal', sourceKeys: ['outsourced-processing'] },
  {
    rowKey: 'fg-combined',
    label: '库存商品（产成品）',
    kind: 'normal',
    sourceKeys: ['finished-goods', 'dev-products'],
  },
  { rowKey: 'dev-products', label: '其中：开发产品', kind: 'detail', sourceKeys: ['dev-products'] },
  {
    rowKey: 'revolving-materials',
    label: '周转材料（包装物、低值易耗品等）',
    kind: 'normal',
    sourceKeys: ['revolving-materials'],
  },
  { rowKey: 'goods-in-transit', label: '发出商品', kind: 'normal', sourceKeys: ['goods-in-transit'] },
  { rowKey: 'consumable-bio', label: '消耗性生物资产', kind: 'normal', sourceKeys: ['consumable-bio'] },
  { rowKey: 'contract-performance', label: '合同履约成本', kind: 'normal', sourceKeys: ['contract-performance'] },
  { rowKey: 'data-resources', label: '数据资源', kind: 'normal', sourceKeys: ['data-resources'] },
  { rowKey: 'other', label: '其他', kind: 'normal', sourceKeys: ['price-difference', 'other'] },
  {
    rowKey: 'land-reserve',
    label: '其中：尚未开发的土地储备（由房地产开发企业填列）',
    kind: 'detail',
    sourceKeys: ['land-reserve'],
  },
]

const PREFIX = 'F2-note-soe-'
const ITEM_S2_OVERRIDES = `${PREFIX}s2-overrides`
const ITEM_NOTE_CATEGORY = `${PREFIX}note-category`
const ITEM_NOTE_BORROW = `${PREFIX}note-borrow`
const ITEM_NOTE_AMORT = `${PREFIX}note-amort`
const ITEM_NOTE = `${PREFIX}note`
const ITEM_LAND_NOTE = `${PREFIX}land-note`

export interface F2SoeClassRow {
  rowKey: string
  label: string
  kind: F2SoeRowKind
  endGross: number
  endImpairment: number
  endNet: number
  priorGross: number
  priorImpairment: number
  priorNet: number
}

export interface F2SoeMovementRow {
  rowKey: string
  label: string
  kind: F2SoeRowKind
  opening: number
  incProvision: number
  incOther: number
  decReversal: number
  decWriteOff: number
  decOther: number
  ending: number
  tieDiff: number
}

interface S2Override {
  incProvision?: number | null
  incOther?: number
  decReversal?: number | null
  decWriteOff?: number
  decOther?: number
}

function itemId(block: 'gross' | 'impairment', rowKey: string, field: string): string {
  return `F2-1-${block}-${rowKey}-${field}`
}

function loadField(map: Map<string, ChecklistResponse>, id: string): number {
  return parseNum(map.get(id)?.conclusion)
}

function sumSources(
  map: Map<string, ChecklistResponse>,
  block: 'gross' | 'impairment',
  sourceKeys: readonly string[],
  field: string,
): number {
  return sourceKeys.reduce((s, key) => s + loadField(map, itemId(block, key, field)), 0)
}

function safeParseJson<T>(jsonStr: string | null | undefined, fallback: T): T {
  if (!jsonStr) return fallback
  try {
    const parsed = JSON.parse(jsonStr)
    return parsed ?? fallback
  } catch {
    return fallback
  }
}

function loadClassRow(
  map: Map<string, ChecklistResponse>,
  cat: (typeof F2_SOE_DISCLOSURE_CATEGORIES)[number],
): F2SoeClassRow {
  const openingG = sumSources(map, 'gross', cat.sourceKeys, 'opening')
  const openingI = sumSources(map, 'impairment', cat.sourceKeys, 'opening')
  const incG = sumSources(map, 'gross', cat.sourceKeys, 'increase')
  const incI = sumSources(map, 'impairment', cat.sourceKeys, 'increase')
  const decG = sumSources(map, 'gross', cat.sourceKeys, 'decrease')
  const decI = sumSources(map, 'impairment', cat.sourceKeys, 'decrease')
  const adjG = sumSources(map, 'gross', cat.sourceKeys, 'adjustment')
  const adjI = sumSources(map, 'impairment', cat.sourceKeys, 'adjustment')

  const priorGross = openingG
  const priorImpairment = openingI
  const priorNet = calcNetValue(priorGross, priorImpairment)
  const endGross = calcAuditedEnd(openingG, incG, decG, adjG)
  const endImpairment = calcAuditedEnd(openingI, incI, decI, adjI)
  const endNet = calcNetValue(endGross, endImpairment)

  return {
    rowKey: cat.rowKey,
    label: cat.label,
    kind: cat.kind,
    endGross,
    endImpairment,
    endNet,
    priorGross,
    priorImpairment,
    priorNet,
  }
}

function totalClass(rows: F2SoeClassRow[]): F2SoeClassRow {
  const mains = rows.filter((r) => r.kind === 'normal')
  return {
    rowKey: '__total__',
    label: '合计',
    kind: 'normal',
    endGross: calcSubtotal(mains.map((r) => r.endGross)),
    endImpairment: calcSubtotal(mains.map((r) => r.endImpairment)),
    endNet: calcSubtotal(mains.map((r) => r.endNet)),
    priorGross: calcSubtotal(mains.map((r) => r.priorGross)),
    priorImpairment: calcSubtotal(mains.map((r) => r.priorImpairment)),
    priorNet: calcSubtotal(mains.map((r) => r.priorNet)),
  }
}

function isF2InventoryAccount(code: string): boolean {
  const n = parseInt(code, 10)
  return (n >= 1401 && n <= 1412) || n === 1421 || n === 1461 || n === 1471
}

export function useF2DisclosureSoe(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
  applicableStandards: Ref<string[]>
}) {
  const { allResponses, isReadonly, applicableStandards } = options
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []
  const adjudicatedRefreshKey = ref(0)
  const dataUpdatedVisible = ref(false)
  let dataUpdatedTimer: ReturnType<typeof setTimeout> | null = null

  const isApplicable: ComputedRef<boolean> = computed(() =>
    isF2DisclosureApplicable('soe', applicableStandards.value),
  )

  // ─── (1) 存货分类 ─────────────
  const section1Rows: ComputedRef<F2SoeClassRow[]> = computed(() => {
    void adjudicatedRefreshKey.value
    return F2_SOE_DISCLOSURE_CATEGORIES.map((cat) => loadClassRow(allResponses.value, cat))
  })

  const section1Total: ComputedRef<F2SoeClassRow> = computed(() => totalClass(section1Rows.value))

  // ─── (2) 跌价准备变动（含转回/转销分列） ─────────────
  const s2Overrides = ref<Record<string, S2Override>>({})
  watch(
    () => allResponses.value.get(ITEM_S2_OVERRIDES)?.remark,
    (json) => { s2Overrides.value = safeParseJson(json, {}) },
    { immediate: true },
  )

  const section2Rows: ComputedRef<F2SoeMovementRow[]> = computed(() => {
    void adjudicatedRefreshKey.value
    const map = allResponses.value
    const classByKey = new Map(section1Rows.value.map((r) => [r.rowKey, r]))
    return F2_SOE_DISCLOSURE_CATEGORIES.map((cat) => {
      const opening = sumSources(map, 'impairment', cat.sourceKeys, 'opening')
      const autoInc = sumSources(map, 'impairment', cat.sourceKeys, 'increase')
      const autoDec = sumSources(map, 'impairment', cat.sourceKeys, 'decrease')
      const ov = s2Overrides.value[cat.rowKey] || {}
      const incProvision = ov.incProvision != null ? parseNum(ov.incProvision) : autoInc
      const incOther = parseNum(ov.incOther)
      const decReversal = ov.decReversal != null ? parseNum(ov.decReversal) : autoDec
      const decWriteOff = parseNum(ov.decWriteOff)
      const decOther = parseNum(ov.decOther)
      const ending = opening + incProvision + incOther - decReversal - decWriteOff - decOther
      const classEndI = classByKey.get(cat.rowKey)?.endImpairment ?? 0
      return {
        rowKey: cat.rowKey,
        label: cat.label,
        kind: cat.kind,
        opening,
        incProvision,
        incOther,
        decReversal,
        decWriteOff,
        decOther,
        ending,
        tieDiff: ending - classEndI,
      }
    })
  })

  const section2Total: ComputedRef<F2SoeMovementRow> = computed(() => {
    const mains = section2Rows.value.filter((r) => r.kind === 'normal')
    const opening = calcSubtotal(mains.map((r) => r.opening))
    const incProvision = calcSubtotal(mains.map((r) => r.incProvision))
    const incOther = calcSubtotal(mains.map((r) => r.incOther))
    const decReversal = calcSubtotal(mains.map((r) => r.decReversal))
    const decWriteOff = calcSubtotal(mains.map((r) => r.decWriteOff))
    const decOther = calcSubtotal(mains.map((r) => r.decOther))
    const ending = opening + incProvision + incOther - decReversal - decWriteOff - decOther
    return {
      rowKey: '__total__',
      label: '合计',
      kind: 'normal' as const,
      opening,
      incProvision,
      incOther,
      decReversal,
      decWriteOff,
      decOther,
      ending,
      tieDiff: ending - section1Total.value.endImpairment,
    }
  })

  // ─── 附注文字 ─────────────
  const noteCategory = ref('')
  const s3BorrowText = ref('')
  const s4AmortText = ref('')
  const noteText = ref('')
  const landNote = ref('')

  watch(() => allResponses.value.get(ITEM_NOTE_CATEGORY)?.remark, (v) => { noteCategory.value = v || '' }, { immediate: true })
  watch(() => allResponses.value.get(ITEM_NOTE_BORROW)?.remark, (v) => { s3BorrowText.value = v || '' }, { immediate: true })
  watch(() => allResponses.value.get(ITEM_NOTE_AMORT)?.remark, (v) => { s4AmortText.value = v || '' }, { immediate: true })
  watch(() => allResponses.value.get(ITEM_NOTE)?.remark, (v) => { noteText.value = v || '' }, { immediate: true })
  watch(() => allResponses.value.get(ITEM_LAND_NOTE)?.remark, (v) => { landNote.value = v || '' }, { immediate: true })

  function setItem(itemIdKey: string, remark: string): void {
    allResponses.value.set(itemIdKey, { item_id: itemIdKey, conclusion: null, remark })
  }

  function flushSave(): void {
    const keys = [ITEM_S2_OVERRIDES, ITEM_NOTE_CATEGORY, ITEM_NOTE_BORROW, ITEM_NOTE_AMORT, ITEM_NOTE, ITEM_LAND_NOTE]
    const items = keys.map((k) => allResponses.value.get(k)).filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items } }))
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function persistNote(itemIdKey: string, val: string, section: string): void {
    setItem(itemIdKey, val)
    debounceSave()
    try {
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: { wpCode: 'F2', section, text: val },
      }))
    } catch { /* silent */ }
  }

  watch(noteCategory, (v) => persistNote(ITEM_NOTE_CATEGORY, v, 'soe-note-category'))
  watch(s3BorrowText, (v) => persistNote(ITEM_NOTE_BORROW, v, 'soe-note-borrow'))
  watch(s4AmortText, (v) => persistNote(ITEM_NOTE_AMORT, v, 'soe-note-amort'))
  watch(noteText, (v) => persistNote(ITEM_NOTE, v, 'soe-note'))
  watch(landNote, (v) => persistNote(ITEM_LAND_NOTE, v, 'soe-note-land'))

  const adjudicatedHandler = (e: Event) => {
    const d = (e as CustomEvent).detail
    if (d?.wpCode !== 'F2') return
    const codes: string[] = d?.accountCodes ?? []
    if (codes.length === 0 || codes.some(isF2InventoryAccount)) {
      adjudicatedRefreshKey.value += 1
      dataUpdatedVisible.value = true
      if (dataUpdatedTimer) clearTimeout(dataUpdatedTimer)
      dataUpdatedTimer = setTimeout(() => { dataUpdatedVisible.value = false }, 3000)
    }
  }
  window.addEventListener('substantive:adjudicated', adjudicatedHandler)
  eventListeners.push({ event: 'substantive:adjudicated', handler: adjudicatedHandler })

  function updateS2Field(rowKey: string, field: keyof S2Override, value: number): void {
    if (isReadonly.value) return
    const next = { ...(s2Overrides.value[rowKey] || {}), [field]: parseNum(value) }
    s2Overrides.value = { ...s2Overrides.value, [rowKey]: next }
    setItem(ITEM_S2_OVERRIDES, JSON.stringify(s2Overrides.value))
    debounceSave()
  }

  function getSyncSnapshot(): F2SoeSyncSnapshot {
    return {
      section1Rows: section1Rows.value.map((r) => ({
        rowKey: r.rowKey,
        label: r.label,
        kind: r.kind,
        endGross: r.endGross,
        endImpairment: r.endImpairment,
        endNet: r.endNet,
        priorGross: r.priorGross,
        priorImpairment: r.priorImpairment,
        priorNet: r.priorNet,
      })),
      section1Total: {
        label: section1Total.value.label,
        endGross: section1Total.value.endGross,
        endImpairment: section1Total.value.endImpairment,
        endNet: section1Total.value.endNet,
        priorGross: section1Total.value.priorGross,
        priorImpairment: section1Total.value.priorImpairment,
        priorNet: section1Total.value.priorNet,
      },
      section2Rows: section2Rows.value.map((r) => ({
        rowKey: r.rowKey,
        label: r.label,
        opening: r.opening,
        incProvision: r.incProvision,
        incOther: r.incOther,
        decReversal: r.decReversal,
        decWriteOff: r.decWriteOff,
        decOther: r.decOther,
        ending: r.ending,
      })),
      section2Total: {
        label: section2Total.value.label,
        opening: section2Total.value.opening,
        incProvision: section2Total.value.incProvision,
        incOther: section2Total.value.incOther,
        decReversal: section2Total.value.decReversal,
        decWriteOff: section2Total.value.decWriteOff,
        decOther: section2Total.value.decOther,
        ending: section2Total.value.ending,
      },
      noteCategory: noteCategory.value,
      s3BorrowText: s3BorrowText.value,
      s4AmortText: s4AmortText.value,
      noteText: noteText.value,
    }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); flushSave() }
    if (dataUpdatedTimer) clearTimeout(dataUpdatedTimer)
    for (const { event, handler } of eventListeners) window.removeEventListener(event, handler)
  })

  return {
    isApplicable,
    section1Rows,
    section1Total,
    section2Rows,
    section2Total,
    noteCategory,
    s3BorrowText,
    s4AmortText,
    noteText,
    landNote,
    dataUpdatedVisible,
    updateS2Field,
    getSyncSnapshot,
  }
}

export default useF2DisclosureSoe
