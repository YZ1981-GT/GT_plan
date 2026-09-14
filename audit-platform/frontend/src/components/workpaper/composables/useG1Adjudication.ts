/**
 * useG1Adjudication — G1-1 审定表
 * 对齐 Excel：期初/期末 × 未审/调整/审定 + 变动分析；
 * 行结构：投资成本 / 累计 FV / 账面余额 × 分类 × 品种
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type WritableComputedRef } from 'vue'
import {
  G1_ACCOUNT_CODE,
  G1_CHANGE_RATE_THRESHOLD,
  G1_ADJUDICATION_ITEMS,
  leafKeysForClass,
  leafKeysForSection,
  parseG1AdjStore,
  applyG1AdjustmentWriteback,
  allocateG1WritebackAcrossRows,
  listG1WritebackAllocTargets,
  G1_ADJ_WRITEBACK_ROW_KEY,
  type G1AdjRowDef,
  type G1AdjRowStore,
  type G1AdjSection,
  type G1AdjClass,
  type G1AdjAsset,
} from './g1AdjudicationItems'
import {
  parseNum,
  calcAuditedAmount,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
} from './useG1TraFinFormulaEngine'
import { calcG1FvChangeAuditedTotal } from './gCycleExternalCross'
import type { ChecklistResponse } from './useF1FormData'
import type { TradingDetailRow } from './useG1Detail'
import { loadDetailPartials } from './g1CrossHelpers'

export { G1_ACCOUNT_CODE, G1_CHANGE_RATE_THRESHOLD, G1_ADJ_WRITEBACK_ROW_KEY, applyG1AdjustmentWriteback, listG1WritebackAllocTargets }

/** @deprecated 旧矩阵常量，保留供外部引用兼容 */
export const G1_INVEST_TYPES = [
  { rowKey: 'stock', label: '股票' },
  { rowKey: 'fund', label: '基金' },
  { rowKey: 'bond', label: '债券' },
  { rowKey: 'derivative', label: '衍生工具' },
  { rowKey: 'other', label: '其他' },
] as const

/** @deprecated */
export const G1_MEASURE_TYPES = [
  { rowKey: 'cost', label: '成本' },
  { rowKey: 'fv-change', label: '公允价值变动' },
  { rowKey: 'disposal', label: '处置损益' },
] as const

const ITEM_ID_ROWS = 'G1-1-rows'
const ITEM_ID_TB = 'G1-1-tb'
const ITEM_ID_NOTE = 'G1-1-note'
const ITEM_ID_CONCLUSION = 'G1-1-conclusion'

export type G1AdjEditableField =
  | 'openingUnadjusted'
  | 'openingAdjustment'
  | 'closingUnadjusted'
  | 'closingAdjustment'
  | 'reasonAnalysis'

export interface G1AdjudicationRow {
  rowKey: string
  label: string
  kind: G1AdjRowDef['kind']
  section?: G1AdjSection
  classKey?: string
  assetKey?: string
  indent: number
  editable: boolean
  openingUnadjusted: number
  openingAdjustment: number
  openingAudited: number
  closingUnadjusted: number
  closingAdjustment: number
  closingAudited: number
  changeAmount: number
  changeRate: number | '' | 'N/A'
  reasonAnalysis: string
  changeRateHighlight: boolean
  reasonRequired: boolean
  /** 兼容旧 calcG1FvChangeAuditedTotal */
  measureKey: string
  currentAudited: number
}

function emptyAmounts() {
  return {
    openingUnadjusted: 0,
    openingAdjustment: 0,
    openingAudited: 0,
    closingUnadjusted: 0,
    closingAdjustment: 0,
    closingAudited: 0,
    changeAmount: 0,
    changeRate: '' as const,
    reasonAnalysis: '',
    changeRateHighlight: false,
    reasonRequired: false,
    measureKey: '',
    currentAudited: 0,
  }
}

function rateFlags(rate: number | '' | 'N/A') {
  const highlight = typeof rate === 'number' && Math.abs(rate) > G1_CHANGE_RATE_THRESHOLD
  return { changeRateHighlight: highlight, reasonRequired: highlight }
}

