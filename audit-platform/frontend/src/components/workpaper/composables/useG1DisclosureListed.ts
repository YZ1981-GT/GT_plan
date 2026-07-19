/**
 * useG1DisclosureListed — G1 上市附注披露（六段页签）
 */
import { ref, computed, watch, onScopeDispose, type Ref } from 'vue'
import { parseNum, calcSubtotal } from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import {
  G1_ACCOUNT_CODE,
  G1_DISCLOSURE_TABS,
  G1_INPUT_CANDIDATES,
  calcL3Closing,
  defaultAmortRows,
  defaultClassificationRows,
  defaultDerivativeRows,
  defaultFvHierarchyRows,
  defaultInputRows,
  defaultL3RollRows,
  hierarchyTotal,
  sumAmountLeaves,
  type G1DiscAmountRow,
  type G1DiscAmortRow,
  type G1DiscHierarchyRow,
  type G1DiscInputRow,
  type G1DiscL3RollRow,
  type G1DisclosureTabKey,
} from './g1DisclosureItems'
import type { G1ListedSyncSnapshot } from './g1DisclosureSyncPayload'
import { buildG1AdjudicationRows } from './useG1Adjudication'
import { parseG1AdjStore } from './g1AdjudicationItems'
import { migrateLegacyLevel3Row, summarizeLevel3ByDisclosureLeaf } from './useG1Level3'

const ITEM_STORE = 'G1-note-listed-store'
const ITEM_NOTE = 'G1-note-listed-note'
/** 兼容旧自由表格 */
const ITEM_LEGACY_ROWS = 'G1-note-listed-rows'

export interface G1ListedDisclosureStore {
  version: 2
  activeTab: G1DisclosureTabKey
  classificationRows: G1DiscAmountRow[]
  designatedReason: string
  derivativeApplicable: boolean
  derivativeRows: G1DiscAmountRow[]
  derivativeNote: string
  fvRows: G1DiscHierarchyRow[]
  inputRows: G1DiscInputRow[]
  l3Rows: G1DiscL3RollRow[]
  amortRows: G1DiscAmortRow[]
}

function emptyStore(): G1ListedDisclosureStore {
  return {
    version: 2,
    activeTab: 'classification',
    classificationRows: defaultClassificationRows(),
    designatedReason: '',
    derivativeApplicable: true,
    derivativeRows: defaultDerivativeRows(),
    derivativeNote: '',
    fvRows: defaultFvHierarchyRows(),
    inputRows: defaultInputRows(),
    l3Rows: defaultL3RollRows(),
    amortRows: defaultAmortRows(),
  }
}

function mergeAmountRows(defaults: G1DiscAmountRow[], saved?: G1DiscAmountRow[]): G1DiscAmountRow[] {
  if (!saved?.length) return defaults
  const byKey = new Map(saved.map((r) => [r.rowKey, r]))
  return defaults.map((d) => {
    const s = byKey.get(d.rowKey)
    return s ? { ...d, ...s, label: d.label, kind: d.kind, adjKey: d.adjKey } : d
  })
}

function mergeHierarchy(defaults: G1DiscHierarchyRow[], saved?: G1DiscHierarchyRow[]): G1DiscHierarchyRow[] {
  if (!saved?.length) return defaults
  const byKey = new Map(saved.map((r) => [r.rowKey, r]))
  return defaults.map((d) => {
    const s = byKey.get(d.rowKey)
    return s ? { ...d, ...s, label: d.label, kind: d.kind } : d
  })
}

function mergeL3(defaults: G1DiscL3RollRow[], saved?: G1DiscL3RollRow[]): G1DiscL3RollRow[] {
  if (!saved?.length) return defaults
  const byKey = new Map(saved.map((r) => [r.rowKey, r]))
  return defaults.map((d) => {
    const s = byKey.get(d.rowKey)
    return s ? { ...d, ...s, label: d.label, kind: d.kind } : d
  })
}

