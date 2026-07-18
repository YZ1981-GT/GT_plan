/**
 * useF2DetailSummary — F2-2 明细汇总表
 * 对齐源模板：一审计目标/过程 · (一)原值 · (二)跌价 · (三)账面价值 · 审计说明/结论
 * 跨表：未审数自 F2-3~F2-13（含 F2-10）；跌价未审自 F2-1；审定=未审+调整
 */
import { ref, computed, watch, type Ref } from 'vue'
import { calcSubtotal, calcAuditedEnd, calcNetValue, calcChangeRate, parseNum } from './useF2InvMaiFormulaEngine'
import { readRowJson, type ChecklistResponse } from './useF2FormData'
import type { F2DetailRow } from './useF2DetailSheet'
import type { DevProductRow } from './useF2DevProductSheet'
import { sumDevProductMovement } from './useF2DevProductSheet'
import { sumDevCostMovement } from './useF2DevCostSheet'
import { sumContractPerfMovement } from './useF2ContractPerfSheet'
import { sumBioAssetMovement } from './useF2BioAssetSheet'
import { F2_SHEET_TO_ROW_KEY, F2_ROW_KEY_TO_SHEET } from './useF2CrossSheet'

/** Excel 行序：含无独立明细表的在产品/数据资源（手工未审） */
export const F2_SUMMARY_CATEGORIES: ReadonlyArray<{
  rowKey: string
  label: string
  sheetCode: string
}> = [
  { rowKey: 'raw-materials', label: '原材料', sheetCode: 'F2-3' },
  { rowKey: 'material-in-transit', label: '材料采购/在途物资', sheetCode: 'F2-4' },
  { rowKey: 'revolving-materials', label: '周转材料/低值易耗品/包装物', sheetCode: 'F2-5' },
  { rowKey: 'work-in-progress', label: '在产品', sheetCode: '' },
  { rowKey: 'semi-finished', label: '自制半成品', sheetCode: 'F2-6' },
  { rowKey: 'outsourced-processing', label: '委托加工物资', sheetCode: 'F2-7' },
  { rowKey: 'finished-goods', label: '库存商品', sheetCode: 'F2-8' },
  { rowKey: 'goods-in-transit', label: '发出商品', sheetCode: 'F2-9' },
  { rowKey: 'dev-products', label: '开发产品', sheetCode: 'F2-10' },
  { rowKey: 'dev-costs', label: '开发成本', sheetCode: 'F2-11' },
  { rowKey: 'contract-performance', label: '合同履约成本', sheetCode: 'F2-12' },
  { rowKey: 'consumable-bio', label: '消耗性生物资产', sheetCode: 'F2-13' },
  { rowKey: 'data-resources', label: '数据资源', sheetCode: '' },
]

const PREFIX = 'F2-2-'
const ITEM_GROSS_ADJ = `${PREFIX}gross-adj`
const ITEM_IMP_ADJ = `${PREFIX}imp-adj`
const ITEM_BV_TEXTS = `${PREFIX}bv-texts`
const ITEM_MANUAL_UNAUD = `${PREFIX}manual-unaud`
const ITEM_OBJECTIVE = `${PREFIX}objective`
const ITEM_PROCESS = `${PREFIX}process`
const ITEM_NOTE = `${PREFIX}audit-note`
const ITEM_CONCLUSION = `${PREFIX}audit-conclusion`

export interface F2SummaryAdj {
  openingAdj: number
  closeAdjInc: number
  closeAdjDec: number
  remark: string
}

export interface F2SummaryImpAdj extends F2SummaryAdj {
  /** 审定减少明细：转回 / 核销 / 其他（合计应≈审定减少） */
  audDecReversal: number
  audDecWriteOff: number
  audDecOther: number
}

export interface F2SummaryBvText {
  changeReason: string
  nrvBasis: string
  reversalReason: string
}