function withDerived(
  base: Omit<G1AdjudicationRow, 'openingAudited' | 'closingAudited' | 'changeAmount' | 'changeRate' | 'changeRateHighlight' | 'reasonRequired' | 'measureKey' | 'currentAudited'> & {
    openingAudited?: number
    closingAudited?: number
  },
): G1AdjudicationRow {
  const openingAudited = base.openingAudited
    ?? calcAuditedAmount(base.openingUnadjusted, base.openingAdjustment, 0)
  const closingAudited = base.closingAudited
    ?? calcAuditedAmount(base.closingUnadjusted, base.closingAdjustment, 0)
  const changeAmount = calcChangeAmount(closingAudited, openingAudited)
  const changeRate = calcChangeRate(openingAudited, closingAudited)
  const flags = rateFlags(changeRate)
  return {
    ...base,
    openingAudited,
    closingAudited,
    changeAmount,
    changeRate,
    ...flags,
    measureKey: base.section === 'fv' ? 'fv-change' : base.section === 'cost' ? 'cost' : '',
    currentAudited: closingAudited,
  }
}

function sumKeys(
  map: Map<string, G1AdjudicationRow>,
  keys: string[],
  field: 'openingUnadjusted' | 'openingAdjustment' | 'closingUnadjusted' | 'closingAdjustment' | 'openingAudited' | 'closingAudited',
): number {
  return calcSubtotal(keys.map((k) => map.get(k)?.[field] ?? 0))
}

/** 供单测：由持久化 store 构建完整审定表行 */
export function buildG1AdjudicationRows(store: G1AdjRowStore): G1AdjudicationRow[] {
  return buildRows(store)
}