function parseStore(raw: string | null | undefined): G1ListedDisclosureStore {
  const base = emptyStore()
  if (!raw) return base
  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return base
    if (parsed.version === 2) {
      return {
        ...base,
        ...parsed,
        classificationRows: mergeAmountRows(defaultClassificationRows(), parsed.classificationRows),
        derivativeRows: mergeAmountRows(defaultDerivativeRows(), parsed.derivativeRows),
        fvRows: mergeHierarchy(defaultFvHierarchyRows(), parsed.fvRows),
        inputRows: Array.isArray(parsed.inputRows) && parsed.inputRows.length
          ? parsed.inputRows
          : defaultInputRows(),
        l3Rows: mergeL3(defaultL3RollRows(), parsed.l3Rows),
        amortRows: Array.isArray(parsed.amortRows) && parsed.amortRows.length
          ? parsed.amortRows
          : defaultAmortRows(),
      }
    }
  } catch {
    /* ignore */
  }
  return base
}

function rollupAmountRows(rows: G1DiscAmountRow[]): G1DiscAmountRow[] {
  const sum = sumAmountLeaves(rows)
  return rows.map((r) => {
    if (r.kind === 'subtotal') return { ...r, endAmount: sum.end, priorAmount: sum.prior }
    if (r.kind === 'header') {
      // header = following leaves until next header/subtotal — simplified: leave 0 or sum children with same prefix
      const prefix = r.rowKey.replace(/__h$/, '')
      const kids = rows.filter((x) => x.kind === 'leaf' && x.rowKey.startsWith(`${prefix}-`) && x.applicable !== false)
      return {
        ...r,
        endAmount: kids.reduce((s, x) => s + (Number(x.endAmount) || 0), 0),
        priorAmount: kids.reduce((s, x) => s + (Number(x.priorAmount) || 0), 0),
      }
    }
    return r
  })
}

function rollupFv(rows: G1DiscHierarchyRow[]): G1DiscHierarchyRow[] {
  const t = hierarchyTotal(rows)
  return rows.map((r) => (r.kind === 'subtotal' ? { ...r, l1: t.l1, l2: t.l2, l3: t.l3 } : r))
}

function rollupL3(rows: G1DiscL3RollRow[]): G1DiscL3RollRow[] {
  const withClose = rows.map((r) =>
    r.kind === 'leaf' ? { ...r, closing: calcL3Closing(r) } : r,
  )
  const leaves = withClose.filter((r) => r.kind === 'leaf')
  const sumField = (f: keyof G1DiscL3RollRow) =>
    leaves.reduce((s, r) => s + (Number(r[f]) || 0), 0)
  return withClose.map((r) => {
    if (r.kind !== 'subtotal') return r
    return {
      ...r,
      opening: sumField('opening'),
      transferIn: sumField('transferIn'),
      transferOut: sumField('transferOut'),
      gainPl: sumField('gainPl'),
      gainOci: sumField('gainOci'),
      purchase: sumField('purchase'),
      issue: sumField('issue'),
      sale: sumField('sale'),
      settlement: sumField('settlement'),
      closing: sumField('closing'),
      unrealizedHeld: sumField('unrealizedHeld'),
    }
  })
}

