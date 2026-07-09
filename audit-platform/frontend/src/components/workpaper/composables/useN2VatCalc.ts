/**
 * useN2VatCalc — N2-6 增值税测算表 composable
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 3.4
 * Requirements: 4.1-4.6
 *
 * 职责：
 * - 按月/季度分行(12行/4行)
 * - Uses calcOutputVat, calcPayableVat, calcVatBurdenRate from useN2VatEngine
 * - 年度汇总行 + 税负率分析
 *
 * 科目：2221-01 应交增值税
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { calcOutputVat, calcPayableVat, calcVatBurdenRate } from './useN2VatEngine'
import { calcSubtotal } from './useN2FormulaEngine'
import type { ChecklistResponse } from './useN2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 增值税测算行（按月/季度） */
export interface N2VatCalcRow {
  /** 期间标识（如"1月"/"第1季度"） */
  period: string
  /** 销售额 */
  salesAmount: number
  /** 适用税率 */
  taxRate: number
  /** 销项税额（公式：销售额×税率） */
  outputVat: number
  /** 进项税额 */
  inputVat: number
  /** 进项转出 */
  inputTransferOut: number
  /** 应交增值税（公式：销项-(进项-转出)） */
  payableVat: number
  /** 已交税额 */
  paidVat: number
  /** 未交税额（应交-已交） */
  unpaidVat: number
}

/** 年度汇总 */
export interface N2VatCalcAnnualSummary {
  totalSales: number
  totalOutputVat: number
  totalInputVat: number
  totalInputTransferOut: number
  totalPayableVat: number
  totalPaidVat: number
  totalUnpaidVat: number
  /** 年度增值税税负率 */
  annualBurdenRate: number
}

/** 申报表核对 */
export interface N2VatDeclarationCheck {
  /** 申报表应交增值税 */
  declaredPayableVat: number
  /** 差异 = 测算 - 申报 */
  diff: number
  isMatch: boolean
}

/** 计算周期模式 */
export type VatCalcPeriodMode = 'monthly' | 'quarterly'

// ─── Constants ───────────────────────────────────────────────────────────────

const MONTHLY_PERIODS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']
const QUARTERLY_PERIODS = ['第1季度', '第2季度', '第3季度', '第4季度']

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseN2VatCalcOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
}

