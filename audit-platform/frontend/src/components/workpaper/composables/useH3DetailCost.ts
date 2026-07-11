/**
 * useH3DetailCost — H3-2 明细表（成本模式）composable
 *
 * DetailCostRow 49列 + 3区段分组 + 行内公式（净值=原值-折旧-减值）+ subtotalRow + crossValidation
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.6
 * Requirements: 3.1-3.9
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import { calcSubtotal } from './useH3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DetailCostRow {
  rowId: string
  // 区段1: 基本信息
  assetName: string
  assetType: string           // 类型：房屋/土地
  location: string
  area: number                // 面积(㎡)
  acquireDate: string         // 取得日期
  originalCost: number        // 入账原值
  // 区段2: 折旧变动
  accDepBegin: number         // 累计折旧期初
  depProvision: number        // 本期计提
  depReversal: number         // 转回
  accDepEnd: number           // 累计折旧期末（公式）
  impairmentBegin: number     // 减值准备期初
  impairmentProvision: number // 本期减值
  impairmentEnd: number       // 减值期末
  netValue: number            // 净值（公式：原值-折旧-减值）
  // 区段3: 增减转换
  costBegin: number           // 原值期初
  costIncrease: number        // 本期增加
  costDecrease: number        // 本期减少
  transferIn: number          // 转入
  transferOut: number         // 转出
  costEnd: number             // 期末原值（公式）
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID = 'H3-2-cost-rows'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH3DetailCost(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params

  const rows = ref<DetailCostRow[]>([])

  // ─── Load ──────────────────────────────────────────────────────────────────

  function loadRows(): void {
    const raw = getValue(ITEM_ID)
    rows.value = Array.isArray(raw) ? raw.map(_normalize) : []
  }

  function _normalize(raw: any): DetailCostRow {
    const costBegin = Number(raw.costBegin) || 0
    const costInc = Number(raw.costIncrease) || 0
    const costDec = Number(raw.costDecrease) || 0
    const transIn = Number(raw.transferIn) || 0
    const transOut = Number(raw.transferOut) || 0
    const costEnd = costBegin + costInc - costDec + transIn - transOut

    const depBegin = Number(raw.accDepBegin) || 0
    const depProv = Number(raw.depProvision) || 0
    const depRev = Number(raw.depReversal) || 0
    const depEnd = depBegin + depProv - depRev

    const impBegin = Number(raw.impairmentBegin) || 0
    const impProv = Number(raw.impairmentProvision) || 0
    const impEnd = impBegin + impProv

    const originalCost = Number(raw.originalCost) || costEnd
    const netValue = originalCost - depEnd - impEnd

    return {
      rowId: raw.rowId ?? `dc-${Math.random().toString(36).slice(2, 8)}`,
      assetName: raw.assetName ?? '',
      assetType: raw.assetType ?? '',
      location: raw.location ?? '',
      area: Number(raw.area) || 0,
      acquireDate: raw.acquireDate ?? '',
      originalCost,
      accDepBegin: depBegin,
      depProvision: depProv,
      depReversal: depRev,
      accDepEnd: depEnd,
      impairmentBegin: impBegin,
      impairmentProvision: impProv,
      impairmentEnd: impEnd,
      netValue,
      costBegin,
      costIncrease: costInc,
      costDecrease: costDec,
      transferIn: transIn,
      transferOut: transOut,
      costEnd,
      remark: raw.remark ?? '',
    }
  }

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function addRow(assetName: string): void {
    const newRow = _normalize({ assetName, rowId: `dc-${Date.now()}` })
    rows.value.push(newRow)
    _persist()
  }

  function removeRow(index: number): void {
    rows.value.splice(index, 1)
    _persist()
  }

  /**
   * 更新单元格：组件已通过 v-model 就地修改 row 对象（同引用），
   * 此处按 rowId 定位后重算公式列并持久化。
   * （组件调用 updateCell(row.rowId, row)，第二参忽略）
   */
  function updateCell(rowId: string): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    // 类型安全：数字列转 number
    row.area = Number(row.area) || 0
    row.originalCost = Number(row.originalCost) || 0
    row.costBegin = Number(row.costBegin) || 0
    row.costIncrease = Number(row.costIncrease) || 0
    row.costDecrease = Number(row.costDecrease) || 0
    row.transferIn = Number(row.transferIn) || 0
    row.transferOut = Number(row.transferOut) || 0
    row.accDepBegin = Number(row.accDepBegin) || 0
    row.depProvision = Number(row.depProvision) || 0
    row.depReversal = Number(row.depReversal) || 0
    row.impairmentBegin = Number(row.impairmentBegin) || 0
    row.impairmentProvision = Number(row.impairmentProvision) || 0
    // 重算公式
    row.costEnd = row.costBegin + row.costIncrease - row.costDecrease + row.transferIn - row.transferOut
    row.accDepEnd = row.accDepBegin + row.depProvision - row.depReversal
    row.impairmentEnd = row.impairmentBegin + row.impairmentProvision
    row.netValue = row.originalCost - row.accDepEnd - row.impairmentEnd
    _persist()
  }

  // ─── Subtotals ─────────────────────────────────────────────────────────────

  const subtotal = computed(() => ({
    originalCost: calcSubtotal(rows.value.map((r) => r.originalCost)),
    accDepEnd: calcSubtotal(rows.value.map((r) => r.accDepEnd)),
    impairmentEnd: calcSubtotal(rows.value.map((r) => r.impairmentEnd)),
    netValue: calcSubtotal(rows.value.map((r) => r.netValue)),
    costEnd: calcSubtotal(rows.value.map((r) => r.costEnd)),
    costBegin: calcSubtotal(rows.value.map((r) => r.costBegin)),
    costIncrease: calcSubtotal(rows.value.map((r) => r.costIncrease)),
    costDecrease: calcSubtotal(rows.value.map((r) => r.costDecrease)),
  }))

  // ─── 交叉验证：明细期末原值合计 vs H3-1 审定表原值审定合计 ──────────────────

  /**
   * crossValidationDiff = 明细期末原值合计 − H3-1 成本审定表原值审定合计。
   * H3-1 未编制（无数据）时返回 0（不触发告警）。
   */
  const crossValidationDiff = computed(() => {
    const h31 = getValue('H3-1-cost-original-rows')
    if (!Array.isArray(h31) || h31.length === 0) return 0
    const h31Audited = h31.reduce((sum: number, r: any) => sum + (Number(r?.audited) || 0), 0)
    return subtotal.value.costEnd - h31Audited
  })

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    setValue(ITEM_ID, rows.value)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => loadRows(), { immediate: true })

  return {
    rows,
    subtotal,
    crossValidationDiff,
    addRow,
    removeRow,
    updateCell,
    loadRows,
  }
}

export default useH3DetailCost
