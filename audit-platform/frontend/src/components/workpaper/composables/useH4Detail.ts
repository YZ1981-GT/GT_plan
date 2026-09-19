/**
 * useH4Detail — H4-2 明细表 composable
 *
 * 对齐致同「工程物资明细表 H4-2」Excel 编制逻辑（冲突决议 C4）：
 * 区段1「基础+未审原值」：分类/名称/计量 + 期初/增加/减少/期末（数量·单价·金额）
 * 区段2「调整+审定原值」：AJE 调整 + 审定期初/增/减/期末
 * 区段3「减值+净值」：跌价准备 rollforward + 未审/审定净值 + 差额 + 库龄/品质
 *
 * 保留采购/其他增加、领用/退货/报废/其他减少分项，供 H4-4/H4-5 勾稽。
 * 单价数量为 0 时不除零（避免源模板 #DIV/0!）。
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Requirements: 3.1-3.9 + C4
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAssetEndBalance,
  calcAuditedAmount,
  calcNetBookValue,
  calcSubtotal,
  calcUnitPrice,
} from './useH4FormulaEngine'
import { applyH43AjeBackToDetails, mergeH42AjeIntoH43 } from './h4AjeSyncModel'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H4-2 明细表行（公式列在 normalize 时重算） */
export interface H4DetailRow {
  rowId: string

  // 基础
  category: string
  name: string
  spec: string
  unit: string
  supplier: string

  // 数量 rollforward
  beginQty: number
  increaseQty: number
  decreaseQty: number
  endQty: number

  // 未审原值金额（保留分项供 H4-4/H4-5）
  beginAmount: number
  purchaseAmount: number
  otherIncrease: number
  increaseSubtotal: number
  usageAmount: number
  returnAmount: number
  scrapAmount: number
  otherDecrease: number
  decreaseTotal: number
  endAmount: number

  // 单价（公式；qty=0 → null）
  beginUnitPrice: number | null
  increaseUnitPrice: number | null
  decreaseUnitPrice: number | null
  endUnitPrice: number | null

  // 调整（金额口径 AJE，对齐 Excel 核实情况）
  ajeBegin: number
  ajeIncrease: number
  ajeDecrease: number

  // 审定原值（公式）
  auditedBegin: number
  auditedIncrease: number
  auditedDecrease: number
  auditedEnd: number

  // 跌价准备
  impairBegin: number
  impairIncrease: number
  impairDecrease: number
  impairEnd: number
  ajeImpair: number
  auditedImpairEnd: number

  // 净值
  bookValueBegin: number
  bookValueEnd: number
  auditedBookValue: number
  /** 未审期末净值 − 审定期末净值（差异≠0 需追查） */
  bookValueDiff: number

  aging: string
  quality: string
}

/** 3区段Tab（C4） */
export type H4DetailTab = 'book' | 'adjust' | 'impair'

