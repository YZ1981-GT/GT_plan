/**
 * useH3DetailFair — H3-2 明细表（公允价值模式）composable
 *
 * DetailFairRow 31列 + 2区段分组 + 行内公式（期末公允=期初+增减±转换+变动）+ subtotalRow
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.7
 * Requirements: 3.1-3.9
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import { calcFairEndBalance, calcSubtotal } from './useH3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DetailFairRow {
  rowId: string
  // 区段1: 基本信息
  assetName: string
  assetType: string
  location: string
  area: number
  acquireDate: string
  fairValueBegin: number      // 期初公允价值
  // 区段2: 公允变动
  fairIncrease: number        // 本期增加
  fairDecrease: number        // 本期减少
  transferIn: number          // 转入
  transferOut: number         // 转出
  fairValueChange: number     // 公允价值变动
  fairValueEnd: number        // 期末公允（公式）
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID = 'H3-2-fair-rows'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH3DetailFair(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params

  const rows = ref<DetailFairRow[]>([])

  function loadRows(): void {
    const raw = getValue(ITEM_ID)
    rows.value = Array.isArray(raw) ? raw.map(_normalize) : []
  }

  function _normalize(raw: any): DetailFairRow {
    const begin = Number(raw.fairValueBegin) || 0
    const inc = Number(raw.fairIncrease) || 0
    const dec = Number(raw.fairDecrease) || 0
    const transIn = Number(raw.transferIn) || 0
    const transOut = Number(raw.transferOut) || 0
    const transfer = transIn - transOut
    const change = Number(raw.fairValueChange) || 0
    const end = calcFairEndBalance(begin, inc, dec, transfer, change)
    return {
      rowId: raw.rowId ?? `df-${Math.random().toString(36).slice(2, 8)}`,
      assetName: raw.assetName ?? '',
      assetType: raw.assetType ?? '',
      location: raw.location ?? '',
      area: Number(raw.area) || 0,
      acquireDate: raw.acquireDate ?? '',
      fairValueBegin: begin,
      fairIncrease: inc,
      fairDecrease: dec,
      transferIn: transIn,
      transferOut: transOut,
      fairValueChange: change,
      fairValueEnd: end,
      remark: raw.remark ?? '',
    }
  }

  function addRow(assetName: string): void {
    const newRow = _normalize({ assetName, rowId: `df-${Date.now()}` })
    rows.value.push(newRow)
    _persist()
  }

  function removeRow(index: number): void {
    rows.value.splice(index, 1)
    _persist()
  }

  function updateCell(index: number, field: keyof DetailFairRow, value: any): void {
    const row = rows.value[index]
    if (!row) return
    ;(row as any)[field] = typeof value === 'number' ? value : (Number(value) || value)
    const transfer = row.transferIn - row.transferOut
    row.fairValueEnd = calcFairEndBalance(
      row.fairValueBegin, row.fairIncrease, row.fairDecrease, transfer, row.fairValueChange,
    )
    _persist()
  }

  const subtotal = computed(() => ({
    fairValueBegin: calcSubtotal(rows.value.map((r) => r.fairValueBegin)),
    fairIncrease: calcSubtotal(rows.value.map((r) => r.fairIncrease)),
    fairDecrease: calcSubtotal(rows.value.map((r) => r.fairDecrease)),
    fairValueChange: calcSubtotal(rows.value.map((r) => r.fairValueChange)),
    fairValueEnd: calcSubtotal(rows.value.map((r) => r.fairValueEnd)),
  }))

  function _persist(): void {
    setValue(ITEM_ID, rows.value)
  }

  watch(allResponses, () => loadRows(), { immediate: true })

  return { rows, subtotal, addRow, removeRow, updateCell, loadRows }
}

export default useH3DetailFair
