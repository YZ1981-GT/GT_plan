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
import {
  buildDataResourceRows,
  buildDataResourceSyncRows,
  buildDataResourceTieChecks,
  deriveDataResourceClassRow,
  isDataResourceEmpty,
  setDrCell,
  type DrClassLinkage,
  type DrColKey,
  type DrValueMap,
} from './f2DataResourceInventory'

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
    // `work-in-progress` 不在审定表 rowKey 全集（1404 是 `semi-finished`）→ 已删该死键
    rowKey: 'wip-combined',
    label: '自制半成品及在产品',
    kind: 'normal',
    sourceKeys: ['semi-finished', 'dev-costs'],
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
  // 数据资源无对应存货科目（1401~1412）→ 从 (5) 数据资源表联动取数，见 loadClassRow
  { rowKey: 'data-resources', label: '数据资源', kind: 'normal', sourceKeys: [] },
  // 1412 商品进销差价在国企版归入「其他」（国企源模板有「其他」行，上市版没有 → 并入库存商品）；
  // 死键 `other` 已删（审定表无此 rowKey），其余部分由 s1Overrides 手工录入补足
  { rowKey: 'other', label: '其他', kind: 'normal', sourceKeys: ['price-difference'] },
  {
    // 土地储备无对应科目 → 全靠 s1Overrides 手工录入（源模板注要求披露面积/本期增加/期末余额）
    rowKey: 'land-reserve',
    label: '其中：尚未开发的土地储备（由房地产开发企业填列）',
    kind: 'detail',
    sourceKeys: [],
  },
]

/** 允许手工录入 (1) 分类表金额的行（无科目来源者）；其余行一律跨表取数，禁手工覆盖 */
export const F2_SOE_MANUAL_CLASS_ROW_KEYS: readonly string[] = ['other', 'land-reserve']

const PREFIX = 'F2-note-soe-'
const ITEM_S2_OVERRIDES = `${PREFIX}s2-overrides`
/** (1) 分类表手工录入（仅「其他」「土地储备」两行，无科目来源） */
const ITEM_S1_OVERRIDES = `${PREFIX}s1-overrides`
const ITEM_NOTE_CATEGORY = `${PREFIX}note-category`
const ITEM_NOTE_BORROW = `${PREFIX}note-borrow`
const ITEM_NOTE_AMORT = `${PREFIX}note-amort`
const ITEM_NOTE = `${PREFIX}note`
const ITEM_LAND_NOTE = `${PREFIX}land-note`
/** (5) 确认为存货的数据资源（三段式 21 行，仅存录入行） */
const ITEM_S5_DR = `${PREFIX}s5-data-resource`

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

/**
 * (1) 分类表手工录入字段。`endNet` / `priorNet` **不可直接录入** ——
 * 由 `calcNetValue(账面余额, 跌价准备)` 派生，避免三者互不自洽。
 */
export type F2SoeClassManualField =
  'endGross' | 'endImpairment' | 'priorGross' | 'priorImpairment'

