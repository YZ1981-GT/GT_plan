/**
 * useH3AdjudicationCost — H3-1 审定表（成本模式）composable
 *
 * 三区块（原值+折旧+减值）+ 三角勾稽 + H3-2 按类别回填（book/full）+ H3-6 转换回填
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.4
 * Requirements: 2.1-2.9
 */
import { ref, computed, watch, onMounted, onUnmounted, getCurrentInstance, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import {
  calcAuditedAmount,
  calcCostTriangle,
  calcSubtotal,
} from './useH3FormulaEngine'
import { normalizeH3Category, H3_ASSET_CATEGORIES, type H3AssetCategory } from './h3CategoryMap'
import {
  aggregateH32CostByCategory,
  allocateTransferByWeight,
  previewCostFillDiff,
  type H3FillDiffRow,
  type H3FillMode,
} from './h3FillFromDetail'

export interface H3CostOriginalRow {
  rowId: string
  category: string
  beginBalance: number
  increase: number
  decrease: number
  transfer: number
  endBalance: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
}

export interface H3CostDepRow {
  rowId: string
  category: string
  beginBalance: number
  provision: number
  reversal: number
  transferDep: number
  endBalance: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
}

/** 成本模式审定表行 — 减值准备区块（1505） */
export interface H3CostImpairRow {
  rowId: string
  category: string
  beginBalance: number
  provision: number
  reversal: number
  transferImp: number
  endBalance: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
}

const ITEM_ID_COST_ORIGINAL = 'H3-1-cost-original-rows'
const ITEM_ID_COST_DEP = 'H3-1-cost-dep-rows'
const ITEM_ID_COST_IMPAIR = 'H3-1-cost-impair-rows'

export type { H3FillMode, H3FillDiffRow }

export function useH3AdjudicationCost(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params

  const originalRows = ref<H3CostOriginalRow[]>([])
  const depRows = ref<H3CostDepRow[]>([])
  const impairRows = ref<H3CostImpairRow[]>([])

  function loadRows(): void {
    const origRaw = getValue(ITEM_ID_COST_ORIGINAL)
    originalRows.value = Array.isArray(origRaw)
      ? origRaw.map(_normalizeOriginalRow)
      : _defaultOriginalRows()

    const depRaw = getValue(ITEM_ID_COST_DEP)
    depRows.value = Array.isArray(depRaw)
      ? depRaw.map(_normalizeDepRow)
      : _defaultDepRows()

    const impRaw = getValue(ITEM_ID_COST_IMPAIR)
    impairRows.value = Array.isArray(impRaw)
      ? impRaw.map(_normalizeImpairRow)
      : _defaultImpairRows()
  }

  function _normalizeOriginalRow(raw: any): H3CostOriginalRow {
    const begin = Number(raw.beginBalance) || 0
    const inc = Number(raw.increase) || 0
    const dec = Number(raw.decrease) || 0
    const trans = Number(raw.transfer) || 0
    const end = begin + inc - dec + trans
    const unadj = Number(raw.unadjusted) || 0
    const aje = Number(raw.aje) || 0
    const rje = Number(raw.rje) || 0
    return {
      rowId: raw.rowId ?? `orig-${Math.random().toString(36).slice(2, 8)}`,
      category: raw.category ?? '',
      beginBalance: begin,
      increase: inc,
      decrease: dec,
      transfer: trans,
      endBalance: end,
      unadjusted: unadj,
      aje,
      rje,
      audited: calcAuditedAmount(unadj, aje, rje),
    }
  }

  function _normalizeDepRow(raw: any): H3CostDepRow {
    const begin = Number(raw.beginBalance) || 0
    const prov = Number(raw.provision) || 0
    const rev = Number(raw.reversal) || 0
    const trans = Number(raw.transferDep) || 0
    const end = begin + prov - rev + trans
    const unadj = Number(raw.unadjusted) || 0
    const aje = Number(raw.aje) || 0
    const rje = Number(raw.rje) || 0
    return {
      rowId: raw.rowId ?? `dep-${Math.random().toString(36).slice(2, 8)}`,
      category: raw.category ?? '',
      beginBalance: begin,
      provision: prov,
      reversal: rev,
      transferDep: trans,
      endBalance: end,
      unadjusted: unadj,
      aje,
      rje,
      audited: calcAuditedAmount(unadj, aje, rje),
    }
  }

  function _normalizeImpairRow(raw: any): H3CostImpairRow {
    const begin = Number(raw.beginBalance) || 0
    const prov = Number(raw.provision) || 0
    const rev = Number(raw.reversal) || 0
    const trans = Number(raw.transferImp) || 0
    const end = begin + prov - rev + trans
    const unadj = Number(raw.unadjusted) || 0
    const aje = Number(raw.aje) || 0
    const rje = Number(raw.rje) || 0
    return {
      rowId: raw.rowId ?? `imp-${Math.random().toString(36).slice(2, 8)}`,
      category: raw.category ?? '',
      beginBalance: begin,
      provision: prov,
      reversal: rev,
      transferImp: trans,
      endBalance: end,
      unadjusted: unadj,
      aje,
      rje,
      audited: calcAuditedAmount(unadj, aje, rje),
    }
  }

  function _defaultOriginalRows(): H3CostOriginalRow[] {
    return H3_ASSET_CATEGORIES.map((cat) => _normalizeOriginalRow({ category: cat }))
  }
  function _defaultDepRows(): H3CostDepRow[] {
    return H3_ASSET_CATEGORIES.map((cat) => _normalizeDepRow({ category: cat }))
  }
  function _defaultImpairRows(): H3CostImpairRow[] {
    return H3_ASSET_CATEGORIES.map((cat) => _normalizeImpairRow({ category: cat }))
  }

  function _ensureCategoryRows(): void {
    if (!originalRows.value.length) originalRows.value = _defaultOriginalRows()
    if (!depRows.value.length) depRows.value = _defaultDepRows()
    if (!impairRows.value.length) impairRows.value = _defaultImpairRows()
    const ensure = <T extends { category: string }>(
      rows: T[],
      factory: (cat: H3AssetCategory) => T,
    ): T[] => {
      const have = new Set(rows.map((r) => normalizeH3Category(r.category)))
      const next = [...rows]
      for (const cat of H3_ASSET_CATEGORIES) {
        if (!have.has(cat)) next.push(factory(cat))
      }
      return next
    }
    originalRows.value = ensure(originalRows.value, (cat) => _normalizeOriginalRow({ category: cat }))
    depRows.value = ensure(depRows.value, (cat) => _normalizeDepRow({ category: cat }))
    impairRows.value = ensure(impairRows.value, (cat) => _normalizeImpairRow({ category: cat }))
  }

  const originalTotal = computed(() => ({
    beginBalance: calcSubtotal(originalRows.value.map((r) => r.beginBalance)),
    increase: calcSubtotal(originalRows.value.map((r) => r.increase)),
    decrease: calcSubtotal(originalRows.value.map((r) => r.decrease)),
    transfer: calcSubtotal(originalRows.value.map((r) => r.transfer)),
    endBalance: calcSubtotal(originalRows.value.map((r) => r.endBalance)),
    unadjusted: calcSubtotal(originalRows.value.map((r) => r.unadjusted)),
    aje: calcSubtotal(originalRows.value.map((r) => r.aje)),
    rje: calcSubtotal(originalRows.value.map((r) => r.rje)),
    audited: calcSubtotal(originalRows.value.map((r) => r.audited)),
  }))

  const depTotal = computed(() => ({
    beginBalance: calcSubtotal(depRows.value.map((r) => r.beginBalance)),
    provision: calcSubtotal(depRows.value.map((r) => r.provision)),
    reversal: calcSubtotal(depRows.value.map((r) => r.reversal)),
    transferDep: calcSubtotal(depRows.value.map((r) => r.transferDep)),
    endBalance: calcSubtotal(depRows.value.map((r) => r.endBalance)),
    unadjusted: calcSubtotal(depRows.value.map((r) => r.unadjusted)),
    aje: calcSubtotal(depRows.value.map((r) => r.aje)),
    rje: calcSubtotal(depRows.value.map((r) => r.rje)),
    audited: calcSubtotal(depRows.value.map((r) => r.audited)),
  }))

  const impairTotal = computed(() => ({
    beginBalance: calcSubtotal(impairRows.value.map((r) => r.beginBalance)),
    provision: calcSubtotal(impairRows.value.map((r) => r.provision)),
    reversal: calcSubtotal(impairRows.value.map((r) => r.reversal)),
    transferImp: calcSubtotal(impairRows.value.map((r) => r.transferImp)),
    endBalance: calcSubtotal(impairRows.value.map((r) => r.endBalance)),
    unadjusted: calcSubtotal(impairRows.value.map((r) => r.unadjusted)),
    aje: calcSubtotal(impairRows.value.map((r) => r.aje)),
    rje: calcSubtotal(impairRows.value.map((r) => r.rje)),
    audited: calcSubtotal(impairRows.value.map((r) => r.audited)),
  }))

  const netValueTotal = computed(
    () => originalTotal.value.endBalance - depTotal.value.endBalance - impairTotal.value.endBalance,
  )

  const originalTriangleErrors = computed(() =>
    originalRows.value.map((r) => calcCostTriangle(r.beginBalance, r.increase, r.decrease, r.transfer, r.endBalance)),
  )
  const depTriangleErrors = computed(() =>
    depRows.value.map((r) => calcCostTriangle(r.beginBalance, r.provision, r.reversal, r.transferDep, r.endBalance)),
  )
  const impairTriangleErrors = computed(() =>
    impairRows.value.map((r) => calcCostTriangle(r.beginBalance, r.provision, r.reversal, r.transferImp, r.endBalance)),
  )
  const isTriangleBalanced = computed(() =>
    originalTriangleErrors.value.every((e) => Math.abs(e) < 0.01)
    && depTriangleErrors.value.every((e) => Math.abs(e) < 0.01)
    && impairTriangleErrors.value.every((e) => Math.abs(e) < 0.01),
  )

  /** H3-2 未匹配标准类别的明细金额（勾稽提示） */
  const h32CategoryMatch = computed(() => {
    const detail = getValue('H3-2-cost-rows')
    if (!Array.isArray(detail) || !detail.length) {
      return { unmatchedEnd: 0, unmatchedCount: 0 }
    }
    const { unmatchedEnd, unmatchedCount } = aggregateH32CostByCategory(detail)
    return { unmatchedEnd, unmatchedCount }
  })

  function updateOriginalCell(rowId: string, field: keyof H3CostOriginalRow, value: any): void {
    const row = originalRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = typeof value === 'number' ? value : Number(value) || 0
    row.endBalance = row.beginBalance + row.increase - row.decrease + row.transfer
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
    _persist()
  }

  function updateDepCell(rowId: string, field: keyof H3CostDepRow, value: any): void {
    const row = depRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = typeof value === 'number' ? value : Number(value) || 0
    row.endBalance = row.beginBalance + row.provision - row.reversal + row.transferDep
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
    _persist()
  }

  function updateImpairCell(rowId: string, field: keyof H3CostImpairRow, value: any): void {
    const row = impairRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = typeof value === 'number' ? value : Number(value) || 0
    row.endBalance = row.beginBalance + row.provision - row.reversal + row.transferImp
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
    _persist()
  }

  function previewFillFromH32(mode: H3FillMode = 'book'): {
    diffs: H3FillDiffRow[]
    unmatchedCount: number
    unmatchedEnd: number
    empty: boolean
  } {
    const detail = getValue('H3-2-cost-rows')
    if (!Array.isArray(detail) || detail.length === 0) {
      return { diffs: [], unmatchedCount: 0, unmatchedEnd: 0, empty: true }
    }
    _ensureCategoryRows()
    const { map, unmatchedCount, unmatchedEnd } = aggregateH32CostByCategory(detail)
    const diffs = previewCostFillDiff({
      originalRows: originalRows.value,
      depRows: depRows.value,
      impairRows: impairRows.value,
      map,
      mode,
    })
    return { diffs, unmatchedCount, unmatchedEnd, empty: false }
  }

  /**
   * 从 H3-2 按类别回填。默认 book：不覆盖 AJE/RJE（留给 H3-3）。
   */
  function fillFromH32Detail(mode: H3FillMode = 'book'): {
    originalFilled: number
    depFilled: number
    impairFilled: number
    unmatchedCount: number
  } {
    const detail = getValue('H3-2-cost-rows')
    if (!Array.isArray(detail) || detail.length === 0) {
      return { originalFilled: 0, depFilled: 0, impairFilled: 0, unmatchedCount: 0 }
    }
    const { map, unmatchedCount } = aggregateH32CostByCategory(detail)
    _ensureCategoryRows()

    let originalFilled = 0
    originalRows.value = originalRows.value.map((row) => {
      const cat = normalizeH3Category(row.category)
      const a = map[cat]
      originalFilled++
      const unadj = mode === 'full' ? a.unadj : a.end
      const aje = mode === 'full' ? a.aje : row.aje
      const rje = mode === 'full' ? a.rje : row.rje
      return _normalizeOriginalRow({
        ...row,
        category: row.category || cat,
        beginBalance: a.begin,
        increase: a.increase,
        decrease: a.decrease,
        transfer: a.transfer,
        endBalance: a.end,
        unadjusted: unadj,
        aje,
        rje,
      })
    })

    let depFilled = 0
    depRows.value = depRows.value.map((row) => {
      const cat = normalizeH3Category(row.category)
      const a = map[cat]
      depFilled++
      const unadj = mode === 'full' ? a.depUnadj : a.depEnd
      const aje = mode === 'full' ? a.depAje : row.aje
      const rje = mode === 'full' ? a.depRje : row.rje
      return _normalizeDepRow({
        ...row,
        category: row.category || cat,
        beginBalance: a.depBegin,
        provision: a.depProv,
        reversal: a.depRev,
        transferDep: 0,
        endBalance: a.depEnd,
        unadjusted: unadj,
        aje,
        rje,
      })
    })

    let impairFilled = 0
    impairRows.value = impairRows.value.map((row) => {
      const cat = normalizeH3Category(row.category)
      const a = map[cat]
      impairFilled++
      const unadj = mode === 'full' ? a.impUnadj : a.impEnd
      const aje = mode === 'full' ? a.impAje : row.aje
      const rje = mode === 'full' ? a.impRje : row.rje
      return _normalizeImpairRow({
        ...row,
        category: row.category || cat,
        beginBalance: a.impBegin,
        provision: a.impProv,
        reversal: a.impRev,
        transferImp: 0,
        endBalance: a.impEnd,
        unadjusted: unadj,
        aje,
        rje,
      })
    })

    _persist()
    return { originalFilled, depFilled, impairFilled, unmatchedCount }
  }

  /** 按期末原值权重把 H3-6 净转入分摊到转换列 */
  function fillTransferFromH36(netTransfer: number): { filled: number } {
    _ensureCategoryRows()
    const weights = originalRows.value.map((r) => ({
      category: r.category,
      weight: Math.abs(r.endBalance) || Math.abs(r.beginBalance) || 0,
    }))
    const alloc = allocateTransferByWeight(weights, netTransfer)
    originalRows.value = originalRows.value.map((row) => {
      const cat = normalizeH3Category(row.category)
      return _normalizeOriginalRow({
        ...row,
        transfer: alloc[cat] || 0,
      })
    })
    _persist()
    return { filled: originalRows.value.length }
  }

  function _persist(): void {
    setValue(ITEM_ID_COST_ORIGINAL, originalRows.value)
    setValue(ITEM_ID_COST_DEP, depRows.value)
    setValue(ITEM_ID_COST_IMPAIR, impairRows.value)
  }

  watch(allResponses, () => loadRows(), { immediate: true })

  if (getCurrentInstance()) {
    const onAdj = () => loadRows()
    onMounted(() => {
      window.addEventListener('adjustment:created', onAdj)
    })
    onUnmounted(() => {
      window.removeEventListener('adjustment:created', onAdj)
    })
  }

  return {
    originalRows,
    depRows,
    impairRows,
    originalTotal,
    depTotal,
    impairTotal,
    netValueTotal,
    originalTriangleErrors,
    depTriangleErrors,
    impairTriangleErrors,
    isTriangleBalanced,
    h32CategoryMatch,
    updateOriginalCell,
    updateDepCell,
    updateImpairCell,
    previewFillFromH32,
    fillFromH32Detail,
    fillTransferFromH36,
    loadRows,
  }
}

export default useH3AdjudicationCost
