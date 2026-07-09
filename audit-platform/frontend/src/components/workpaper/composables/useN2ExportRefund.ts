/**
 * useN2ExportRefund — N2-7 出口退税核对表 composable
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 3.4
 * Requirements: 8.1-8.4
 *
 * 职责：
 * - 出口销售额|退税率|免抵退税额|应退|免抵|已退|差异
 * - Simple计算 + 差异标记
 *
 * 公式：
 * - 免抵退税额 = 出口销售额 × 退税率
 * - 差异 = 免抵退税额 - 已退税额（或 应退-已退）
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { calcSubtotal } from './useN2FormulaEngine'
import type { ChecklistResponse } from './useN2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 出口退税核对行 */
export interface N2ExportRefundRow {
  /** 行ID */
  id: string
  /** 产品/批次描述 */
  description: string
  /** 出口销售额 */
  exportSales: number
  /** 退税率 */
  refundRate: number
  /** 免抵退税额（公式：出口销售额×退税率） */
  taxRefundAmount: number
  /** 应退税额（批复） */
  refundDue: number
  /** 免抵税额（批复） */
  exemptCreditAmount: number
  /** 已退税额（实际到账） */
  actualRefunded: number
  /** 差异（应退-已退） */
  diff: number
  /** 差异是否显著（|diff|>阈值） */
  hasDiff: boolean
}

/** 出口退税汇总 */
export interface N2ExportRefundSummary {
  /** 出口销售额合计 */
  totalExportSales: number
  /** 免抵退税额合计 */
  totalTaxRefund: number
  /** 应退税额合计 */
  totalRefundDue: number
  /** 已退税额合计 */
  totalActualRefunded: number
  /** 差异合计 */
  totalDiff: number
  /** 是否全部核对一致 */
  allMatch: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 差异阈值（0.01元内视为一致） */
const DIFF_THRESHOLD = 0.01

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function generateRowId(): string {
  return `exp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseN2ExportRefundOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
}

export function useN2ExportRefund(options: UseN2ExportRefundOptions) {
  const { allResponses, saveField, getField } = options

  // ─── 1. 出口退税行数据 ────────────────────────────────────────────────────

  /** 出口退税核对各行（公式列自动计算） */
  const rows: ComputedRef<N2ExportRefundRow[]> = computed(() => {
    const itemId = 'N2-7-export-refund-rows'
    const resp = allResponses.value.get(itemId)
    let raw: any[] = []
    if (resp?.conclusion) {
      try { raw = JSON.parse(resp.conclusion) } catch { raw = [] }
    }

    return raw.map((r: any) => {
      const exportSales = parseNum(r.exportSales)
      const refundRate = parseNum(r.refundRate)
      const refundDue = parseNum(r.refundDue)
      const exemptCreditAmount = parseNum(r.exemptCreditAmount)
      const actualRefunded = parseNum(r.actualRefunded)

      // 免抵退税额 = 出口销售额 × 退税率
      const taxRefundAmount = exportSales * refundRate
      // 差异 = 应退 - 已退
      const diff = parseFloat((refundDue - actualRefunded).toFixed(2))

      return {
        id: r.id || generateRowId(),
        description: r.description || '',
        exportSales,
        refundRate,
        taxRefundAmount,
        refundDue,
        exemptCreditAmount,
        actualRefunded,
        diff,
        hasDiff: Math.abs(diff) > DIFF_THRESHOLD,
      }
    })
  })

  // ─── 2. 汇总 ──────────────────────────────────────────────────────────────

  const summary: ComputedRef<N2ExportRefundSummary> = computed(() => {
    const r = rows.value
    const totalExportSales = calcSubtotal(r.map(x => x.exportSales))
    const totalTaxRefund = calcSubtotal(r.map(x => x.taxRefundAmount))
    const totalRefundDue = calcSubtotal(r.map(x => x.refundDue))
    const totalActualRefunded = calcSubtotal(r.map(x => x.actualRefunded))
    const totalDiff = parseFloat((totalRefundDue - totalActualRefunded).toFixed(2))

    return {
      totalExportSales,
      totalTaxRefund,
      totalRefundDue,
      totalActualRefunded,
      totalDiff,
      allMatch: Math.abs(totalDiff) <= DIFF_THRESHOLD,
    }
  })

  // ─── 3. 差异行标识 ────────────────────────────────────────────────────────

  /** 存在差异的行ID集合（黄色/红色标记用） */
  const diffRowIds: ComputedRef<Set<string>> = computed(() => {
    const ids = new Set<string>()
    for (const row of rows.value) {
      if (row.hasDiff) {
        ids.add(row.id)
      }
    }
    return ids
  })

  // ─── 4. 行操作 ────────────────────────────────────────────────────────────

  /**
   * 新增出口退税行
   */
  async function addRow(description: string): Promise<void> {
    const stored = getField('7', 'export-refund-rows') || []
    const raw: any[] = Array.isArray(stored) ? [...stored] : []

    raw.push({
      id: generateRowId(),
      description,
      exportSales: 0,
      refundRate: 0,
      refundDue: 0,
      exemptCreditAmount: 0,
      actualRefunded: 0,
    })

    await saveField('7', 'export-refund-rows', raw)
  }

  /**
   * 删除指定行
   */
  async function removeRow(rowId: string): Promise<void> {
    const stored = getField('7', 'export-refund-rows') || []
    const raw: any[] = Array.isArray(stored) ? [...stored] : []
    const filtered = raw.filter(r => r.id !== rowId)
    await saveField('7', 'export-refund-rows', filtered)
  }

  /**
   * 更新指定行字段
   */
  async function updateRow(
    rowId: string,
    field: 'description' | 'exportSales' | 'refundRate' | 'refundDue' | 'exemptCreditAmount' | 'actualRefunded',
    value: any,
  ): Promise<void> {
    const stored = getField('7', 'export-refund-rows') || []
    const raw: any[] = Array.isArray(stored) ? [...stored] : []
    const idx = raw.findIndex(r => r.id === rowId)
    if (idx >= 0) {
      raw[idx] = { ...raw[idx], [field]: value }
      await saveField('7', 'export-refund-rows', raw)
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    summary,
    diffRowIds,
    addRow,
    removeRow,
    updateRow,
  }
}

export default useN2ExportRefund
