/**
 * useH3AdjudicationCost — H3-1 审定表（成本模式）composable
 *
 * 双区块（原值+折旧）+ 10列50公式 + 三角勾稽校验 + TB回写1503+1504 + 交叉验证H3-2
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.4
 * Requirements: 2.1-2.9
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import {
  calcAuditedAmount,
  calcCostTriangle,
  calcSubtotal,
} from './useH3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 成本模式审定表行 — 原值区块 */
export interface H3CostOriginalRow {
  rowId: string
  category: string          // 分类（房屋/建筑物/土地使用权…）
  beginBalance: number      // 期初
  increase: number          // 增加
  decrease: number          // 减少
  transfer: number          // 转换（±）
  endBalance: number        // 期末（公式：期初+增加-减少±转换）
  unadjusted: number        // 未审数
  aje: number               // AJE
  rje: number               // RJE
  audited: number           // 审定数（未审+AJE+RJE）
}

/** 成本模式审定表行 — 累计折旧区块 */
export interface H3CostDepRow {
  rowId: string
  category: string
  beginBalance: number      // 期初
  provision: number         // 本期计提
  reversal: number          // 转回
  transferDep: number       // 转换折旧
  endBalance: number        // 期末
  unadjusted: number
  aje: number
  rje: number
  audited: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_COST_ORIGINAL = 'H3-1-cost-original-rows'
const ITEM_ID_COST_DEP = 'H3-1-cost-dep-rows'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH3AdjudicationCost(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const originalRows = ref<H3CostOriginalRow[]>([])
  const depRows = ref<H3CostDepRow[]>([])

  // ─── Load ──────────────────────────────────────────────────────────────────

  function loadRows(): void {
    const origRaw = getValue(ITEM_ID_COST_ORIGINAL)
    originalRows.value = Array.isArray(origRaw)
      ? origRaw.map(_normalizeOriginalRow)
      : _defaultOriginalRows()

    const depRaw = getValue(ITEM_ID_COST_DEP)
    depRows.value = Array.isArray(depRaw)
      ? depRaw.map(_normalizeDepRow)
      : _defaultDepRows()
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

  function _defaultOriginalRows(): H3CostOriginalRow[] {
    const categories = ['房屋及建筑物', '土地使用权', '其他']
    return categories.map((cat) => _normalizeOriginalRow({ category: cat }))
  }

  function _defaultDepRows(): H3CostDepRow[] {
    const categories = ['房屋及建筑物', '土地使用权', '其他']
    return categories.map((cat) => _normalizeDepRow({ category: cat }))
  }

  // ─── Computed Totals ───────────────────────────────────────────────────────

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

  /** 净值合计 = 原值期末 - 折旧期末 */
  const netValueTotal = computed(() => originalTotal.value.endBalance - depTotal.value.endBalance)

  // ─── 三角勾稽校验 ─────────────────────────────────────────────────────────

  /** 原值三角勾稽差额（每行） */
  const originalTriangleErrors = computed(() =>
    originalRows.value.map((r) => calcCostTriangle(r.beginBalance, r.increase, r.decrease, r.transfer, r.endBalance)),
  )

  /** 折旧三角勾稽差额（每行） */
  const depTriangleErrors = computed(() =>
    depRows.value.map((r) => calcCostTriangle(r.beginBalance, r.provision, r.reversal, r.transferDep, r.endBalance)),
  )

  /** 是否全部勾稽平衡 */
  const isTriangleBalanced = computed(() =>
    originalTriangleErrors.value.every((e) => Math.abs(e) < 0.01)
    && depTriangleErrors.value.every((e) => Math.abs(e) < 0.01),
  )

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateOriginalCell(rowId: string, field: keyof H3CostOriginalRow, value: any): void {
    const row = originalRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = typeof value === 'number' ? value : Number(value) || 0
    // 重算公式列
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

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    setValue(ITEM_ID_COST_ORIGINAL, originalRows.value)
    setValue(ITEM_ID_COST_DEP, depRows.value)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => loadRows(), { immediate: true })

  return {
    originalRows,
    depRows,
    originalTotal,
    depTotal,
    netValueTotal,
    originalTriangleErrors,
    depTriangleErrors,
    isTriangleBalanced,
    updateOriginalCell,
    updateDepCell,
    loadRows,
  }
}

export default useH3AdjudicationCost