/** 分类小计行 */
export interface H4CategorySubtotal {
  category: string
  beginAmount: number
  increaseSubtotal: number
  decreaseTotal: number
  endAmount: number
  impairEnd: number
  bookValueEnd: number
  auditedBookValue: number
  bookValueDiff: number
  rowCount: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H4-2-rows'
const DETAIL_TOTAL_KEY = 'H4-2-detail-total'
const DETAIL_INCREASE_KEY = 'H4-2-increase-total'
const DETAIL_DECREASE_KEY = 'H4-2-decrease-total'
const DETAIL_IMPAIR_KEY = 'H4-2-impair-total'

const TEXT_FIELDS = ['category', 'name', 'spec', 'unit', 'supplier', 'aging', 'quality'] as const
const NUM_FIELDS = [
  'beginQty', 'increaseQty', 'decreaseQty',
  'beginAmount', 'purchaseAmount', 'otherIncrease',
  'usageAmount', 'returnAmount', 'scrapAmount', 'otherDecrease',
  'ajeBegin', 'ajeIncrease', 'ajeDecrease',
  'impairBegin', 'impairIncrease', 'impairDecrease', 'ajeImpair',
] as const

// ─── Pure helpers（可单测） ───────────────────────────────────────────────────

function _n(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 重算一行全部公式列 */
export function recomputeH4DetailRow(row: H4DetailRow): H4DetailRow {
  const increaseSubtotal = row.purchaseAmount + row.otherIncrease
  const decreaseTotal = row.usageAmount + row.returnAmount + row.scrapAmount + row.otherDecrease
  const endAmount = calcAssetEndBalance(row.beginAmount, increaseSubtotal, decreaseTotal)
  const endQty = calcAssetEndBalance(row.beginQty, row.increaseQty, row.decreaseQty)

  const auditedBegin = calcAuditedAmount(row.beginAmount, row.ajeBegin, 0)
  const auditedIncrease = calcAuditedAmount(increaseSubtotal, row.ajeIncrease, 0)
  const auditedDecrease = calcAuditedAmount(decreaseTotal, row.ajeDecrease, 0)
  const auditedEnd = calcAssetEndBalance(auditedBegin, auditedIncrease, auditedDecrease)

  const impairEnd = calcAssetEndBalance(row.impairBegin, row.impairIncrease, row.impairDecrease)
  const auditedImpairEnd = calcAuditedAmount(impairEnd, row.ajeImpair, 0)

  const bookValueBegin = calcNetBookValue(row.beginAmount, row.impairBegin)
  const bookValueEnd = calcNetBookValue(endAmount, impairEnd)
  const auditedBookValue = calcNetBookValue(auditedEnd, auditedImpairEnd)

  return {
    ...row,
    increaseSubtotal,
    decreaseTotal,
    endAmount,
    endQty,
    beginUnitPrice: calcUnitPrice(row.beginAmount, row.beginQty),
    increaseUnitPrice: calcUnitPrice(increaseSubtotal, row.increaseQty),
    decreaseUnitPrice: calcUnitPrice(decreaseTotal, row.decreaseQty),
    endUnitPrice: calcUnitPrice(endAmount, endQty),
    auditedBegin,
    auditedIncrease,
    auditedDecrease,
    auditedEnd,
    impairEnd,
    auditedImpairEnd,
    bookValueBegin,
    bookValueEnd,
    auditedBookValue,
    bookValueDiff: Math.round((bookValueEnd - auditedBookValue) * 100) / 100,
  }
}

/** 按物资分类汇总（对齐 Excel SUMPRODUCT 分类小计） */
export function buildCategorySubtotals(rows: H4DetailRow[]): H4CategorySubtotal[] {
  const map = new Map<string, H4CategorySubtotal>()
  for (const r of rows) {
    const cat = (r.category || '未分类').trim() || '未分类'
    const cur = map.get(cat) ?? {
      category: cat,
      beginAmount: 0,
      increaseSubtotal: 0,
      decreaseTotal: 0,
      endAmount: 0,
      impairEnd: 0,
      bookValueEnd: 0,
      auditedBookValue: 0,
      bookValueDiff: 0,
      rowCount: 0,
    }
    cur.beginAmount += r.beginAmount
    cur.increaseSubtotal += r.increaseSubtotal
    cur.decreaseTotal += r.decreaseTotal
    cur.endAmount += r.endAmount
    cur.impairEnd += r.impairEnd
    cur.bookValueEnd += r.bookValueEnd
    cur.auditedBookValue += r.auditedBookValue
    cur.bookValueDiff += r.bookValueDiff
    cur.rowCount += 1
    map.set(cat, cur)
  }
  return [...map.values()].map(c => ({
    ...c,
    beginAmount: Math.round(c.beginAmount * 100) / 100,
    increaseSubtotal: Math.round(c.increaseSubtotal * 100) / 100,
    decreaseTotal: Math.round(c.decreaseTotal * 100) / 100,
    endAmount: Math.round(c.endAmount * 100) / 100,
    impairEnd: Math.round(c.impairEnd * 100) / 100,
    bookValueEnd: Math.round(c.bookValueEnd * 100) / 100,
    auditedBookValue: Math.round(c.auditedBookValue * 100) / 100,
    bookValueDiff: Math.round(c.bookValueDiff * 100) / 100,
  }))
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH4Detail(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  const rows = ref<H4DetailRow[]>([])
  const activeTab = ref<H4DetailTab>('book')
  const selectedRowId = ref<string | null>(null)

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  /** 规范化行（兼容旧字段 quantity / 无数量拆分） */
  function _normalizeRow(raw: any): H4DetailRow {
    const beginQty = _n(raw.beginQty ?? raw.openingQty)
    const increaseQty = _n(raw.increaseQty)
    const decreaseQty = _n(raw.decreaseQty)
    // 旧版单一 quantity → 视为期末数量；若无拆分则期初=期末
    const legacyQty = _n(raw.quantity)
    const resolvedBeginQty = beginQty || (legacyQty && !increaseQty && !decreaseQty ? legacyQty : beginQty)
    const resolvedEndQtyHint = _n(raw.endQty) || legacyQty

    const row: H4DetailRow = {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      category: String(raw.category ?? ''),
      name: String(raw.name ?? ''),
      spec: String(raw.spec ?? ''),
      unit: String(raw.unit ?? ''),
      supplier: String(raw.supplier ?? ''),
      beginQty: resolvedBeginQty,
      increaseQty,
      decreaseQty,
      endQty: 0,
      beginAmount: _n(raw.beginAmount ?? raw.openingAmount),
      purchaseAmount: _n(raw.purchaseAmount ?? raw.purchased),
      otherIncrease: _n(raw.otherIncrease),
      increaseSubtotal: 0,
      usageAmount: _n(raw.usageAmount ?? raw.usedOut),
      returnAmount: _n(raw.returnAmount ?? raw.returned),
      scrapAmount: _n(raw.scrapAmount ?? raw.scrapped),
      otherDecrease: _n(raw.otherDecrease),
      decreaseTotal: 0,
      endAmount: 0,
      beginUnitPrice: null,
      increaseUnitPrice: null,
      decreaseUnitPrice: null,
      endUnitPrice: null,
      ajeBegin: _n(raw.ajeBegin),
      ajeIncrease: _n(raw.ajeIncrease),
      ajeDecrease: _n(raw.ajeDecrease),
      auditedBegin: 0,
      auditedIncrease: 0,
      auditedDecrease: 0,
      auditedEnd: 0,
      impairBegin: _n(raw.impairBegin),
      impairIncrease: _n(raw.impairIncrease),
      impairDecrease: _n(raw.impairDecrease),
      impairEnd: 0,
      ajeImpair: _n(raw.ajeImpair),
      auditedImpairEnd: 0,
      bookValueBegin: 0,
      bookValueEnd: 0,
      auditedBookValue: 0,
      bookValueDiff: 0,
      aging: String(raw.aging ?? ''),
      quality: String(raw.quality ?? ''),
    }

    const computed = recomputeH4DetailRow(row)
    // 若旧数据仅有期末数量且无增减，保持期末=旧 quantity
    if (!increaseQty && !decreaseQty && resolvedEndQtyHint && !beginQty) {
      computed.beginQty = resolvedEndQtyHint
      computed.endQty = resolvedEndQtyHint
      computed.endUnitPrice = calcUnitPrice(computed.endAmount, computed.endQty)
    }
    return computed
  }

  function load(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(_normalizeRow)
    } else {
      rows.value = []
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  const subtotalRow = computed(() => ({
    beginQty: calcSubtotal(rows.value.map(r => r.beginQty)),
    increaseQty: calcSubtotal(rows.value.map(r => r.increaseQty)),
    decreaseQty: calcSubtotal(rows.value.map(r => r.decreaseQty)),
    endQty: calcSubtotal(rows.value.map(r => r.endQty)),
    beginAmount: calcSubtotal(rows.value.map(r => r.beginAmount)),
    purchaseAmount: calcSubtotal(rows.value.map(r => r.purchaseAmount)),
    otherIncrease: calcSubtotal(rows.value.map(r => r.otherIncrease)),
    increaseSubtotal: calcSubtotal(rows.value.map(r => r.increaseSubtotal)),
    usageAmount: calcSubtotal(rows.value.map(r => r.usageAmount)),
    returnAmount: calcSubtotal(rows.value.map(r => r.returnAmount)),
    scrapAmount: calcSubtotal(rows.value.map(r => r.scrapAmount)),
    otherDecrease: calcSubtotal(rows.value.map(r => r.otherDecrease)),
    decreaseTotal: calcSubtotal(rows.value.map(r => r.decreaseTotal)),
    endAmount: calcSubtotal(rows.value.map(r => r.endAmount)),
    ajeBegin: calcSubtotal(rows.value.map(r => r.ajeBegin)),
    ajeIncrease: calcSubtotal(rows.value.map(r => r.ajeIncrease)),
    ajeDecrease: calcSubtotal(rows.value.map(r => r.ajeDecrease)),
    auditedBegin: calcSubtotal(rows.value.map(r => r.auditedBegin)),
    auditedIncrease: calcSubtotal(rows.value.map(r => r.auditedIncrease)),
    auditedDecrease: calcSubtotal(rows.value.map(r => r.auditedDecrease)),
    auditedEnd: calcSubtotal(rows.value.map(r => r.auditedEnd)),
    impairBegin: calcSubtotal(rows.value.map(r => r.impairBegin)),
    impairIncrease: calcSubtotal(rows.value.map(r => r.impairIncrease)),
    impairDecrease: calcSubtotal(rows.value.map(r => r.impairDecrease)),
    impairEnd: calcSubtotal(rows.value.map(r => r.impairEnd)),
    ajeImpair: calcSubtotal(rows.value.map(r => r.ajeImpair)),
    auditedImpairEnd: calcSubtotal(rows.value.map(r => r.auditedImpairEnd)),
    bookValueBegin: calcSubtotal(rows.value.map(r => r.bookValueBegin)),
    bookValueEnd: calcSubtotal(rows.value.map(r => r.bookValueEnd)),
    auditedBookValue: calcSubtotal(rows.value.map(r => r.auditedBookValue)),
    bookValueDiff: calcSubtotal(rows.value.map(r => r.bookValueDiff)),
  }))

  const categorySubtotals: ComputedRef<H4CategorySubtotal[]> = computed(() =>
    buildCategorySubtotals(rows.value),
  )

  const endTotal: ComputedRef<number> = computed(() => subtotalRow.value.endAmount)
  const auditedBookTotal: ComputedRef<number> = computed(() => subtotalRow.value.auditedBookValue)
  const hasMaterialDiff: ComputedRef<boolean> = computed(() =>
    Math.abs(subtotalRow.value.bookValueDiff) >= 0.01,
  )

  function addRow(name: string): void {
    if (!name?.trim()) return
    rows.value.push(_normalizeRow({ name: name.trim() }))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    _persist()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    const row = { ...rows.value[idx] }

    if ((TEXT_FIELDS as readonly string[]).includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      rows.value[idx] = recomputeH4DetailRow(row)
      _persist()
      return
    }

    if ((NUM_FIELDS as readonly string[]).includes(field)) {
      ;(row as any)[field] = _n(value)
      rows.value[idx] = recomputeH4DetailRow(row)
      _persist()
    }
  }

  function setActiveTab(tab: H4DetailTab): void {
    activeTab.value = tab
  }

  function selectRow(rowId: string | null): void {
    selectedRowId.value = rowId
  }

  function save(): void { _persist() }

  function _rowToPersist(r: H4DetailRow) {
    return {
      rowId: r.rowId,
      category: r.category,
      name: r.name,
      spec: r.spec,
      unit: r.unit,
      supplier: r.supplier,
      quantity: r.endQty,
      beginQty: r.beginQty,
      increaseQty: r.increaseQty,
      decreaseQty: r.decreaseQty,
      beginAmount: r.beginAmount,
      purchaseAmount: r.purchaseAmount,
      otherIncrease: r.otherIncrease,
      usageAmount: r.usageAmount,
      returnAmount: r.returnAmount,
      scrapAmount: r.scrapAmount,
      otherDecrease: r.otherDecrease,
      increaseSubtotal: r.increaseSubtotal,
      decreaseTotal: r.decreaseTotal,
      endAmount: r.endAmount,
      endQty: r.endQty,
      ajeBegin: r.ajeBegin,
      ajeIncrease: r.ajeIncrease,
      ajeDecrease: r.ajeDecrease,
      impairBegin: r.impairBegin,
      impairIncrease: r.impairIncrease,
      impairDecrease: r.impairDecrease,
      impairEnd: r.impairEnd,
      ajeImpair: r.ajeImpair,
      auditedEnd: r.auditedEnd,
      auditedBookValue: r.auditedBookValue,
      bookValueEnd: r.bookValueEnd,
      bookValueDiff: r.bookValueDiff,
      aging: r.aging,
      quality: r.quality,
    }
  }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.map(_rowToPersist)
    onSave(ROWS_KEY, toPersist)
    onSave(DETAIL_TOTAL_KEY, endTotal.value)
    onSave(DETAIL_INCREASE_KEY, subtotalRow.value.increaseSubtotal)
    onSave(DETAIL_DECREASE_KEY, subtotalRow.value.decreaseTotal)
    onSave(DETAIL_IMPAIR_KEY, subtotalRow.value.impairEnd)
  }

  const H43_ROWS_KEY = 'H4-3-rows'

  /** 将明细行级 AJE 推送为 H4-3 借贷平衡草稿（替换旧自动行） */
  function pushAjeToH43(): { ok: boolean; added: number; cleared: number; message: string } {
    if (!onSave) return { ok: false, added: 0, cleared: 0, message: '无保存通道' }
    const hasAje = rows.value.some(r =>
      Math.abs(r.ajeBegin) + Math.abs(r.ajeIncrease) + Math.abs(r.ajeDecrease) + Math.abs(r.ajeImpair) >= 0.005,
    )
    if (!hasAje) {
      return { ok: false, added: 0, cleared: 0, message: '明细暂无 AJE 金额，无需推送' }
    }
    const existing = _getJson(H43_ROWS_KEY)
    const { rows: merged, added, cleared } = mergeH42AjeIntoH43(
      Array.isArray(existing) ? existing : [],
      rows.value,
    )
    onSave(H43_ROWS_KEY, merged)
    _persist()
    return {
      ok: true,
      added,
      cleared,
      message: `已向 H4-3 推送 ${added} 行 AJE 草稿（清除旧自动行 ${cleared}）`,
    }
  }

  /** 从 H4-3 自动行回写明细 AJE 字段 */
  function pullAjeFromH43(): { ok: boolean; updated: number; matchedLines: number; message: string } {
    if (!onSave) return { ok: false, updated: 0, matchedLines: 0, message: '无保存通道' }
    const existing = _getJson(H43_ROWS_KEY)
    if (!Array.isArray(existing) || existing.length === 0) {
      return { ok: false, updated: 0, matchedLines: 0, message: 'H4-3 暂无分录' }
    }
    const { rows: next, updated, matchedLines } = applyH43AjeBackToDetails(rows.value, existing)
    if (matchedLines === 0) {
      return { ok: false, updated: 0, matchedLines: 0, message: 'H4-3 无 H4-2 自动推送分录可回写' }
    }
    rows.value = next.map(recomputeH4DetailRow)
    _persist()
    return {
      ok: true,
      updated,
      matchedLines,
      message: updated > 0
        ? `已从 H4-3 回写 ${updated} 行明细 AJE（匹配 ${matchedLines} 条 1605 自动行）`
        : `已核对：明细 AJE 与 H4-3 自动行一致（${matchedLines} 条）`,
    }
  }

  return {
    rows,
    activeTab,
    selectedRowId,
    subtotalRow,
    categorySubtotals,
    endTotal,
    auditedBookTotal,
    hasMaterialDiff,
    addRow,
    deleteRow,
    updateCell,
    setActiveTab,
    selectRow,
    save,
    load,
    pushAjeToH43,
    pullAjeFromH43,
  }
}

export default useH4Detail