function buildRows(store: G1AdjRowStore): G1AdjudicationRow[] {
  const byKey = new Map<string, G1AdjudicationRow>()

  // 1) cost / fv leaf + headers placeholders
  for (const def of G1_ADJUDICATION_ITEMS) {
    if (def.section === 'carrying') continue
    if (def.kind === 'footer') continue

    if (def.kind === 'section_header') {
      byKey.set(def.rowKey, withDerived({
        rowKey: def.rowKey,
        label: def.label,
        kind: def.kind,
        section: def.section,
        indent: def.indent ?? 0,
        editable: false,
        ...emptyAmounts(),
      }))
      continue
    }

    if (def.kind === 'leaf' && def.section && def.editable) {
      const raw = store[def.rowKey] ?? {}
      byKey.set(def.rowKey, withDerived({
        rowKey: def.rowKey,
        label: def.label,
        kind: def.kind,
        section: def.section,
        classKey: def.classKey,
        assetKey: def.assetKey,
        indent: def.indent ?? 0,
        editable: true,
        openingUnadjusted: parseNum(raw.openingUnadjusted),
        openingAdjustment: parseNum(raw.openingAdjustment),
        closingUnadjusted: parseNum(raw.closingUnadjusted),
        closingAdjustment: parseNum(raw.closingAdjustment),
        reasonAnalysis: String(raw.reasonAnalysis ?? ''),
      }))
      continue
    }

    // class_header / section_subtotal filled after leaves
    byKey.set(def.rowKey, withDerived({
      rowKey: def.rowKey,
      label: def.label,
      kind: def.kind,
      section: def.section,
      classKey: def.classKey,
      indent: def.indent ?? 0,
      editable: false,
      ...emptyAmounts(),
    }))
  }

  // 2) roll up cost/fv class headers & section subtotals
  for (const section of ['cost', 'fv'] as G1AdjSection[]) {
    for (const cls of ['trading', 'classified', 'designated'] as const) {
      const keys = leafKeysForClass(section, cls)
      const classKey = `${section}-${cls}__class`
      byKey.set(classKey, withDerived({
        rowKey: classKey,
        label: byKey.get(classKey)?.label ?? '',
        kind: 'class_header',
        section,
        classKey: cls,
        indent: 1,
        editable: false,
        openingUnadjusted: sumKeys(byKey, keys, 'openingUnadjusted'),
        openingAdjustment: sumKeys(byKey, keys, 'openingAdjustment'),
        closingUnadjusted: sumKeys(byKey, keys, 'closingUnadjusted'),
        closingAdjustment: sumKeys(byKey, keys, 'closingAdjustment'),
        reasonAnalysis: '',
      }))
    }
    const allLeaves = leafKeysForSection(section)
    const subKey = `${section}__subtotal`
    byKey.set(subKey, withDerived({
      rowKey: subKey,
      label: '小计',
      kind: 'section_subtotal',
      section,
      indent: 0,
      editable: false,
      openingUnadjusted: sumKeys(byKey, allLeaves, 'openingUnadjusted'),
      openingAdjustment: sumKeys(byKey, allLeaves, 'openingAdjustment'),
      closingUnadjusted: sumKeys(byKey, allLeaves, 'closingUnadjusted'),
      closingAdjustment: sumKeys(byKey, allLeaves, 'closingAdjustment'),
      reasonAnalysis: '',
    }))
  }

  // 3) carrying = cost + fv（同分类同品种）
  for (const def of G1_ADJUDICATION_ITEMS) {
    if (def.section !== 'carrying') continue
    if (def.kind === 'section_header') {
      byKey.set(def.rowKey, withDerived({
        rowKey: def.rowKey,
        label: def.label,
        kind: def.kind,
        section: 'carrying',
        indent: 0,
        editable: false,
        ...emptyAmounts(),
      }))
      continue
    }
    if (def.kind === 'leaf' && def.classKey && def.assetKey) {
      const cost = byKey.get(`cost-${def.classKey}-${def.assetKey}`)
      const fv = byKey.get(`fv-${def.classKey}-${def.assetKey}`)
      byKey.set(def.rowKey, withDerived({
        rowKey: def.rowKey,
        label: def.label,
        kind: 'leaf',
        section: 'carrying',
        classKey: def.classKey,
        assetKey: def.assetKey,
        indent: 2,
        editable: false,
        openingUnadjusted: (cost?.openingUnadjusted ?? 0) + (fv?.openingUnadjusted ?? 0),
        openingAdjustment: (cost?.openingAdjustment ?? 0) + (fv?.openingAdjustment ?? 0),
        closingUnadjusted: (cost?.closingUnadjusted ?? 0) + (fv?.closingUnadjusted ?? 0),
        closingAdjustment: (cost?.closingAdjustment ?? 0) + (fv?.closingAdjustment ?? 0),
        openingAudited: (cost?.openingAudited ?? 0) + (fv?.openingAudited ?? 0),
        closingAudited: (cost?.closingAudited ?? 0) + (fv?.closingAudited ?? 0),
        reasonAnalysis: '',
      }))
      continue
    }
  }

  for (const cls of ['trading', 'classified', 'designated'] as const) {
    const keys = leafKeysForClass('carrying', cls)
    const classKey = `carrying-${cls}__class`
    const defLabel = G1_ADJUDICATION_ITEMS.find((d) => d.rowKey === classKey)?.label ?? ''
    byKey.set(classKey, withDerived({
      rowKey: classKey,
      label: defLabel,
      kind: 'class_header',
      section: 'carrying',
      classKey: cls,
      indent: 1,
      editable: false,
      openingUnadjusted: sumKeys(byKey, keys, 'openingUnadjusted'),
      openingAdjustment: sumKeys(byKey, keys, 'openingAdjustment'),
      closingUnadjusted: sumKeys(byKey, keys, 'closingUnadjusted'),
      closingAdjustment: sumKeys(byKey, keys, 'closingAdjustment'),
      openingAudited: sumKeys(byKey, keys, 'openingAudited'),
      closingAudited: sumKeys(byKey, keys, 'closingAudited'),
      reasonAnalysis: '',
    }))
  }
  {
    const allLeaves = leafKeysForSection('carrying')
    byKey.set('carrying__subtotal', withDerived({
      rowKey: 'carrying__subtotal',
      label: '小计',
      kind: 'section_subtotal',
      section: 'carrying',
      indent: 0,
      editable: false,
      openingUnadjusted: sumKeys(byKey, allLeaves, 'openingUnadjusted'),
      openingAdjustment: sumKeys(byKey, allLeaves, 'openingAdjustment'),
      closingUnadjusted: sumKeys(byKey, allLeaves, 'closingUnadjusted'),
      closingAdjustment: sumKeys(byKey, allLeaves, 'closingAdjustment'),
      openingAudited: sumKeys(byKey, allLeaves, 'openingAudited'),
      closingAudited: sumKeys(byKey, allLeaves, 'closingAudited'),
      reasonAnalysis: '',
    }))
  }

  // 4) footer
  const overRaw = store['footer-over-one-year'] ?? {}
  const over = withDerived({
    rowKey: 'footer-over-one-year',
    label: '减：超过一年到期的部分',
    kind: 'footer',
    indent: 0,
    editable: true,
    openingUnadjusted: parseNum(overRaw.openingUnadjusted),
    openingAdjustment: parseNum(overRaw.openingAdjustment),
    closingUnadjusted: parseNum(overRaw.closingUnadjusted),
    closingAdjustment: parseNum(overRaw.closingAdjustment),
    reasonAnalysis: String(overRaw.reasonAnalysis ?? ''),
  })
  byKey.set(over.rowKey, over)

  const carryingSub = byKey.get('carrying__subtotal')
  const bookTotal = withDerived({
    rowKey: 'footer-book-total',
    label: '账面余额（公允价值）合计',
    kind: 'footer',
    indent: 0,
    editable: false,
    openingUnadjusted: (carryingSub?.openingUnadjusted ?? 0) - over.openingUnadjusted,
    openingAdjustment: (carryingSub?.openingAdjustment ?? 0) - over.openingAdjustment,
    closingUnadjusted: (carryingSub?.closingUnadjusted ?? 0) - over.closingUnadjusted,
    closingAdjustment: (carryingSub?.closingAdjustment ?? 0) - over.closingAdjustment,
    openingAudited: (carryingSub?.openingAudited ?? 0) - over.openingAudited,
    closingAudited: (carryingSub?.closingAudited ?? 0) - over.closingAudited,
    reasonAnalysis: '',
  })
  byKey.set(bookTotal.rowKey, bookTotal)

  return G1_ADJUDICATION_ITEMS.map((d) => byKey.get(d.rowKey)!).filter(Boolean)
}