export interface F2SummaryGrossRow {
  rowKey: string
  label: string
  sheetCode: string
  unaudOpen: number
  unaudInc: number
  unaudDec: number
  unaudClose: number
  openingAdj: number
  closeAdjInc: number
  closeAdjDec: number
  audOpen: number
  audInc: number
  audDec: number
  audClose: number
  remark: string
  crossSheet: boolean
}

export interface F2SummaryImpRow extends F2SummaryGrossRow {
  audDecReversal: number
  audDecWriteOff: number
  audDecOther: number
}

export interface F2SummaryBvRow {
  rowKey: string
  label: string
  sheetCode: string
  unaudOpen: number
  unaudClose: number
  audOpen: number
  audClose: number
  changeRateUnaud: number | '' | 'N/A'
  changeRateAud: number | '' | 'N/A'
  changeReason: string
  nrvBasis: string
  reversalReason: string
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

function emptyAdj(): F2SummaryAdj {
  return { openingAdj: 0, closeAdjInc: 0, closeAdjDec: 0, remark: '' }
}

function emptyImpAdj(): F2SummaryImpAdj {
  return { ...emptyAdj(), audDecReversal: 0, audDecWriteOff: 0, audDecOther: 0 }
}

function loadDevProductMovement(map: Map<string, ChecklistResponse>) {
  const raw = readRowJson(map.get('F2-10-rows'))
  if (!raw) return { opening: 0, increase: 0, decrease: 0, closing: 0 }
  try {
    const rows = JSON.parse(raw) as Partial<DevProductRow>[]
    return sumDevProductMovement(rows)
  } catch {
    return { opening: 0, increase: 0, decrease: 0, closing: 0 }
  }
}

function loadDevCostMovement(map: Map<string, ChecklistResponse>) {
  const raw = readRowJson(map.get('F2-11-rows'))
  if (!raw) return { opening: 0, increase: 0, decrease: 0, closing: 0 }
  try {
    return sumDevCostMovement(JSON.parse(raw))
  } catch {
    return { opening: 0, increase: 0, decrease: 0, closing: 0 }
  }
}

function loadContractPerfMovement(map: Map<string, ChecklistResponse>) {
  const raw = readRowJson(map.get('F2-12-rows'))
  if (!raw) return { opening: 0, increase: 0, decrease: 0, closing: 0 }
  try {
    return sumContractPerfMovement(JSON.parse(raw))
  } catch {
    return { opening: 0, increase: 0, decrease: 0, closing: 0 }
  }
}

function loadBioAssetMovement(map: Map<string, ChecklistResponse>) {
  const raw = readRowJson(map.get('F2-13-rows'))
  if (!raw) return { opening: 0, increase: 0, decrease: 0, closing: 0 }
  try {
    return sumBioAssetMovement(JSON.parse(raw))
  } catch {
    return { opening: 0, increase: 0, decrease: 0, closing: 0 }
  }
}

function loadDetailMovement(map: Map<string, ChecklistResponse>, sheetCode: string) {
  if (!sheetCode) return { opening: 0, increase: 0, decrease: 0, closing: 0 }
  if (sheetCode === 'F2-10') return loadDevProductMovement(map)
  if (sheetCode === 'F2-11') return loadDevCostMovement(map)
  if (sheetCode === 'F2-12') return loadContractPerfMovement(map)
  if (sheetCode === 'F2-13') return loadBioAssetMovement(map)
  const raw = readRowJson(map.get(`${sheetCode}-rows`))
  if (!raw) return { opening: 0, increase: 0, decrease: 0, closing: 0 }
  try {
    const rows = JSON.parse(raw) as F2DetailRow[]
    return {
      opening: calcSubtotal(rows.map((r) => r.openingAmt)),
      increase: calcSubtotal(rows.map((r) => r.increaseAmt)),
      decrease: calcSubtotal(rows.map((r) => r.decreaseAmt)),
      closing: calcSubtotal(rows.map((r) => r.closingAmt ?? 0)),
    }
  } catch {
    return { opening: 0, increase: 0, decrease: 0, closing: 0 }
  }
}

function loadF21Field(map: Map<string, ChecklistResponse>, block: 'gross' | 'impairment', rowKey: string, field: string): number {
  return parseNum(map.get(`F2-1-${block}-${rowKey}-${field}`)?.conclusion)
}

function loadImpairmentMovement(map: Map<string, ChecklistResponse>, rowKey: string) {
  const opening = loadF21Field(map, 'impairment', rowKey, 'opening')
  const increase = loadF21Field(map, 'impairment', rowKey, 'increase')
  const decrease = loadF21Field(map, 'impairment', rowKey, 'decrease')
  const adjustment = loadF21Field(map, 'impairment', rowKey, 'adjustment')
  const closing = calcAuditedEnd(opening, increase, decrease, adjustment)
  return { opening, increase, decrease, closing }
}

function fmtChangeRate(rate: number | '' | 'N/A'): string {
  if (rate === '' || rate === 'N/A') return rate === 'N/A' ? 'N/A' : '-'
  return `${(rate * 100).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
}

export { fmtChangeRate }

export function useF2DetailSummary(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
}) {
  const { allResponses, isReadonly } = options
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const grossAdjMap = ref<Record<string, F2SummaryAdj>>({})
  const impAdjMap = ref<Record<string, F2SummaryImpAdj>>({})
  const bvTextMap = ref<Record<string, F2SummaryBvText>>({})
  const manualUnaud = ref<Record<string, { open: number; inc: number; dec: number }>>({})

  const auditObjective = ref('')
  const auditProcess = ref('')
  const auditNote = ref('')
  const auditConclusion = ref('')

  watch(() => allResponses.value.get(ITEM_GROSS_ADJ)?.remark, (j) => { grossAdjMap.value = safeParseJson(j, {}) }, { immediate: true })
  watch(() => allResponses.value.get(ITEM_IMP_ADJ)?.remark, (j) => { impAdjMap.value = safeParseJson(j, {}) }, { immediate: true })
  watch(() => allResponses.value.get(ITEM_BV_TEXTS)?.remark, (j) => { bvTextMap.value = safeParseJson(j, {}) }, { immediate: true })
  watch(() => allResponses.value.get(ITEM_MANUAL_UNAUD)?.remark, (j) => { manualUnaud.value = safeParseJson(j, {}) }, { immediate: true })
  watch(() => allResponses.value.get(ITEM_OBJECTIVE)?.remark, (v) => { auditObjective.value = v || '' }, { immediate: true })
  watch(() => allResponses.value.get(ITEM_PROCESS)?.remark, (v) => { auditProcess.value = v || '' }, { immediate: true })
  // 兼容旧 key
  watch(() => allResponses.value.get(ITEM_NOTE)?.remark ?? allResponses.value.get('F2-detail-summary-audit-note')?.remark, (v) => { auditNote.value = v || '' }, { immediate: true })
  watch(() => allResponses.value.get(ITEM_CONCLUSION)?.remark ?? allResponses.value.get('F2-detail-summary-audit-conclusion')?.remark, (v) => { auditConclusion.value = v || '' }, { immediate: true })

  function setItem(key: string, remark: string): void {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark })
  }

  function flushSave(): void {
    const keys = [ITEM_GROSS_ADJ, ITEM_IMP_ADJ, ITEM_BV_TEXTS, ITEM_MANUAL_UNAUD, ITEM_OBJECTIVE, ITEM_PROCESS, ITEM_NOTE, ITEM_CONCLUSION]
    const items = keys.map((k) => allResponses.value.get(k)).filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items } }))
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function persistText(key: string, val: string): void {
    setItem(key, val)
    debounceSave()
  }

  watch(auditObjective, (v) => persistText(ITEM_OBJECTIVE, v))
  watch(auditProcess, (v) => persistText(ITEM_PROCESS, v))
  watch(auditNote, (v) => persistText(ITEM_NOTE, v))
  watch(auditConclusion, (v) => persistText(ITEM_CONCLUSION, v))

  const grossRows = computed((): F2SummaryGrossRow[] => {
    const map = allResponses.value
    return F2_SUMMARY_CATEGORIES.map((cat) => {
      let mov = loadDetailMovement(map, cat.sheetCode)
      if (!cat.sheetCode) {
        const m = manualUnaud.value[cat.rowKey] || { open: 0, inc: 0, dec: 0 }
        mov = {
          opening: parseNum(m.open),
          increase: parseNum(m.inc),
          decrease: parseNum(m.dec),
          closing: calcAuditedEnd(parseNum(m.open), parseNum(m.inc), parseNum(m.dec), 0),
        }
      }
      const adj = grossAdjMap.value[cat.rowKey] || emptyAdj()
      const unaudOpen = mov.opening
      const unaudInc = mov.increase
      const unaudDec = mov.decrease
      const unaudClose = mov.closing || calcAuditedEnd(unaudOpen, unaudInc, unaudDec, 0)
      const audOpen = unaudOpen + adj.openingAdj
      const audInc = unaudInc + adj.closeAdjInc
      const audDec = unaudDec + adj.closeAdjDec
      const audClose = audOpen + audInc - audDec
      return {
        rowKey: cat.rowKey,
        label: cat.label,
        sheetCode: cat.sheetCode || F2_ROW_KEY_TO_SHEET[cat.rowKey] || '',
        unaudOpen, unaudInc, unaudDec, unaudClose,
        openingAdj: adj.openingAdj,
        closeAdjInc: adj.closeAdjInc,
        closeAdjDec: adj.closeAdjDec,
        audOpen, audInc, audDec, audClose,
        remark: adj.remark,
        crossSheet: !!cat.sheetCode,
      }
    })
  })

  const grossTotal = computed((): F2SummaryGrossRow => {
    const rows = grossRows.value
    const sum = (fn: (r: F2SummaryGrossRow) => number) => calcSubtotal(rows.map(fn))
    return {
      rowKey: '__total__',
      label: '合计',
      sheetCode: '',
      unaudOpen: sum((r) => r.unaudOpen),
      unaudInc: sum((r) => r.unaudInc),
      unaudDec: sum((r) => r.unaudDec),
      unaudClose: sum((r) => r.unaudClose),
      openingAdj: sum((r) => r.openingAdj),
      closeAdjInc: sum((r) => r.closeAdjInc),
      closeAdjDec: sum((r) => r.closeAdjDec),
      audOpen: sum((r) => r.audOpen),
      audInc: sum((r) => r.audInc),
      audDec: sum((r) => r.audDec),
      audClose: sum((r) => r.audClose),
      remark: '',
      crossSheet: false,
    }
  })

  const impRows = computed((): F2SummaryImpRow[] => {
    const map = allResponses.value
    return F2_SUMMARY_CATEGORIES.map((cat) => {
      const mov = loadImpairmentMovement(map, cat.rowKey)
      const adj = impAdjMap.value[cat.rowKey] || emptyImpAdj()
      const unaudOpen = mov.opening
      const unaudInc = mov.increase
      const unaudDec = mov.decrease
      const unaudClose = mov.closing
      const audOpen = unaudOpen + adj.openingAdj
      const audInc = unaudInc + adj.closeAdjInc
      const audDec = unaudDec + adj.closeAdjDec
      const audClose = audOpen + audInc - audDec
      return {
        rowKey: cat.rowKey,
        label: cat.label,
        sheetCode: cat.sheetCode,
        unaudOpen, unaudInc, unaudDec, unaudClose,
        openingAdj: adj.openingAdj,
        closeAdjInc: adj.closeAdjInc,
        closeAdjDec: adj.closeAdjDec,
        audOpen, audInc, audDec, audClose,
        audDecReversal: adj.audDecReversal,
        audDecWriteOff: adj.audDecWriteOff,
        audDecOther: adj.audDecOther,
        remark: adj.remark,
        crossSheet: true,
      }
    })
  })

  const impTotal = computed((): F2SummaryImpRow => {
    const rows = impRows.value
    const sum = (fn: (r: F2SummaryImpRow) => number) => calcSubtotal(rows.map(fn))
    return {
      rowKey: '__total__',
      label: '合计',
      sheetCode: '',
      unaudOpen: sum((r) => r.unaudOpen),
      unaudInc: sum((r) => r.unaudInc),
      unaudDec: sum((r) => r.unaudDec),
      unaudClose: sum((r) => r.unaudClose),
      openingAdj: sum((r) => r.openingAdj),
      closeAdjInc: sum((r) => r.closeAdjInc),
      closeAdjDec: sum((r) => r.closeAdjDec),
      audOpen: sum((r) => r.audOpen),
      audInc: sum((r) => r.audInc),
      audDec: sum((r) => r.audDec),
      audClose: sum((r) => r.audClose),
      audDecReversal: sum((r) => r.audDecReversal),
      audDecWriteOff: sum((r) => r.audDecWriteOff),
      audDecOther: sum((r) => r.audDecOther),
      remark: '',
      crossSheet: false,
    }
  })

  const bvRows = computed((): F2SummaryBvRow[] => {
    const gBy = new Map(grossRows.value.map((r) => [r.rowKey, r]))
    const iBy = new Map(impRows.value.map((r) => [r.rowKey, r]))
    return F2_SUMMARY_CATEGORIES.map((cat) => {
      const g = gBy.get(cat.rowKey)!
      const i = iBy.get(cat.rowKey)!
      const text = bvTextMap.value[cat.rowKey] || { changeReason: '', nrvBasis: '', reversalReason: '' }
      const unaudOpen = calcNetValue(g.unaudOpen, i.unaudOpen)
      const unaudClose = calcNetValue(g.unaudClose, i.unaudClose)
      const audOpen = calcNetValue(g.audOpen, i.audOpen)
      const audClose = calcNetValue(g.audClose, i.audClose)
      return {
        rowKey: cat.rowKey,
        label: cat.label,
        sheetCode: cat.sheetCode,
        unaudOpen,
        unaudClose,
        audOpen,
        audClose,
        changeRateUnaud: calcChangeRate(unaudOpen, unaudClose),
        changeRateAud: calcChangeRate(audOpen, audClose),
        changeReason: text.changeReason,
        nrvBasis: text.nrvBasis,
        reversalReason: text.reversalReason,
      }
    })
  })

  const bvTotal = computed((): F2SummaryBvRow => {
    const rows = bvRows.value
    const unaudOpen = calcSubtotal(rows.map((r) => r.unaudOpen))
    const unaudClose = calcSubtotal(rows.map((r) => r.unaudClose))
    const audOpen = calcSubtotal(rows.map((r) => r.audOpen))
    const audClose = calcSubtotal(rows.map((r) => r.audClose))
    return {
      rowKey: '__total__',
      label: '合计',
      sheetCode: '',
      unaudOpen, unaudClose, audOpen, audClose,
      changeRateUnaud: calcChangeRate(unaudOpen, unaudClose),
      changeRateAud: calcChangeRate(audOpen, audClose),
      changeReason: '',
      nrvBasis: '',
      reversalReason: '',
    }
  })

  function updateGrossAdj(rowKey: string, field: keyof F2SummaryAdj, value: string | number): void {
    if (isReadonly.value) return
    const prev = grossAdjMap.value[rowKey] || emptyAdj()
    const next = { ...prev }
    if (field === 'remark') next.remark = String(value ?? '')
    else (next as any)[field] = parseNum(value)
    grossAdjMap.value = { ...grossAdjMap.value, [rowKey]: next }
    setItem(ITEM_GROSS_ADJ, JSON.stringify(grossAdjMap.value))
    debounceSave()
  }

  function updateImpAdj(rowKey: string, field: keyof F2SummaryImpAdj, value: string | number): void {
    if (isReadonly.value) return
    const prev = impAdjMap.value[rowKey] || emptyImpAdj()
    const next = { ...prev }
    if (field === 'remark') next.remark = String(value ?? '')
    else (next as any)[field] = parseNum(value)
    impAdjMap.value = { ...impAdjMap.value, [rowKey]: next }
    setItem(ITEM_IMP_ADJ, JSON.stringify(impAdjMap.value))
    debounceSave()
  }

  function updateBvText(rowKey: string, field: keyof F2SummaryBvText, value: string): void {
    if (isReadonly.value) return
    const prev = bvTextMap.value[rowKey] || { changeReason: '', nrvBasis: '', reversalReason: '' }
    bvTextMap.value = { ...bvTextMap.value, [rowKey]: { ...prev, [field]: value } }
    setItem(ITEM_BV_TEXTS, JSON.stringify(bvTextMap.value))
    debounceSave()
  }

  function updateManualUnaud(rowKey: string, field: 'open' | 'inc' | 'dec', value: number): void {
    if (isReadonly.value) return
    const prev = manualUnaud.value[rowKey] || { open: 0, inc: 0, dec: 0 }
    manualUnaud.value = { ...manualUnaud.value, [rowKey]: { ...prev, [field]: parseNum(value) } }
    setItem(ITEM_MANUAL_UNAUD, JSON.stringify(manualUnaud.value))
    debounceSave()
  }

  /** 供 AI / 审定表联动的上下文 */
  function getAiContext(): Record<string, unknown> {
    return {
      sheet: 'F2-2',
      grossTotal: {
        unaudClose: grossTotal.value.unaudClose,
        audClose: grossTotal.value.audClose,
      },
      impTotal: {
        unaudClose: impTotal.value.unaudClose,
        audClose: impTotal.value.audClose,
      },
      bvTotal: {
        unaudClose: bvTotal.value.unaudClose,
        audClose: bvTotal.value.audClose,
        changeRateAud: bvTotal.value.changeRateAud,
      },
      categories: bvRows.value.map((r) => ({
        label: r.label,
        sheetCode: r.sheetCode || F2_ROW_KEY_TO_SHEET[r.rowKey] || '',
        unaudClose: r.unaudClose,
        audClose: r.audClose,
        changeRateAud: r.changeRateAud,
      })),
    }
  }

  // 兼容旧 API（部分测试/引用）
  const rows = grossRows
  const totals = grossTotal
  const agingMismatchCount = computed(() => 0)

  return {
    grossRows,
    grossTotal,
    impRows,
    impTotal,
    bvRows,
    bvTotal,
    auditObjective,
    auditProcess,
    auditNote,
    auditConclusion,
    updateGrossAdj,
    updateImpAdj,
    updateBvText,
    updateManualUnaud,
    getAiContext,
    flushSave,
    // legacy
    rows,
    totals,
    agingMismatchCount,
  }
}

export default useF2DetailSummary

/** @deprecated 旧汇总行类型，保留导出以免外部引用断裂 */
export interface F2SummaryRow {
  sheetCode: string
  label: string
  hasQuantity: boolean
  openingQty: number
  openingUnitPrice: number | ''
  openingAmt: number
  increaseQty: number
  increaseUnitPrice: number | ''
  increaseAmt: number
  decreaseQty: number
  decreaseUnitPrice: number | ''
  decreaseAmt: number
  closingQty: number
  closingUnitPrice: number | ''
  closingAmt: number
  agingLt1: number
  aging1to2: number
  aging2to3: number
  agingGt3: number
  agingTotal: number
  agingMismatch: boolean
}
