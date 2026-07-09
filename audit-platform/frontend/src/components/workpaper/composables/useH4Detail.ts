/**
 * useH4Detail — H4-2 明细表 composable（67列宽表，3区段Tab）
 *
 * 3区段Tab：基础(物资分类/名称/规格/数量/单位/供应商) | 入库(期初金额/本期采购/其他增加/入库小计) | 出库(领用出库/退货/报废/其他减少/期末余额)
 *
 * 功能：
 * - 3区段Tab state management
 * - Dynamic rows CRUD (add/delete physical items)
 * - Row-level formula: 期末=期初+入库-出库
 * - Subtotal row computed
 * - Saves rows as JSON to "H4-2-rows"
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Task: 3.4
 * Requirements: 3.1-3.9
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcAssetEndBalance, calcSubtotal } from './useH4FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H4-2 明细表行 */
export interface H4DetailRow {
  rowId: string

  // ═══ 区段1: 基础信息 ═══
  /** 物资分类 */
  category: string
  /** 物资名称 */
  name: string
  /** 规格型号 */
  spec: string
  /** 数量 */
  quantity: number
  /** 单位 */
  unit: string
  /** 供应商 */
  supplier: string

  // ═══ 区段2: 入库 ═══
  /** 期初金额 */
  beginAmount: number
  /** 本期采购 */
  purchaseAmount: number
  /** 其他增加 */
  otherIncrease: number
  /** 入库小计（公式：=采购+其他增加） */
  increaseSubtotal: number

  // ═══ 区段3: 出库 ═══
  /** 领用出库 */
  usageAmount: number
  /** 退货 */
  returnAmount: number
  /** 报废 */
  scrapAmount: number
  /** 其他减少 */
  otherDecrease: number
  /** 期末余额（公式：=期初+入库小计-出库合计） */
  endAmount: number
}

/** 3区段Tab类型 */
export type H4DetailTab = 'basic' | 'inbound' | 'outbound'

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H4-2-rows'
const DETAIL_TOTAL_KEY = 'H4-2-detail-total'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH4Detail(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H4DetailRow[]>([])
  const activeTab = ref<H4DetailTab>('basic')
  const selectedRowId = ref<string | null>(null)

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  /** 计算出库合计 */
  function _calcDecreaseTotal(row: H4DetailRow): number {
    return row.usageAmount + row.returnAmount + row.scrapAmount + row.otherDecrease
  }

  /** 规范化行（加载后重算公式列） */
  function _normalizeRow(raw: any): H4DetailRow {
    const begin = Number(raw.beginAmount) || 0
    const purchase = Number(raw.purchaseAmount) || 0
    const otherInc = Number(raw.otherIncrease) || 0
    const usage = Number(raw.usageAmount) || 0
    const ret = Number(raw.returnAmount) || 0
    const scrap = Number(raw.scrapAmount) || 0
    const otherDec = Number(raw.otherDecrease) || 0

    const increaseSubtotal = purchase + otherInc
    const decreaseTotal = usage + ret + scrap + otherDec
    // 期末=期初+入库-出库（资产类借方科目模式）
    const endAmount = calcAssetEndBalance(begin, increaseSubtotal, decreaseTotal)

    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      category: raw.category ?? '',
      name: raw.name ?? '',
      spec: raw.spec ?? '',
      quantity: Number(raw.quantity) || 0,
      unit: raw.unit ?? '',
      supplier: raw.supplier ?? '',
      beginAmount: begin,
      purchaseAmount: purchase,
      otherIncrease: otherInc,
      increaseSubtotal,
      usageAmount: usage,
      returnAmount: ret,
      scrapAmount: scrap,
      otherDecrease: otherDec,
      endAmount,
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

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const subtotalRow: ComputedRef<Omit<H4DetailRow, 'rowId' | 'category' | 'name' | 'spec' | 'quantity' | 'unit' | 'supplier'>> = computed(() => ({
    beginAmount: calcSubtotal(rows.value.map(r => r.beginAmount)),
    purchaseAmount: calcSubtotal(rows.value.map(r => r.purchaseAmount)),
    otherIncrease: calcSubtotal(rows.value.map(r => r.otherIncrease)),
    increaseSubtotal: calcSubtotal(rows.value.map(r => r.increaseSubtotal)),
    usageAmount: calcSubtotal(rows.value.map(r => r.usageAmount)),
    returnAmount: calcSubtotal(rows.value.map(r => r.returnAmount)),
    scrapAmount: calcSubtotal(rows.value.map(r => r.scrapAmount)),
    otherDecrease: calcSubtotal(rows.value.map(r => r.otherDecrease)),
    endAmount: calcSubtotal(rows.value.map(r => r.endAmount)),
  }))

  /** 期末合计（供CrossSheet使用） */
  const endTotal: ComputedRef<number> = computed(() => subtotalRow.value.endAmount)

  // ─── Actions ───────────────────────────────────────────────────────────────

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
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    // 文本字段
    if (['category', 'name', 'spec', 'unit', 'supplier'].includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persist()
      return
    }

    // 数值字段
    const numVal = Number(value) || 0
    switch (field) {
      case 'quantity': row.quantity = numVal; break
      case 'beginAmount': row.beginAmount = numVal; break
      case 'purchaseAmount': row.purchaseAmount = numVal; break
      case 'otherIncrease': row.otherIncrease = numVal; break
      case 'usageAmount': row.usageAmount = numVal; break
      case 'returnAmount': row.returnAmount = numVal; break
      case 'scrapAmount': row.scrapAmount = numVal; break
      case 'otherDecrease': row.otherDecrease = numVal; break
      default: return
    }

    // 重算公式列
    row.increaseSubtotal = row.purchaseAmount + row.otherIncrease
    row.endAmount = calcAssetEndBalance(row.beginAmount, row.increaseSubtotal, _calcDecreaseTotal(row))

    _persist()
  }

  function setActiveTab(tab: H4DetailTab): void {
    activeTab.value = tab
  }

  function selectRow(rowId: string | null): void {
    selectedRowId.value = rowId
  }

  // ─── Save ──────────────────────────────────────────────────────────────────

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.map(r => ({
      rowId: r.rowId,
      category: r.category,
      name: r.name,
      spec: r.spec,
      quantity: r.quantity,
      unit: r.unit,
      supplier: r.supplier,
      beginAmount: r.beginAmount,
      purchaseAmount: r.purchaseAmount,
      otherIncrease: r.otherIncrease,
      usageAmount: r.usageAmount,
      returnAmount: r.returnAmount,
      scrapAmount: r.scrapAmount,
      otherDecrease: r.otherDecrease,
    }))
    onSave(ROWS_KEY, toPersist)
    // 同步写入期末合计供CrossSheet
    onSave(DETAIL_TOTAL_KEY, endTotal.value)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    rows,
    activeTab,
    selectedRowId,
    // Computed
    subtotalRow,
    endTotal,
    // Actions
    addRow,
    deleteRow,
    updateCell,
    setActiveTab,
    selectRow,
    save,
    load,
  }
}

export default useH4Detail