export function useG1DisclosureListed(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const store = ref<G1ListedDisclosureStore>(parseStore(opts.allResponses.value.get(ITEM_STORE)?.remark))
  const generalNote = ref(opts.allResponses.value.get(ITEM_NOTE)?.remark ?? '')
  const adjudicatedAmount = ref<number | null>(null)
  const activeTab = computed({
    get: () => store.value.activeTab,
    set: (v: G1DisclosureTabKey) => {
      store.value = { ...store.value, activeTab: v }
      persist()
    },
  })

  watch(
    () => opts.allResponses.value.get(ITEM_STORE)?.remark,
    (raw) => {
      if (raw) store.value = parseStore(raw)
    },
  )
  watch(
    () => opts.allResponses.value.get(ITEM_NOTE)?.remark,
    (v) => {
      if (v != null && !generalNote.value) generalNote.value = v
    },
  )

  const classificationRows = computed(() => rollupAmountRows(store.value.classificationRows))
  const derivativeRows = computed(() => rollupAmountRows(store.value.derivativeRows))
  const fvRows = computed(() => rollupFv(store.value.fvRows))
  const l3Rows = computed(() => rollupL3(store.value.l3Rows))
  const inputRows = computed(() => store.value.inputRows)
  const amortRows = computed(() => store.value.amortRows)

  const classTotal = computed(() => sumAmountLeaves(store.value.classificationRows).end)
  const fvTotal = computed(() => hierarchyTotal(store.value.fvRows).total)
  const l3ClosingTotal = computed(() =>
    calcSubtotal(rollupL3(store.value.l3Rows).filter((r) => r.kind === 'leaf').map((r) => r.closing)),
  )

  const classVsAdjDiff = computed(() => {
    if (adjudicatedAmount.value == null) return null
    return classTotal.value - adjudicatedAmount.value
  })
  const fvVsAdjDiff = computed(() => {
    if (adjudicatedAmount.value == null) return null
    return fvTotal.value - adjudicatedAmount.value
  })
  const l3VsFvDiff = computed(() => {
    const fvL3 = hierarchyTotal(store.value.fvRows).l3
    return l3ClosingTotal.value - fvL3
  })

  function persist() {
    if (opts.isReadonly.value) return
    opts.debouncedSave(ITEM_STORE, { remark: JSON.stringify(store.value) })
  }

  function persistNote() {
    if (opts.isReadonly.value) return
    opts.debouncedSave(ITEM_NOTE, { remark: generalNote.value })
    try {
      window.dispatchEvent(
        new CustomEvent('disclosure:note-text-updated', {
          detail: {
            wpCode: 'G1',
            accountCode: G1_ACCOUNT_CODE,
            type: 'listed',
            text: generalNote.value,
            sectionId: '五、2',
          },
        }),
      )
    } catch {
      /* silent */
    }
  }

  watch(generalNote, () => persistNote())

  function patchStore(patch: Partial<G1ListedDisclosureStore>) {
    store.value = { ...store.value, ...patch }
    persist()
  }

  function updateClassField(rowKey: string, field: 'endAmount' | 'priorAmount' | 'remark' | 'applicable', value: unknown) {
    if (opts.isReadonly.value) return
    const rows = store.value.classificationRows.map((r) => {
      if (r.rowKey !== rowKey || r.kind !== 'leaf') return r
      if (field === 'applicable') return { ...r, applicable: Boolean(value) }
      if (field === 'remark') return { ...r, remark: String(value ?? '') }
      return { ...r, [field]: parseNum(value) }
    })
    patchStore({ classificationRows: rows })
  }

  function updateDerivField(rowKey: string, field: 'endAmount' | 'priorAmount' | 'remark' | 'applicable', value: unknown) {
    if (opts.isReadonly.value) return
    const rows = store.value.derivativeRows.map((r) => {
      if (r.rowKey !== rowKey || r.kind !== 'leaf') return r
      if (field === 'applicable') return { ...r, applicable: Boolean(value) }
      if (field === 'remark') return { ...r, remark: String(value ?? '') }
      return { ...r, [field]: parseNum(value) }
    })
    patchStore({ derivativeRows: rows })
  }

  function updateFvField(rowKey: string, field: 'l1' | 'l2' | 'l3' | 'applicable', value: unknown) {
    if (opts.isReadonly.value) return
    const rows = store.value.fvRows.map((r) => {
      if (r.rowKey !== rowKey || r.kind !== 'leaf') return r
      if (field === 'applicable') return { ...r, applicable: Boolean(value) }
      return { ...r, [field]: parseNum(value) }
    })
    patchStore({ fvRows: rows })
  }

  function updateInputField(rowKey: string, field: keyof G1DiscInputRow, value: unknown) {
    if (opts.isReadonly.value) return
    const rows = store.value.inputRows.map((r) => {
      if (r.rowKey !== rowKey) return r
      if (field === 'endFv') return { ...r, endFv: parseNum(value) }
      if (field === 'selectedIndicators') return { ...r, selectedIndicators: value as string[] }
      return { ...r, [field]: value as never }
    })
    patchStore({ inputRows: rows })
  }

  function applyTechniqueIndicators(rowKey: string, technique: string) {
    const candidates = G1_INPUT_CANDIDATES[technique] ?? []
    updateInputField(rowKey, 'technique', technique)
    updateInputField(rowKey, 'selectedIndicators', [...candidates])
    updateInputField(rowKey, 'inputs', candidates.join('、'))
  }

  function updateL3Field(rowKey: string, field: keyof G1DiscL3RollRow, value: unknown) {
    if (opts.isReadonly.value) return
    const rows = store.value.l3Rows.map((r) => {
      if (r.rowKey !== rowKey || r.kind !== 'leaf') return r
      if (field === 'label') return { ...r, label: String(value ?? '') }
      return { ...r, [field]: parseNum(value) }
    })
    patchStore({ l3Rows: rows })
  }

  function updateAmortField(rowKey: string, field: keyof G1DiscAmortRow, value: unknown) {
    if (opts.isReadonly.value) return
    const rows = store.value.amortRows.map((r) => {
      if (r.rowKey !== rowKey) return r
      if (field === 'label' || field === 'remark') return { ...r, [field]: String(value ?? '') }
      return { ...r, [field]: parseNum(value) }
    })
    patchStore({ amortRows: rows })
  }

  /** 从 G1-1 审定表 carrying 叶子带入分类披露期末数 */
  function pullFromAdjudication() {
    if (opts.isReadonly.value) return
    const adjRaw = opts.allResponses.value.get('G1-1-rows')?.remark
    const adjRows = buildG1AdjudicationRows(parseG1AdjStore(adjRaw))
    const byKey = new Map(adjRows.map((r) => [r.rowKey, r]))
    const rows = store.value.classificationRows.map((r) => {
      if (!r.adjKey || r.kind !== 'leaf') return r
      const src = byKey.get(r.adjKey)
      if (!src) return r
      return {
        ...r,
        endAmount: src.closingAudited,
        priorAmount: src.openingAudited,
      }
    })
    // 衍生：从 carrying 各分类 derivative 汇总
    const derivEnd = ['classified', 'designated', 'trading']
      .map((c) => byKey.get(`carrying-${c}-derivative`)?.closingAudited ?? 0)
      .reduce((a, b) => a + b, 0)
    const derivPrior = ['classified', 'designated', 'trading']
      .map((c) => byKey.get(`carrying-${c}-derivative`)?.openingAudited ?? 0)
      .reduce((a, b) => a + b, 0)
    const derivRows = store.value.derivativeRows.map((r) =>
      r.rowKey === 'deriv-other'
        ? { ...r, endAmount: derivEnd, priorAmount: derivPrior }
        : r,
    )
    const book = byKey.get('footer-book-total')
    if (book) adjudicatedAmount.value = book.closingAudited
    patchStore({ classificationRows: rows, derivativeRows: derivRows })
  }

  /** 从 G1-6 汇总层次到 FV 表（优先审定 FV；兼容 conclusion/remark） */
  function pullFromFairValueTest() {
    if (opts.isReadonly.value) return
    const item = opts.allResponses.value.get('G1-6-rows')
    const raw = item?.conclusion || item?.remark
    if (!raw) return
    try {
      const list = JSON.parse(raw)
      if (!Array.isArray(list)) return
      let l1 = 0
      let l2 = 0
      let l3 = 0
      for (const row of list) {
        const amt = parseNum(
          row.testedValue
            ?? row.auditedFv
            ?? row.bookFv
            ?? row.bookValue
            ?? row.marketValue
            ?? row.level2Result
            ?? row.level3Result,
        )
        const lv = row.fvLevel ?? row.fairValueLevel
        const level =
          lv === 2 || lv === '2' || lv === 'Level2' || lv === 'Level 2' ? 2
            : lv === 3 || lv === '3' || lv === 'Level3' || lv === 'Level 3' ? 3
              : 1
        if (level === 1) l1 += amt
        else if (level === 2) l2 += amt
        else l3 += amt
      }
      const fvRows = store.value.fvRows.map((r) =>
        r.rowKey === 'fv-trading' ? { ...r, l1, l2, l3 } : r,
      )
      patchStore({ fvRows })
    } catch {
      /* ignore */
    }
  }

  /** 从 G1-7 带入 L3 调节（按品种拆分到债务/权益/衍生叶子） */
  function pullFromLevel3() {
    if (opts.isReadonly.value) return
    const item = opts.allResponses.value.get('G1-7-rows')
    const raw = item?.conclusion || item?.remark
    if (!raw) return
    try {
      const list = JSON.parse(raw)
      if (!Array.isArray(list) || !list.length) return
      const rows = list.map((p: Record<string, unknown>, i: number) => migrateLegacyLevel3Row(p, i + 1))
      const byLeaf = summarizeLevel3ByDisclosureLeaf(rows)
      const l3Rows = store.value.l3Rows.map((r) => {
        const summary = byLeaf[r.rowKey]
        if (!summary || r.kind !== 'leaf') return r
        return {
          ...r,
          opening: summary.opening,
          transferIn: summary.transferIn,
          transferOut: summary.transferOut,
          gainPl: summary.gainPl,
          gainOci: summary.gainOci,
          purchase: summary.purchase,
          issue: summary.issue,
          sale: summary.sale,
          settlement: summary.settlement,
          unrealizedHeld: summary.unrealizedHeld,
        }
      })
      patchStore({ l3Rows })
    } catch {
      /* ignore */
    }
  }

  function refreshFromSources() {
    pullFromAdjudication()
    pullFromFairValueTest()
    pullFromLevel3()
    pullPledgeFlagsFromDetail()
  }

  /** 从 G1-2 汇总质押/变现受限项数，写入附注说明草稿提示 */
  function pullPledgeFlagsFromDetail() {
    if (opts.isReadonly.value) return
    const raw = opts.allResponses.value.get('G1-2-rows')?.conclusion
    if (!raw) return
    try {
      const list = JSON.parse(raw) as Array<{
        securityName?: string
        pledged?: boolean
        realizationRestricted?: boolean
      }>
      if (!Array.isArray(list)) return
      const pledged = list.filter((r) => r.pledged).map((r) => r.securityName || '未命名')
      const restricted = list.filter((r) => r.realizationRestricted).map((r) => r.securityName || '未命名')
      if (!pledged.length && !restricted.length) return
      const tip = [
        pledged.length ? `质押：${pledged.join('、')}` : '',
        restricted.length ? `变现受限：${restricted.join('、')}` : '',
      ]
        .filter(Boolean)
        .join('；')
      const prefix = `【自 G1-2】${tip}`
      if (!generalNote.value.includes('【自 G1-2】')) {
        generalNote.value = generalNote.value ? `${prefix}\n${generalNote.value}` : prefix
        persistNote()
      }
    } catch {
      /* ignore */
    }
  }

  function onAdjudicated(e: Event) {
    const detail = (e as CustomEvent).detail
    if (detail?.accountCode !== G1_ACCOUNT_CODE) return
    const amt = detail.auditedAmount ?? detail.adjudicatedAmount
    if (typeof amt === 'number') adjudicatedAmount.value = amt
  }

  window.addEventListener('substantive:adjudicated', onAdjudicated)
  onScopeDispose(() => window.removeEventListener('substantive:adjudicated', onAdjudicated))

  // 启动时尝试读审定合计
  watch(
    () => opts.allResponses.value.get('G1-1-rows')?.remark,
    (raw) => {
      if (!raw || adjudicatedAmount.value != null) return
      try {
        const book = buildG1AdjudicationRows(parseG1AdjStore(raw)).find((r) => r.rowKey === 'footer-book-total')
        if (book) adjudicatedAmount.value = book.closingAudited
      } catch {
        /* ignore */
      }
    },
    { immediate: true },
  )

  // 旧版自由行：若无 store 但有 legacy rows，不自动迁移金额（结构不同），仅保留 note

  function getSyncSnapshot(): G1ListedSyncSnapshot {
    return {
      classificationRows: classificationRows.value,
      designatedReason: store.value.designatedReason,
      derivativeRows: derivativeRows.value,
      derivativeNote: store.value.derivativeNote,
      fvRows: fvRows.value,
      inputRows: inputRows.value,
      l3Rows: l3Rows.value,
      amortRows: amortRows.value,
      generalNote: generalNote.value,
    }
  }

  return {
    G1_ACCOUNT_CODE,
    G1_DISCLOSURE_TABS,
    G1_INPUT_CANDIDATES,
    activeTab,
    store,
    classificationRows,
    derivativeRows,
    fvRows,
    inputRows,
    l3Rows,
    amortRows,
    designatedReason: computed({
      get: () => store.value.designatedReason,
      set: (v: string) => patchStore({ designatedReason: v }),
    }),
    derivativeNote: computed({
      get: () => store.value.derivativeNote,
      set: (v: string) => patchStore({ derivativeNote: v }),
    }),
    derivativeApplicable: computed({
      get: () => store.value.derivativeApplicable,
      set: (v: boolean) => patchStore({ derivativeApplicable: v }),
    }),
    generalNote,
    adjudicatedAmount,
    classTotal,
    fvTotal,
    l3ClosingTotal,
    classVsAdjDiff,
    fvVsAdjDiff,
    l3VsFvDiff,
    updateClassField,
    updateDerivField,
    updateFvField,
    updateInputField,
    applyTechniqueIndicators,
    updateL3Field,
    updateAmortField,
    refreshFromSources,
    getSyncSnapshot,
    persist,
  }
}