export function useG1Adjudication(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
  /** render html_data：含 tb_values / adjudicated_amount（后端 seed） */
  htmlData?: Ref<any>
}) {
  const rowStore = ref<G1AdjRowStore>({})
  const trialBalanceAmount = ref(0)
  const auditNote = ref('')
  const conclusion = ref('')
  let tbSeeded = false

  watch(() => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark, (j) => {
    rowStore.value = parseG1AdjStore(j)
  }, { immediate: true })

  watch(() => opts.allResponses.value.get(ITEM_ID_TB)?.remark, (v) => {
    trialBalanceAmount.value = parseNum(v)
  }, { immediate: true })

  watch(() => opts.allResponses.value.get(ITEM_ID_NOTE)?.conclusion, (v) => {
    auditNote.value = v ?? ''
  }, { immediate: true })

  watch(() => opts.allResponses.value.get(ITEM_ID_CONCLUSION)?.conclusion, (v) => {
    conclusion.value = v ?? ''
  }, { immediate: true })

  /** 本地试算为空时，用后端 html_data.tb_values 灌入 */
  function seedTrialBalanceFromHtml(): void {
    if (tbSeeded || opts.isReadonly.value) return
    const existing = opts.allResponses.value.get(ITEM_ID_TB)?.remark
    if (existing != null && String(existing).trim() !== '' && Math.abs(parseNum(existing)) > 0.0001) {
      tbSeeded = true
      return
    }
    const hd = opts.htmlData?.value
    const tb = hd?.tb_values ?? hd?.tbValues ?? null
    const closing = parseNum(tb?.closing ?? tb?.closing_balance ?? tb?.ending)
    const opening = parseNum(tb?.opening ?? tb?.opening_balance)
    if (Math.abs(closing) < 0.0001 && Math.abs(opening) < 0.0001) return
    trialBalanceAmount.value = closing
    opts.debouncedSave(ITEM_ID_TB, { remark: String(closing) })
    tbSeeded = true
  }

  watch(
    () => opts.htmlData?.value,
    () => { seedTrialBalanceFromHtml() },
    { immediate: true, deep: true },
  )

  const rows = computed(() => buildRows(rowStore.value))

  const totalRow = computed(() => {
    const book = rows.value.find((r) => r.rowKey === 'footer-book-total')
    return book ?? withDerived({
      rowKey: 'total',
      label: '合计',
      kind: 'footer',
      indent: 0,
      editable: false,
      ...emptyAmounts(),
    })
  })

  const fvChangeTotal = computed(() =>
    calcG1FvChangeAuditedTotal(
      rows.value.filter((r) => r.kind === 'leaf' && r.section === 'fv'),
    ),
  )

  const trialBalanceDiff = computed(
    () => totalRow.value.closingAudited - trialBalanceAmount.value,
  )

  function persistStore() {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rowStore.value) })
  }

  function updateField(rowKey: string, field: G1AdjEditableField, value: number | string) {
    if (opts.isReadonly.value) return
    const def = G1_ADJUDICATION_ITEMS.find((d) => d.rowKey === rowKey)
    if (!def?.editable && def?.kind !== 'footer') return
    if (def?.kind === 'footer' && rowKey !== 'footer-over-one-year') return
    if (def?.section === 'carrying') return

    const prev = rowStore.value[rowKey] ?? {}
    if (field === 'reasonAnalysis') {
      rowStore.value = { ...rowStore.value, [rowKey]: { ...prev, reasonAnalysis: String(value) } }
    } else {
      rowStore.value = {
        ...rowStore.value,
        [rowKey]: { ...prev, [field]: parseNum(value) },
      }
    }
    persistStore()
  }

  function updateTrialBalance(v: number) {
    if (opts.isReadonly.value) return
    trialBalanceAmount.value = v
    opts.debouncedSave(ITEM_ID_TB, { remark: String(v) })
  }

  const auditNoteModel: WritableComputedRef<string> = computed({
    get: () => auditNote.value,
    set: (v) => {
      auditNote.value = v
      if (!opts.isReadonly.value) opts.debouncedSave(ITEM_ID_NOTE, { conclusion: v })
    },
  })

  const conclusionModel: WritableComputedRef<string> = computed({
    get: () => conclusion.value,
    set: (v) => {
      conclusion.value = v
      if (!opts.isReadonly.value) opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: v })
    },
  })

  function publishAdjudicated(): void {
    try {
      window.dispatchEvent(
        new CustomEvent('substantive:adjudicated', {
          detail: {
            wpCode: 'G1',
            accountCode: G1_ACCOUNT_CODE,
            auditedAmount: totalRow.value.closingAudited,
            priorAudited: totalRow.value.openingAudited,
          },
        }),
      )
      window.dispatchEvent(
        new CustomEvent('g1:writeback-trial-balance', {
          detail: {
            accountCode: G1_ACCOUNT_CODE,
            auditedAmount: totalRow.value.closingAudited,
          },
        }),
      )
    } catch {
      /* ignore */
    }
  }

  function publishFvChangeForCross(): void {
    try {
      window.dispatchEvent(
        new CustomEvent('g-cycle:source-fv', {
          detail: { source: 'G1', amount: fvChangeTotal.value },
        }),
      )
    } catch {
      /* ignore */
    }
  }

  watch(() => totalRow.value.closingAudited, () => { publishAdjudicated() })
  watch(() => fvChangeTotal.value, () => { publishFvChangeForCross() })

  /** 监听 G1-3 确认事件，回写期末账项调整 */
  const lastWritebackNet = ref(0)
  function applyAdjustmentWriteback(netAdjustment: number, rowKey = G1_ADJ_WRITEBACK_ROW_KEY) {
    if (opts.isReadonly.value) return
    rowStore.value = applyG1AdjustmentWriteback(rowStore.value, netAdjustment, rowKey)
    lastWritebackNet.value = parseNum(netAdjustment)
    persistStore()
    publishAdjudicated()
  }

  /** 将默认行净额分摊到多个投资成本·交易性·品种行 */
  function allocateWriteback(
    allocations: Array<{ rowKey: string; amount: number }>,
  ): { ok: boolean; message: string } {
    if (opts.isReadonly.value) return { ok: false, message: '只读' }
    const net = lastWritebackNet.value
    if (Math.abs(net) < 0.01) return { ok: false, message: '无回写净额可分摊' }
    const sum = allocations.reduce((s, a) => s + (Number(a.amount) || 0), 0)
    if (Math.abs(sum - net) > 0.05) {
      return {
        ok: false,
        message: `分摊合计 ${sum.toFixed(2)} 与回写净额 ${net.toFixed(2)} 相差过大（容差 0.05）`,
      }
    }
    rowStore.value = allocateG1WritebackAcrossRows(rowStore.value, net, allocations)
    persistStore()
    publishAdjudicated()
    return { ok: true, message: '已分摊' }
  }

  function onAdjustmentConfirmed(ev: Event) {
    const detail = (ev as CustomEvent).detail || {}
    if (detail.accountCode && detail.accountCode !== G1_ACCOUNT_CODE) return
    if (typeof detail.netAdjustment !== 'number') return
    applyAdjustmentWriteback(detail.netAdjustment)
  }

  window.addEventListener('g1:adjustment-confirmed', onAdjustmentConfirmed)
  onBeforeUnmount(() => {
    window.removeEventListener('g1:adjustment-confirmed', onAdjustmentConfirmed)
  })

  function rowClassName({ row }: { row: G1AdjudicationRow }) {
    if (row.kind === 'section_header') return 'row-section-header'
    if (row.kind === 'class_header') return 'row-class-header'
    if (row.kind === 'section_subtotal' || row.rowKey === 'footer-book-total') return 'row-subtotal'
    if (row.kind === 'footer') return 'row-footer'
    return ''
  }

  /**
   * 从 G1-2 汇总未审数（保留已有账项调整与原因分析）。
   * 映射：acctClass × investType → cost/fv 叶子；一年一年以上扣减写入 footer。
   */
  function syncFromDetail(): number {
    if (opts.isReadonly.value) return 0
    const details = loadDetailPartials(opts.allResponses.value)
    if (!details.length) return 0

    const buckets = new Map<string, { openingCost: number; closingCost: number; openingFv: number; closingFv: number }>()
    let openingLt = 0
    let closingLt = 0

    for (const d of details) {
      const classKey = mapAcctClass(d.acctClass)
      const assetKey = mapInvestType(d.investType)
      const key = `${classKey}|${assetKey}`
      const cur = buckets.get(key) ?? { openingCost: 0, closingCost: 0, openingFv: 0, closingFv: 0 }
      cur.openingCost += parseNum(d.openingCost)
      cur.closingCost += parseNum(d.closingCost) || parseNum(d.auditedClosingCost)
      cur.openingFv += parseNum(d.openingCumulativeFv)
      cur.closingFv += parseNum(d.cumulativeFVChange) || parseNum(d.auditedClosingCumulativeFv)
      buckets.set(key, cur)
      openingLt += parseNum(d.openingLtDeduction)
      closingLt += parseNum(d.closingLtDeduction)
    }

    const next: G1AdjRowStore = { ...rowStore.value }
    let touched = 0
    for (const [combo, amt] of buckets) {
      const [classKey, assetKey] = combo.split('|') as [G1AdjClass, G1AdjAsset]
      const costKey = `cost-${classKey}-${assetKey}`
      const fvKey = `fv-${classKey}-${assetKey}`
      const prevCost = next[costKey] ?? {}
      const prevFv = next[fvKey] ?? {}
      next[costKey] = {
        ...prevCost,
        openingUnadjusted: amt.openingCost,
        closingUnadjusted: amt.closingCost,
        openingAdjustment: parseNum(prevCost.openingAdjustment),
        closingAdjustment: parseNum(prevCost.closingAdjustment),
        reasonAnalysis: prevCost.reasonAnalysis ?? '',
      }
      next[fvKey] = {
        ...prevFv,
        openingUnadjusted: amt.openingFv,
        closingUnadjusted: amt.closingFv,
        openingAdjustment: parseNum(prevFv.openingAdjustment),
        closingAdjustment: parseNum(prevFv.closingAdjustment),
        reasonAnalysis: prevFv.reasonAnalysis ?? '',
      }
      touched += 1
    }

    const prevOver = next['footer-over-one-year'] ?? {}
    next['footer-over-one-year'] = {
      ...prevOver,
      openingUnadjusted: openingLt,
      closingUnadjusted: closingLt,
      openingAdjustment: parseNum(prevOver.openingAdjustment),
      closingAdjustment: parseNum(prevOver.closingAdjustment),
      reasonAnalysis: prevOver.reasonAnalysis ?? '',
    }

    rowStore.value = next
    persistStore()
    publishAdjudicated()
    return touched
  }

  return {
    rows,
    totalRow,
    trialBalanceAmount,
    trialBalanceDiff,
    auditNote: auditNoteModel,
    conclusion: conclusionModel,
    updateField,
    updateTrialBalance,
    publishAdjudicated,
    syncFromDetail,
    applyAdjustmentWriteback,
    allocateWriteback,
    lastWritebackNet,
    writebackAllocTargets: listG1WritebackAllocTargets(),
    rowClassName,
    G1_CHANGE_RATE_THRESHOLD,
    G1_ADJ_WRITEBACK_ROW_KEY,
  }
}

function mapAcctClass(v: TradingDetailRow['acctClass'] | string | undefined): G1AdjClass {
  if (v === 'classified_fvpl') return 'classified'
  if (v === 'designated_fvpl') return 'designated'
  return 'trading'
}

function mapInvestType(v: TradingDetailRow['investType'] | string | undefined): G1AdjAsset {
  if (v === 'bond') return 'debt'
  if (v === 'stock') return 'equity'
  if (v === 'fund') return 'fund'
  if (v === 'derivative') return 'derivative'
  return 'other'
}
