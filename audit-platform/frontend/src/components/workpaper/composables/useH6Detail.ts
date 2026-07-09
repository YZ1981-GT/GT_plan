/**
 * useH6Detail — H6-2 明细表 composable（25列2区块+动态行+导入导出）
 *
 * 2区块：
 * 基础(序号/资产名称/原值/累计折旧/净值/清理原因/开始日期)
 * 清理(处置收入/清理费用/税费/净损益/结转科目/完成日期/状态/联动H1编号/联动H10编号)
 *
 * 功能：
 * - calcNetBookValue + calcDisposalGainLoss for each row
 * - Dynamic rows (add/delete)
 * - Status options: 清理中/已完成/已结转
 * - Subtotal row
 * - 联动H1编号→H1-8减少检查；联动H10编号→H10明细
 * - Saves to "H6-2-rows"
 *
 * Spec: .kiro/specs/h6-asset-disposal-clearing/
 * Task: 3.4
 * Requirements: 3.1-3.7
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcNetBookValue, calcDisposalGainLoss, calcSubtotal } from './useH6FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H6-2 明细表行 */
export interface H6DetailRow {
  rowId: string

  // ═══ 区块1: 基础信息 ═══
  /** 序号 */
  seq: number
  /** 资产名称 */
  assetName: string
  /** 原值 */
  originalCost: number
  /** 累计折旧 */
  accumulatedDepreciation: number
  /** 净值（公式：=原值-累计折旧） */
  netBookValue: number
  /** 清理原因 */
  disposalReason: string
  /** 开始日期 */
  startDate: string

  // ═══ 区块2: 清理信息 ═══
  /** 处置收入 */
  disposalIncome: number
  /** 清理费用 */
  disposalExpenses: number
  /** 税费 */
  taxAmount: number
  /** 净损益（公式：=处置收入-净值-清理费用-税费） */
  gainLoss: number
  /** 结转科目 */
  transferAccount: string
  /** 完成日期 */
  completionDate: string
  /** 状态：清理中/已完成/已结转 */
  status: '清理中' | '已完成' | '已结转'
  /** 联动H1编号（GtIndexChip跳转H1-8减少检查） */
  refH1Code: string
  /** 联动H10编号（GtIndexChip跳转H10明细） */
  refH10Code: string
}

/** 明细表Tab类型 */
export type H6DetailTab = 'basic' | 'disposal'