export type S1Override = Partial<Record<F2SoeClassManualField, number>>

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

  // ─── (5) 数据资源持久化值 ─────────────
  // 🔴 声明必须早于 `section1Rows`（分类表「数据资源」行从本表联动，computed 可能在
  // setup 期间就被求值；`drValues` 若在 TDZ 会 ReferenceError）。
  const drValues = ref<DrValueMap>({})

  watch(
    () => allResponses.value.get(ITEM_S5_DR)?.remark,
    (json) => { drValues.value = safeParseJson<DrValueMap>(json, {}) },
    { immediate: true },
  )

  const drClassLinkage: ComputedRef<DrClassLinkage> = computed(() =>
    deriveDataResourceClassRow(drValues.value),
  )

  // ─── (1) 分类表手工录入（仅无科目来源的两行）─────────────
  const s1Overrides = ref<Record<string, S1Override>>({})
  watch(
    () => allResponses.value.get(ITEM_S1_OVERRIDES)?.remark,
    (json) => { s1Overrides.value = safeParseJson(json, {}) },
    { immediate: true },
  )

  /** 手工录入行：四个金额取覆盖值，净值仍派生 */
  function manualClassRow(
    cat: (typeof F2_SOE_DISCLOSURE_CATEGORIES)[number],
    ov: S1Override,
  ): F2SoeClassRow {
    const endGross = parseNum(ov.endGross)
    const endImpairment = parseNum(ov.endImpairment)
    const priorGross = parseNum(ov.priorGross)
    const priorImpairment = parseNum(ov.priorImpairment)
    return {
      rowKey: cat.rowKey,
      label: cat.label,
      kind: cat.kind,
      endGross,
      endImpairment,
      endNet: calcNetValue(endGross, endImpairment),
      priorGross,
      priorImpairment,
      priorNet: calcNetValue(priorGross, priorImpairment),
    }
  }

  // ─── (1) 存货分类：跨 sheet 自 F2-1；数据资源自 (5) 联动；其他/土地储备手工录入 ───
  const section1Rows: ComputedRef<F2SoeClassRow[]> = computed(() => {
    void adjudicatedRefreshKey.value
    const map = allResponses.value
    const dr = drClassLinkage.value
    return F2_SOE_DISCLOSURE_CATEGORIES.map((cat) => {
      if (cat.rowKey === 'data-resources') {
        return {
          rowKey: cat.rowKey,
          label: cat.label,
          kind: cat.kind,
          endGross: dr.endGross,
          endImpairment: dr.endImpairment,
          endNet: calcNetValue(dr.endGross, dr.endImpairment),
          priorGross: dr.priorGross,
          priorImpairment: dr.priorImpairment,
          priorNet: calcNetValue(dr.priorGross, dr.priorImpairment),
        }
      }
      if (F2_SOE_MANUAL_CLASS_ROW_KEYS.includes(cat.rowKey)) {
        const base = loadClassRow(map, cat)
        const ov = s1Overrides.value[cat.rowKey]
        if (!ov || Object.keys(ov).length === 0) return base
        // 「其他」行仍保留 1412 进销差价的跨表取数：手工值与取数值相加
        const merged: S1Override = {
          endGross: base.endGross + parseNum(ov.endGross),
          endImpairment: base.endImpairment + parseNum(ov.endImpairment),
          priorGross: base.priorGross + parseNum(ov.priorGross),
          priorImpairment: base.priorImpairment + parseNum(ov.priorImpairment),
        }
        return manualClassRow(cat, merged)
      }
      return loadClassRow(map, cat)
    })
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

  // ─── (5) 确认为存货的数据资源（`drValues` 与 watch 已提前到 (1) 之前声明）─────────────
  const drRows = computed(() => buildDataResourceRows(drValues.value, 'soe'))
  const drIsEmpty = computed(() => isDataResourceEmpty(drValues.value))

  /** 与 (1) 分类表「数据资源」行的交叉勾稽（F9-12/12a/13/13a） */
  const drTieChecks = computed(() => {
    const cls = section1Rows.value.find((r) => r.rowKey === 'data-resources')
    return buildDataResourceTieChecks(
      drValues.value,
      cls
        ? {
            endGross: cls.endGross,
            endImpairment: cls.endImpairment,
            priorGross: cls.priorGross,
            priorImpairment: cls.priorImpairment,
          }
        : null,
      'soe',
    )
  })

  const drTieFailures = computed(() => drTieChecks.value.filter((c) => !c.ok))

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
    const keys = [
      ITEM_S1_OVERRIDES, ITEM_S2_OVERRIDES, ITEM_S5_DR,
      ITEM_NOTE_CATEGORY, ITEM_NOTE_BORROW, ITEM_NOTE_AMORT, ITEM_NOTE, ITEM_LAND_NOTE,
    ]
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
        // 存货 soe → 八、10（note_template_variant_matrix）
        detail: { wpCode: 'F2', accountCode: '1405', section, sectionIds: ['八、10'], text: val },
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

  /**
   * (1) 分类表手工录入。**rowKey 白名单**：只允许「其他」「土地储备」两行 ——
   * 其余行一律跨表自 F2-1 审定表取数，开放手工覆盖会破坏审定表的唯一权威性。
   */
  function updateS1Field(rowKey: string, field: F2SoeClassManualField, value: number): void {
    if (isReadonly.value) return
    if (!F2_SOE_MANUAL_CLASS_ROW_KEYS.includes(rowKey)) return
    const next = { ...(s1Overrides.value[rowKey] || {}), [field]: parseNum(value) }
    s1Overrides.value = { ...s1Overrides.value, [rowKey]: next }
    setItem(ITEM_S1_OVERRIDES, JSON.stringify(s1Overrides.value))
    debounceSave()
  }

  /** UI 判定：该行该列是否可手工录入 */
  function isManualClassRow(rowKey: string): boolean {
    return F2_SOE_MANUAL_CLASS_ROW_KEYS.includes(rowKey)
  }

  function updateS2Field(rowKey: string, field: keyof S2Override, value: number): void {
    if (isReadonly.value) return
    const next = { ...(s2Overrides.value[rowKey] || {}), [field]: parseNum(value) }
    s2Overrides.value = { ...s2Overrides.value, [rowKey]: next }
    setItem(ITEM_S2_OVERRIDES, JSON.stringify(s2Overrides.value))
    debounceSave()
  }

  /** (5) 数据资源：仅录入行可写（派生行/段标题行由 setDrCell 拦截） */
  function updateDrCell(rowKey: string, col: DrColKey, value: number | string | null): void {
    if (isReadonly.value) return
    const next = setDrCell(drValues.value, rowKey, col, value)
    if (next === drValues.value) return
    drValues.value = next
    setItem(ITEM_S5_DR, JSON.stringify(next))
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
      s5DataResourceRows: buildDataResourceSyncRows(drRows.value),
      noteCategory: noteCategory.value,
      landNote: landNote.value,
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
    drRows,
    drIsEmpty,
    drTieChecks,
    drTieFailures,
    noteCategory,
    s3BorrowText,
    s4AmortText,
    noteText,
    landNote,
    dataUpdatedVisible,
    isManualClassRow,
    updateS1Field,
    updateS2Field,
    updateDrCell,
    getSyncSnapshot,
  }
}

export default useF2DisclosureSoe
