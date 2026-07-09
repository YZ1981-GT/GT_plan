/**
 * useH4RelatedParty — H4-9 关联交易检查表 composable
 *
 * 16列：序号 | 物资名称 | 交易对手 | 关联关系 | 交易金额 | 市场价格 | 价差率
 *       | 合同日期 | 合同编号 | 定价依据 | 审批流程 | 是否公允 | 决策程序 | 披露情况 | 核查结论 | 备注
 *
 * 功能：
 * - calcPriceDiffRate for each row
 * - 异常判定: |rate| > 10% → isAbnormal=true
 * - Statistics: transCount/totalAmount/abnormalCount
 * - Saves to "H4-9-rows"
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Task: 3.4
 * Requirements: 8.1-8.5
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcPriceDiffRate, calcSubtotal } from './useH4FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H4-9 关联交易行 */
export interface H4RelatedPartyRow {
  rowId: string
  /** 序号 */
  seq: number
  /** 物资名称 */
  name: string
  /** 交易对手 */
  counterparty: string
  /** 关联关系 */
  relationship: string
  /** 交易金额 */
  transAmount: number
  /** 市场价格 */
  marketPrice: number
  /** 价差率（%）（公式：=(交易金额-市场价格)/市场价格×100） */
  priceDiffRate: number
  /** 合同日期 */
  contractDate: string
  /** 合同编号 */
  contractNo: string
  /** 定价依据 */
  pricingBasis: string
  /** 审批流程 */
  approvalProcess: string
  /** 是否公允 */
  isFair: string
  /** 决策程序 */
  decisionProcess: string
  /** 披露情况 */
  disclosureStatus: string
  /** 核查结论 */
  conclusion: string
  /** 备注 */
  remark: string
  /** 异常标记（|价差率| > 10%） */
  isAbnormal: boolean
}

/** 关联交易统计 */
export interface H4RelatedPartyStats {
  /** 关联交易笔数 */
  transCount: number
  /** 总金额 */
  totalAmount: number
  /** 异常笔数 */
  abnormalCount: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H4-9-rows'
const ABNORMAL_THRESHOLD = 10 // |价差率| > 10% 为异常

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH4RelatedParty(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H4RelatedPartyRow[]>([])

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any, idx: number): H4RelatedPartyRow {
    const transAmount = Number(raw.transAmount) || 0
    const marketPrice = Number(raw.marketPrice) || 0
    const rate = calcPriceDiffRate(transAmount, marketPrice)

    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      seq: raw.seq ?? idx + 1,
      name: raw.name ?? '',
      counterparty: raw.counterparty ?? '',
      relationship: raw.relationship ?? '',
      transAmount,
      marketPrice,
      priceDiffRate: rate,
      contractDate: raw.contractDate ?? '',
      contractNo: raw.contractNo ?? '',
      pricingBasis: raw.pricingBasis ?? '',
      approvalProcess: raw.approvalProcess ?? '',
      isFair: raw.isFair ?? '',
      decisionProcess: raw.decisionProcess ?? '',
      disclosureStatus: raw.disclosureStatus ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
      isAbnormal: Math.abs(rate) > ABNORMAL_THRESHOLD,
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

  const stats: ComputedRef<H4RelatedPartyStats> = computed(() => ({
    transCount: rows.value.length,
    totalAmount: calcSubtotal(rows.value.map(r => r.transAmount)),
    abnormalCount: rows.value.filter(r => r.isAbnormal).length,
  }))

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
    if (['name', 'counterparty', 'relationship', 'contractDate', 'contractNo', 'pricingBasis', 'approvalProcess', 'isFair', 'decisionProcess', 'disclosureStatus', 'conclusion', 'remark'].includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persist()
      return
    }

    // 数值字段
    const numVal = Number(value) || 0
    switch (field) {
      case 'transAmount': row.transAmount = numVal; break
      case 'marketPrice': row.marketPrice = numVal; break
      default: return
    }

    // 重算价差率 + 异常标记
    row.priceDiffRate = calcPriceDiffRate(row.transAmount, row.marketPrice)
    row.isAbnormal = Math.abs(row.priceDiffRate) > ABNORMAL_THRESHOLD

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
      counterparty: r.counterparty,
      relationship: r.relationship,
      transAmount: r.transAmount,
      marketPrice: r.marketPrice,
      contractDate: r.contractDate,
      contractNo: r.contractNo,
      pricingBasis: r.pricingBasis,
      approvalProcess: r.approvalProcess,
      isFair: r.isFair,
      decisionProcess: r.decisionProcess,
      disclosureStatus: r.disclosureStatus,
      conclusion: r.conclusion,
      remark: r.remark,
    }))
    onSave(ROWS_KEY, toPersist)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    rows,
    // Computed
    stats,
    // Actions
    addRow,
    deleteRow,
    updateCell,
    save,
    load,
  }
}

export default useH4RelatedParty
