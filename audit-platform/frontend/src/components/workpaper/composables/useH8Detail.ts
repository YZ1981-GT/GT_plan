/**
 * useH8Detail — H8-2 明细表 composable（58列4区段Tab，动态行CRUD）
 *
 * 4区段Tab：
 * 基础(租赁合同号/承租资产/出租方/起始日/到期日)
 * | 初始(H9初始+直接费用-激励=入账值)
 * | 折旧(累计折旧/本期计提/期末净值)
 * | 变更(租赁变更调整/终止日)
 *
 * 核心公式：入账值 = H9初始计量 + 初始直接费用 - 租赁激励（CAS21第16条）
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/
 * Task: 3.4
 * Requirements: 3.1-3.4
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcSubtotal } from './useH8FormulaEngine'
import { calcInitialMeasurement } from './useH8CAS21Engine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H8-2 明细表行 */
export interface H8DetailRow {
  rowId: string
  // ═══ 区段1: 基础 ═══
  contractNo: string
  assetName: string
  lessor: string
  startDate: string
  endDate: string
  leaseType: string

  // ═══ 区段2: 初始计量 ═══
  /** H9租赁负债初始确认 */
  h9InitialAmount: number
  /** 初始直接费用 */
  directCost: number
  /** 租赁激励 */
  incentive: number
  /** 入账值（公式：=H9+直接费用-激励） */
  initialAmount: number

  // ═══ 区段3: 折旧 ═══
  /** 累计折旧期初 */
  accDepBegin: number
  /** 本期计提折旧 */
  depCurrentPeriod: number
  /** 累计折旧期末 */
  accDepEnd: number
  /** 期末净值 */
  netValue: number

  // ═══ 区段4: 变更 ═══
  /** 租赁变更调整额 */
  modificationAmount: number
  /** 终止日（提前退租） */
  terminationDate: string
  /** 备注 */
  remark: string
}

/** 4区段Tab类型 */
export type H8DetailTab = 'basic' | 'initial' | 'depreciation' | 'modification'

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H8-2-rows'
const DETAIL_TOTAL_KEY = 'H8-2-initial-total'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8Detail(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H8DetailRow[]>([])
  const activeTab = ref<H8DetailTab>('basic')

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any): H8DetailRow {
    const h9Init = Number(raw.h9InitialAmount) || 0
    const dc = Number(raw.directCost) || 0
    const inc = Number(raw.incentive) || 0
    const accDepBegin = Number(raw.accDepBegin) || 0
    const depCur = Number(raw.depCurrentPeriod) || 0

    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      contractNo: raw.contractNo ?? '',
      assetName: raw.assetName ?? '',
      lessor: raw.lessor ?? '',
      startDate: raw.startDate ?? '',
      endDate: raw.endDate ?? '',
      leaseType: raw.leaseType ?? '',
      h9InitialAmount: h9Init,
      directCost: dc,
      incentive: inc,
      initialAmount: calcInitialMeasurement(h9Init, dc, inc),
      accDepBegin,
      depCurrentPeriod: depCur,
      accDepEnd: accDepBegin + depCur,
      netValue: calcInitialMeasurement(h9Init, dc, inc) - (accDepBegin + depCur),
      modificationAmount: Number(raw.modificationAmount) || 0,
      terminationDate: raw.terminationDate ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Load ──────────────────────────────────────────────────────────────────

  function load(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(_normalizeRow)
    } else {
      rows.value = []
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  const subtotalRow = computed(() => ({
    initialAmount: calcSubtotal(rows.value.map(r => r.initialAmount)),
    accDepEnd: calcSubtotal(rows.value.map(r => r.accDepEnd)),
    netValue: calcSubtotal(rows.value.map(r => r.netValue)),
    depCurrentPeriod: calcSubtotal(rows.value.map(r => r.depCurrentPeriod)),
  }))

  const initialTotal: ComputedRef<number> = computed(() => subtotalRow.value.initialAmount)

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(contractNo: string): void {
    if (!contractNo?.trim()) return
    rows.value.push(_normalizeRow({ contractNo: contractNo.trim() }))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    _persist()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    const textFields = ['contractNo', 'assetName', 'lessor', 'startDate', 'endDate', 'leaseType', 'terminationDate', 'remark']
    if (textFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persist()
      return
    }

    const numVal = Number(value) || 0
    switch (field) {
      case 'h9InitialAmount': row.h9InitialAmount = numVal; break
      case 'directCost': row.directCost = numVal; break
      case 'incentive': row.incentive = numVal; break
      case 'accDepBegin': row.accDepBegin = numVal; break
      case 'depCurrentPeriod': row.depCurrentPeriod = numVal; break
      case 'modificationAmount': row.modificationAmount = numVal; break
      default: return
    }

    // 重算公式列
    row.initialAmount = calcInitialMeasurement(row.h9InitialAmount, row.directCost, row.incentive)
    row.accDepEnd = row.accDepBegin + row.depCurrentPeriod
    row.netValue = row.initialAmount - row.accDepEnd
    _persist()
  }

  function setActiveTab(tab: H8DetailTab): void {
    activeTab.value = tab
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.map(r => ({
      rowId: r.rowId, contractNo: r.contractNo, assetName: r.assetName,
      lessor: r.lessor, startDate: r.startDate, endDate: r.endDate, leaseType: r.leaseType,
      h9InitialAmount: r.h9InitialAmount, directCost: r.directCost, incentive: r.incentive,
      accDepBegin: r.accDepBegin, depCurrentPeriod: r.depCurrentPeriod,
      modificationAmount: r.modificationAmount, terminationDate: r.terminationDate,
      remark: r.remark,
    }))
    onSave(ROWS_KEY, toPersist)
    onSave(DETAIL_TOTAL_KEY, initialTotal.value)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows, activeTab, subtotalRow, initialTotal,
    addRow, deleteRow, updateCell, setActiveTab, save, load,
  }
}

export default useH8Detail
