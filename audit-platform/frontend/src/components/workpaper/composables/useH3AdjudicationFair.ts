/**
 * useH3AdjudicationFair — H3-1 审定表（公允价值模式）composable
 *
 * 单区块（公允价值）+ 10列50公式 + 公允模式校验 + TB回写1503 + 交叉验证H3-2
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.5
 * Requirements: 2.1-2.9
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import {
  calcAuditedAmount,
  calcFairEndBalance,
  calcFairValueChange,
  calcSubtotal,
} from './useH3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H3FairAdjRow {
  rowId: string
  category: string            // 分类
  beginFair: number           // 期初公允价值
  increase: number            // 本期增加
  decrease: number            // 本期减少
  transfer: number            // 转换（±）
  fairValueChange: number     // 公允价值变动
  endFair: number             // 期末公允（公式：期初+增加-减少±转换+变动）
  unadjusted: number          // 未审数
  aje: number                 // AJE
  rje: number                 // RJE
  audited: number             // 审定数
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_FAIR_ROWS = 'H3-1-fair-rows'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH3AdjudicationFair(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H3FairAdjRow[]>([])

  // ─── Load ──────────────────────────────────────────────────────────────────

  function loadRows(): void {
    const raw = getValue(ITEM_ID_FAIR_ROWS)
    rows.value = Array.isArray(raw)
      ? raw.map(_normalizeRow)
      : _defaultRows()
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
    const categories = ['房屋及建筑物', '土地使用权', '其他']
    return categories.map((cat) => _normalizeRow({ category: cat }))
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

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

  /** 公允模式校验：期末公允 = 期初+增加-减少±转换+变动（差额=0即平衡） */
  const fairBalanceErrors = computed(() =>
    rows.value.map((r) => {
      const expected = calcFairEndBalance(r.beginFair, r.increase, r.decrease, r.transfer, r.fairValueChange)
      return r.endFair - expected
    }),
  )

  const isFairBalanced = computed(() =>
    fairBalanceErrors.value.every((e) => Math.abs(e) < 0.01),
  )

  /** 公允价值变动损益合计 */
  const fairValueChangePL = computed(() =>
    calcSubtotal(rows.value.map((r) => r.fairValueChange)),
  )

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: keyof H3FairAdjRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = typeof value === 'number' ? value : Number(value) || 0
    // 重算公式列
    row.endFair = calcFairEndBalance(row.beginFair, row.increase, row.decrease, row.transfer, row.fairValueChange)
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
    _persist()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    setValue(ITEM_ID_FAIR_ROWS, rows.value)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => loadRows(), { immediate: true })

  return {
    rows,
    total,
    fairBalanceErrors,
    isFairBalanced,
    fairValueChangePL,
    updateCell,
    loadRows,
  }
}

export default useH3AdjudicationFair