export function useN2VatCalc(options: UseN2VatCalcOptions) {
  const { allResponses, saveField, getField } = options

  // ─── 1. 计算周期模式 ──────────────────────────────────────────────────────

  /** 当前计算周期（月/季） */
  const periodMode: ComputedRef<VatCalcPeriodMode> = computed(() => {
    const mode = getField('6', 'period-mode')
    return mode === 'quarterly' ? 'quarterly' : 'monthly'
  })

  // ─── 2. 增值税测算行数据 ──────────────────────────────────────────────────

  /** 增值税测算各期行（公式列自动计算） */
  const rows: ComputedRef<N2VatCalcRow[]> = computed(() => {
    const itemId = 'N2-6-vat-rows'
    const resp = allResponses.value.get(itemId)
    let raw: any[] = []
    if (resp?.conclusion) {
      try { raw = JSON.parse(resp.conclusion) } catch { raw = [] }
    }

    const periods = periodMode.value === 'quarterly' ? QUARTERLY_PERIODS : MONTHLY_PERIODS

    // 如果有存储数据，使用之；否则生成空行
    if (raw.length > 0) {
      return raw.map((r: any, i: number) => {
        const salesAmount = parseNum(r.salesAmount)
        const taxRate = parseNum(r.taxRate)
        const inputVat = parseNum(r.inputVat)
        const inputTransferOut = parseNum(r.inputTransferOut)
        const paidVat = parseNum(r.paidVat)

        const outputVat = calcOutputVat(salesAmount, taxRate)
        const payableVat = calcPayableVat(outputVat, inputVat, inputTransferOut)

        return {
          period: r.period || periods[i] || `期${i + 1}`,
          salesAmount,
          taxRate,
          outputVat,
          inputVat,
          inputTransferOut,
          payableVat,
          paidVat,
          unpaidVat: payableVat - paidVat,
        }
      })
    }

    // 默认空行
    return periods.map(period => ({
      period,
      salesAmount: 0,
      taxRate: 0.13,
      outputVat: 0,
      inputVat: 0,
      inputTransferOut: 0,
      payableVat: 0,
      paidVat: 0,
      unpaidVat: 0,
    }))
  })

  // ─── 3. 年度汇总 + 税负率 ────────────────────────────────────────────────

  const annualSummary: ComputedRef<N2VatCalcAnnualSummary> = computed(() => {
    const r = rows.value
    const totalSales = calcSubtotal(r.map(x => x.salesAmount))
    const totalOutputVat = calcSubtotal(r.map(x => x.outputVat))
    const totalInputVat = calcSubtotal(r.map(x => x.inputVat))
    const totalInputTransferOut = calcSubtotal(r.map(x => x.inputTransferOut))
    const totalPayableVat = calcSubtotal(r.map(x => x.payableVat))
    const totalPaidVat = calcSubtotal(r.map(x => x.paidVat))
    const totalUnpaidVat = calcSubtotal(r.map(x => x.unpaidVat))
    const annualBurdenRate = calcVatBurdenRate(totalPayableVat, totalSales)

    return {
      totalSales,
      totalOutputVat,
      totalInputVat,
      totalInputTransferOut,
      totalPayableVat,
      totalPaidVat,
      totalUnpaidVat,
      annualBurdenRate,
    }
  })

  // ─── 4. 申报表核对 ────────────────────────────────────────────────────────

  /** 与增值税纳税申报表核对 */
  const declarationCheck: ComputedRef<N2VatDeclarationCheck> = computed(() => {
    const declared = parseNum(getField('6', 'declared-payable-vat'))
    const calculated = annualSummary.value.totalPayableVat
    const diff = parseFloat((calculated - declared).toFixed(2))
    return {
      declaredPayableVat: declared,
      diff,
      isMatch: Math.abs(diff) <= 0.01,
    }
  })

  // ─── 5. 行更新 ────────────────────────────────────────────────────────────

  /**
   * 更新指定期间行的可编辑字段
   */
  async function updateRow(
    periodIndex: number,
    field: 'salesAmount' | 'taxRate' | 'inputVat' | 'inputTransferOut' | 'paidVat',
    value: number,
  ): Promise<void> {
    const stored = getField('6', 'vat-rows') || []
    const raw: any[] = Array.isArray(stored) ? [...stored] : []

    // 确保有足够行
    const periods = periodMode.value === 'quarterly' ? QUARTERLY_PERIODS : MONTHLY_PERIODS
    while (raw.length < periods.length) {
      raw.push({ period: periods[raw.length], taxRate: 0.13 })
    }

    if (periodIndex >= 0 && periodIndex < raw.length) {
      raw[periodIndex] = { ...raw[periodIndex], [field]: value }
      await saveField('6', 'vat-rows', raw)
    }
  }

  /**
   * 切换计算周期模式
   */
  async function setPeriodMode(mode: VatCalcPeriodMode): Promise<void> {
    await saveField('6', 'period-mode', mode)
  }

  // ─── 6. 保存应交增值税到独立字段（供N2-8计税依据 + N2-1回填） ──────────────

  /**
   * 同步年度应交增值税到独立字段
   * - "N2-6-vat-payable" → N2-8 城建税计税依据 (vatToSurtax)
   * - "N2-1-vat-audited" → N2-1 增值税行
   */
  async function syncVatPayable(): Promise<void> {
    await saveField('6', 'vat-payable', annualSummary.value.totalPayableVat)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    periodMode,
    rows,
    annualSummary,
    declarationCheck,
    updateRow,
    setPeriodMode,
    syncVatPayable,
  }
}

export default useN2VatCalc
