/**
 * useH4AdditionCheck — H4-4 增加检查表 composable
 *
 * 19列：序号 | 物资名称 | 规格型号 | 数量 | 单价 | 金额 | 供应商 | 合同编号 | 入库日期
 *       | 入库单号 | 发票号 | 发票金额 | 差异 | 验收人 | 抽凭结果 | 附件 | 核查结论 | 备注 | 索引
 *
 * 功能：
 * - 差异自动计算：diff = amount - invoiceAmount
 * - Statistics computed: checkedCount/totalAmount/diffCount
 * - Saves to "H4-4-rows"
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Task: 3.4
 * Requirements: 5.1-5.7
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcSubtotal } from './useH4FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H4-4 增加检查行 */
export interface H4AdditionCheckRow {
  rowId: string
  /** 序号 */
  seq: number
  /** 物资名称 */
  name: string
  /** 规格型号 */
  spec: string
  /** 数量 */
  quantity: number
  /** 单价 */
  unitPrice: number
  /** 金额 */
  amount: number
  /** 供应商 */
  supplier: string
  /** 合同编号 */
  contractNo: string
  /** 入库日期 */
  inboundDate: string
  /** 入库单号 */
  inboundNo: string
  /** 发票号 */
  invoiceNo: string
  /** 发票金额 */
  invoiceAmount: number
  /** 差异（公式：=金额-发票金额） */
  diff: number
  /** 验收人 */
  inspector: string
  /** 抽凭结果 */
  voucherResult: string
  /** 附件标记 */
  hasAttachment: boolean
  /** 核查结论 */
  conclusion: string
  /** 备注 */
  remark: string
  /** 索引 */
  refIndex: string
}

/** 统计摘要 */
export interface H4AdditionStats {
  /** 已检查笔数 */
  checkedCount: number
  /** 总金额 */
  totalAmount: number
  /** 差异笔数 */
  diffCount: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H4-4-rows'
const ADDITION_TOTAL_KEY = 'H4-4-addition-total'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH4AdditionCheck(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H4AdditionCheckRow[]>([])

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any, idx: number): H4AdditionCheckRow {
    const amount = Number(raw.amount) || 0
    const invoiceAmount = Number(raw.invoiceAmount) || 0

    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      seq: raw.seq ?? idx + 1,
      name: raw.name ?? '',
      spec: raw.spec ?? '',
      quantity: Number(raw.quantity) || 0,
      unitPrice: Number(raw.unitPrice) || 0,
      amount,
      supplier: raw.supplier ?? '',
      contractNo: raw.contractNo ?? '',
      inboundDate: raw.inboundDate ?? '',
      inboundNo: raw.inboundNo ?? '',
      invoiceNo: raw.invoiceNo ?? '',
      invoiceAmount,
      diff: amount - invoiceAmount,
      inspector: raw.inspector ?? '',
      voucherResult: raw.voucherResult ?? '',
      hasAttachment: raw.hasAttachment ?? false,
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
      refIndex: raw.refIndex ?? '',
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

  // ─── Computed: 统计摘要 ────────────────────────────────────────────────────

  const stats: ComputedRef<H4AdditionStats> = computed(() => {
    const checkedCount = rows.value.filter(r => r.conclusion !== '').length
    const totalAmount = calcSubtotal(rows.value.map(r => r.amount))
    const diffCount = rows.value.filter(r => Math.abs(r.diff) > 0.01).length
    return { checkedCount, totalAmount, diffCount }
  })

  /** 金额合计（供CrossSheet使用） */
  const additionTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.amount)),
  )

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(name: string): void {
    if (!name?.trim()) return
    const seq = rows.value.length + 1
    rows.value.push(_normalizeRow({ name: name.trim(), seq }, seq - 1))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persist()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    // 文本字段
    if (['name', 'spec', 'supplier', 'contractNo', 'inboundDate', 'inboundNo', 'invoiceNo', 'inspector', 'voucherResult', 'conclusion', 'remark', 'refIndex'].includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persist()
      return
    }

    // 布尔字段
    if (field === 'hasAttachment') {
      row.hasAttachment = !!value
      _persist()
      return
    }

    // 数值字段
    const numVal = Number(value) || 0
    switch (field) {
      case 'quantity': row.quantity = numVal; break
      case 'unitPrice': row.unitPrice = numVal; break
      case 'amount': row.amount = numVal; break
      case 'invoiceAmount': row.invoiceAmount = numVal; break
      default: return
    }

    // 重算差异
    row.diff = row.amount - row.invoiceAmount

    _persist()
  }

  // ─── Save ──────────────────────────────────────────────────────────────────

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.map(r => ({
      rowId: r.rowId,
      seq: r.seq,
      name: r.name,
      spec: r.spec,
      quantity: r.quantity,
      unitPrice: r.unitPrice,
      amount: r.amount,
      supplier: r.supplier,
      contractNo: r.contractNo,
      inboundDate: r.inboundDate,
      inboundNo: r.inboundNo,
      invoiceNo: r.invoiceNo,
      invoiceAmount: r.invoiceAmount,
      inspector: r.inspector,
      voucherResult: r.voucherResult,
      hasAttachment: r.hasAttachment,
      conclusion: r.conclusion,
      remark: r.remark,
      refIndex: r.refIndex,
    }))
    onSave(ROWS_KEY, toPersist)
    // 同步写入合计供CrossSheet
    onSave(ADDITION_TOTAL_KEY, additionTotal.value)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    rows,
    // Computed
    stats,
    additionTotal,
    // Actions
    addRow,
    deleteRow,
    updateCell,
    save,
    load,
  }
}

export default useH4AdditionCheck