/** 状态选项 */
export const H6_DETAIL_STATUS_OPTIONS = ['清理中', '已完成', '已结转'] as const

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H6-2-rows'
const SUBTOTAL_GAIN_LOSS_KEY = 'H6-2-subtotal-gain-loss'
const SUBTOTAL_END_KEY = 'H6-2-subtotal-net-book-value'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH6Detail(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H6DetailRow[]>([])
  const activeTab = ref<H6DetailTab>('basic')

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  /** 规范化行（加载后重算公式列） */
  function _normalizeRow(raw: any, idx: number): H6DetailRow {
    const cost = Number(raw.originalCost) || 0
    const dep = Number(raw.accumulatedDepreciation) || 0
    const income = Number(raw.disposalIncome) || 0
    const expenses = Number(raw.disposalExpenses) || 0
    const tax = Number(raw.taxAmount) || 0

    const netBookValue = calcNetBookValue(cost, dep)
    const gainLoss = calcDisposalGainLoss(income, netBookValue, expenses, tax)

    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      seq: raw.seq ?? idx + 1,
      assetName: raw.assetName ?? '',
      originalCost: cost,
      accumulatedDepreciation: dep,
      netBookValue,
      disposalReason: raw.disposalReason ?? '',
      startDate: raw.startDate ?? '',
      disposalIncome: income,
      disposalExpenses: expenses,
      taxAmount: tax,
      gainLoss,
      transferAccount: raw.transferAccount ?? '',
      completionDate: raw.completionDate ?? '',
      status: H6_DETAIL_STATUS_OPTIONS.includes(raw.status) ? raw.status : '清理中',
      refH1Code: raw.refH1Code ?? '',
      refH10Code: raw.refH10Code ?? '',
    }
  }

  // ─── Load ──────────────────────────────────────────────────────────────────

  function load(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map((r, i) => _normalizeRow(r, i))
    } else {
      rows.value = []
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const subtotalRow = computed(() => ({
    originalCost: calcSubtotal(rows.value.map(r => r.originalCost)),
    accumulatedDepreciation: calcSubtotal(rows.value.map(r => r.accumulatedDepreciation)),
    netBookValue: calcSubtotal(rows.value.map(r => r.netBookValue)),
    disposalIncome: calcSubtotal(rows.value.map(r => r.disposalIncome)),
    disposalExpenses: calcSubtotal(rows.value.map(r => r.disposalExpenses)),
    taxAmount: calcSubtotal(rows.value.map(r => r.taxAmount)),
    gainLoss: calcSubtotal(rows.value.map(r => r.gainLoss)),
  }))

  /** 净损益合计（供CrossSheet使用，验证与H6-1一致） */
  const gainLossTotal: ComputedRef<number> = computed(() => subtotalRow.value.gainLoss)

  /** 统计各状态数量 */
  const statusSummary = computed(() => ({
    clearing: rows.value.filter(r => r.status === '清理中').length,
    completed: rows.value.filter(r => r.status === '已完成').length,
    transferred: rows.value.filter(r => r.status === '已结转').length,
    total: rows.value.length,
  }))

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(assetName: string): void {
    if (!assetName?.trim()) return
    const seq = rows.value.length + 1
    rows.value.push(_normalizeRow({ assetName: assetName.trim(), seq }, seq - 1))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    // 重排序号
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persist()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    // 文本/日期/状态字段
    if (['assetName', 'disposalReason', 'startDate', 'transferAccount', 'completionDate', 'refH1Code', 'refH10Code'].includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persist()
      return
    }

    if (field === 'status') {
      row.status = H6_DETAIL_STATUS_OPTIONS.includes(value as any) ? value : '清理中'
      _persist()
      return
    }

    // 数值字段
    const numVal = Number(value) || 0
    switch (field) {
      case 'originalCost': row.originalCost = numVal; break
      case 'accumulatedDepreciation': row.accumulatedDepreciation = numVal; break
      case 'disposalIncome': row.disposalIncome = numVal; break
      case 'disposalExpenses': row.disposalExpenses = numVal; break
      case 'taxAmount': row.taxAmount = numVal; break
      default: return
    }

    // 重算公式列
    row.netBookValue = calcNetBookValue(row.originalCost, row.accumulatedDepreciation)
    row.gainLoss = calcDisposalGainLoss(row.disposalIncome, row.netBookValue, row.disposalExpenses, row.taxAmount)

    _persist()
  }

  function setActiveTab(tab: H6DetailTab): void {
    activeTab.value = tab
  }

  /** 从H1处置事件自动创建清理项目行 */
  function createFromH1Disposal(payload: { assetName: string; originalCost: number; accDep: number; refH1Code: string }): void {
    const seq = rows.value.length + 1
    rows.value.push(_normalizeRow({
      assetName: payload.assetName,
      originalCost: payload.originalCost,
      accumulatedDepreciation: payload.accDep,
      refH1Code: payload.refH1Code,
      seq,
    }, seq - 1))
    _persist()
  }

  // ─── Save ──────────────────────────────────────────────────────────────────

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.map(r => ({
      rowId: r.rowId,
      seq: r.seq,
      assetName: r.assetName,
      originalCost: r.originalCost,
      accumulatedDepreciation: r.accumulatedDepreciation,
      disposalReason: r.disposalReason,
      startDate: r.startDate,
      disposalIncome: r.disposalIncome,
      disposalExpenses: r.disposalExpenses,
      taxAmount: r.taxAmount,
      transferAccount: r.transferAccount,
      completionDate: r.completionDate,
      status: r.status,
      refH1Code: r.refH1Code,
      refH10Code: r.refH10Code,
    }))
    onSave(ROWS_KEY, toPersist)
    // 同步写入合计供CrossSheet
    onSave(SUBTOTAL_GAIN_LOSS_KEY, gainLossTotal.value)
    onSave(SUBTOTAL_END_KEY, subtotalRow.value.netBookValue)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    rows,
    activeTab,
    // Computed
    subtotalRow,
    gainLossTotal,
    statusSummary,
    // Actions
    addRow,
    deleteRow,
    updateCell,
    setActiveTab,
    createFromH1Disposal,
    save,
    load,
  }
}

export default useH6Detail
