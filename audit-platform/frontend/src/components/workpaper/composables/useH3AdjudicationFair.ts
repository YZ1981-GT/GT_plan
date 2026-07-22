/**
 * useH3AdjudicationFair — H3-1 审定表（公允价值模式）composable
 *
 * 单区块公允 + H3-2 按类别回填（book/full）+ H3-6 转换回填 + H3-8 勾稽
 */
import { ref, computed, watch, onMounted, onUnmounted, getCurrentInstance, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import {
  calcAuditedAmount,
  calcFairEndBalance,
  calcSubtotal,
} from './useH3FormulaEngine'
import { normalizeH3Category, H3_ASSET_CATEGORIES } from './h3CategoryMap'
import {
  aggregateH32FairByCategory,
  allocateTransferByWeight,
  previewFairFillDiff,
  type H3FillDiffRow,
  type H3FillMode,
} from './h3FillFromDetail'

const G_CYCLE_SOURCE_FV_EVENT = 'g-cycle:source-fv'

function publishH3SourceFv(amount: number): void {
  try {
    window.dispatchEvent(
      new CustomEvent(G_CYCLE_SOURCE_FV_EVENT, {
        detail: { source: 'H3', amount },
      }),
    )
    window.dispatchEvent(
      new CustomEvent('h3:fair-value-changed', {
        detail: { source: 'H3', totalFairValueChange: amount },
      }),
    )
  } catch { /* best effort */ }
}

export interface H3FairAdjRow {
  rowId: string
  category: string
  beginFair: number
  increase: number
  decrease: number
  transfer: number
  fairValueChange: number
  endFair: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
}

const ITEM_ID_FAIR_ROWS = 'H3-1-fair-rows'
const ITEM_H38_ROWS = 'H3-8-calc-rows'

export interface H31H38Reconcile {
  h31Audited: number
  h38Ending: number
  h38AuditorFv: number
  diffAudited: number
  matched: boolean
  hasH38Data: boolean
  note: string
}

export type { H3FillMode, H3FillDiffRow }

export function useH3AdjudicationFair(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params
  const rows = ref<H3FairAdjRow[]>([])

  function loadRows(): void {
    const raw = getValue(ITEM_ID_FAIR_ROWS)
    rows.value = Array.isArray(raw) ? raw.map(_normalizeRow) : _defaultRows()
  }

  function _normalizeRow(raw: any): H3FairAdjRow {
    const begin = Number(raw.beginFair) || 0
    const inc = Number(raw.increase) || 0
    const dec = Number(raw.decrease) || 0
    const trans = Number(raw.transfer) || 0
    const change = Number(raw.fairValueChange) || 0
    const end = calcFairEndBalance(begin, inc, dec, trans, change)
    const unadj = Number(raw.unadjusted) || 0
    const aje = Number(raw.aje) || 0
    const rje = Number(raw.rje) || 0
    return {
      rowId: raw.rowId ?? `fair-${Math.random().toString(36).slice(2, 8)}`,
      category: raw.category ?? '',
      beginFair: begin,
      increase: inc,
      decrease: dec,
      transfer: trans,
      fairValueChange: change,
      endFair: end,
      unadjusted: unadj,
      aje,
      rje,
      audited: calcAuditedAmount(unadj, aje, rje),
    }
  }

  function _defaultRows(): H3FairAdjRow[] {
    return H3_ASSET_CATEGORIES.map((cat) => _normalizeRow({ category: cat }))
  }

  function _ensureCategoryRows(): void {
    if (!rows.value.length) rows.value = _defaultRows()
    const have = new Set(rows.value.map((r) => normalizeH3Category(r.category)))
    for (const cat of H3_ASSET_CATEGORIES) {
      if (!have.has(cat)) rows.value.push(_normalizeRow({ category: cat }))
    }
  }

  const total = computed(() => ({
    beginFair: calcSubtotal(rows.value.map((r) => r.beginFair)),
    increase: calcSubtotal(rows.value.map((r) => r.increase)),
    decrease: calcSubtotal(rows.value.map((r) => r.decrease)),
    transfer: calcSubtotal(rows.value.map((r) => r.transfer)),
    fairValueChange: calcSubtotal(rows.value.map((r) => r.fairValueChange)),
    endFair: calcSubtotal(rows.value.map((r) => r.endFair)),
    unadjusted: calcSubtotal(rows.value.map((r) => r.unadjusted)),
    aje: calcSubtotal(rows.value.map((r) => r.aje)),
    rje: calcSubtotal(rows.value.map((r) => r.rje)),
    audited: calcSubtotal(rows.value.map((r) => r.audited)),
  }))

  const fairBalanceErrors = computed(() =>
    rows.value.map((r) => {
      const expected = calcFairEndBalance(r.beginFair, r.increase, r.decrease, r.transfer, r.fairValueChange)
      return r.endFair - expected
    }),
  )
  const isFairBalanced = computed(() =>
    fairBalanceErrors.value.every((e) => Math.abs(e) < 0.01),
  )
  const fairValueChangePL = computed(() =>
    calcSubtotal(rows.value.map((r) => r.fairValueChange)),
  )

  const h32CategoryMatch = computed(() => {
    const detail = getValue('H3-2-fair-rows')
    if (!Array.isArray(detail) || !detail.length) {
      return { unmatchedEnd: 0, unmatchedCount: 0 }
    }
    const { unmatchedEnd, unmatchedCount } = aggregateH32FairByCategory(detail)
    return { unmatchedEnd, unmatchedCount }
  })

  const h38Reconcile = computed<H31H38Reconcile>(() => {
    const raw = getValue(ITEM_H38_ROWS)
    const h38Rows = Array.isArray(raw) ? raw : []
    const h38Ending = h38Rows.reduce((s: number, r: any) => {
      return s + (Number(r.endingBalance ?? r.appraisalValue ?? r.bookValue) || 0)
    }, 0)
    const h38AuditorFv = h38Rows.reduce((s: number, r: any) => {
      const area = Number(r.area) || 0
      const ref = Number(r.refUnitPrice ?? r.marketRef) || 0
      const fv = Number(r.auditorFairValue)
      return s + (fv || area * ref)
    }, 0)
    const h31Audited = total.value.audited || total.value.endFair
    const diffAudited = h31Audited - h38Ending
    const hasH38Data = h38Rows.length > 0 && h38Ending > 0
    const matched = hasH38Data && Math.abs(diffAudited) < 0.01
    return {
      h31Audited,
      h38Ending,
      h38AuditorFv,
      diffAudited,
      matched,
      hasH38Data,
      note: !hasH38Data
        ? 'H3-8 公允价值复核表尚未编制或无期末余额，请先完成 H3-8。'
        : matched
          ? 'H3-1 审定数与 H3-8 期末余额合计勾稽一致。'
          : `H3-1 审定数 ${h31Audited.toLocaleString('zh-CN')} 与 H3-8 期末合计 ${h38Ending.toLocaleString('zh-CN')} 差异 ${diffAudited.toLocaleString('zh-CN')}，请核对。`,
    }
  })

  function updateCell(rowId: string, field: keyof H3FairAdjRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = typeof value === 'number' ? value : Number(value) || 0
    row.endFair = calcFairEndBalance(row.beginFair, row.increase, row.decrease, row.transfer, row.fairValueChange)
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
    _persist()
    if (
      field === 'fairValueChange'
      || field === 'beginFair'
      || field === 'increase'
      || field === 'decrease'
      || field === 'transfer'
    ) {
      publishH3SourceFv(fairValueChangePL.value)
    }
  }

  function previewFillFromH32(mode: H3FillMode = 'book'): {
    diffs: H3FillDiffRow[]
    unmatchedCount: number
    unmatchedEnd: number
    empty: boolean
  } {
    const detail = getValue('H3-2-fair-rows')
    if (!Array.isArray(detail) || detail.length === 0) {
      return { diffs: [], unmatchedCount: 0, unmatchedEnd: 0, empty: true }
    }
    _ensureCategoryRows()
    const { map, unmatchedCount, unmatchedEnd } = aggregateH32FairByCategory(detail)
    return {
      diffs: previewFairFillDiff({ rows: rows.value, map, mode }),
      unmatchedCount,
      unmatchedEnd,
      empty: false,
    }
  }

  function fillFromH32Detail(mode: H3FillMode = 'book'): { filled: number; unmatchedCount: number } {
    const detail = getValue('H3-2-fair-rows')
    if (!Array.isArray(detail) || detail.length === 0) {
      return { filled: 0, unmatchedCount: 0 }
    }
    const { map, unmatchedCount } = aggregateH32FairByCategory(detail)
    _ensureCategoryRows()

    let filled = 0
    rows.value = rows.value.map((row) => {
      const cat = normalizeH3Category(row.category)
      const a = map[cat]
      filled++
      const unadj = mode === 'full' ? a.unadj : a.end
      const aje = mode === 'full' ? a.aje : row.aje
      const rje = mode === 'full' ? a.rje : row.rje
      return _normalizeRow({
        ...row,
        category: row.category || cat,
        beginFair: a.begin,
        increase: a.increase,
        decrease: a.decrease,
        transfer: a.transfer,
        fairValueChange: a.fvChange,
        endFair: a.end,
        unadjusted: unadj,
        aje,
        rje,
      })
    })

    _persist()
    publishH3SourceFv(fairValueChangePL.value)
    return { filled, unmatchedCount }
  }

  function fillTransferFromH36(netTransfer: number): { filled: number } {
    _ensureCategoryRows()
    const weights = rows.value.map((r) => ({
      category: r.category,
      weight: Math.abs(r.endFair) || Math.abs(r.beginFair) || 0,
    }))
    const alloc = allocateTransferByWeight(weights, netTransfer)
    rows.value = rows.value.map((row) => {
      const cat = normalizeH3Category(row.category)
      return _normalizeRow({
        ...row,
        transfer: alloc[cat] || 0,
      })
    })
    _persist()
    publishH3SourceFv(fairValueChangePL.value)
    return { filled: rows.value.length }
  }

  function _persist(): void {
    setValue(ITEM_ID_FAIR_ROWS, rows.value)
  }

  watch(allResponses, () => loadRows(), { immediate: true })
  watch(fairValueChangePL, (amount) => { publishH3SourceFv(amount) })

  if (getCurrentInstance()) {
    const onAdj = () => loadRows()
    onMounted(() => {
      publishH3SourceFv(fairValueChangePL.value)
      window.addEventListener('adjustment:created', onAdj)
    })
    onUnmounted(() => {
      window.removeEventListener('adjustment:created', onAdj)
    })
  }

  return {
    rows,
    total,
    fairBalanceErrors,
    isFairBalanced,
    fairValueChangePL,
    h38Reconcile,
    h32CategoryMatch,
    updateCell,
    previewFillFromH32,
    fillFromH32Detail,
    fillTransferFromH36,
    loadRows,
    publishH3SourceFv: () => publishH3SourceFv(fairValueChangePL.value),
  }
}

export default useH3AdjudicationFair
