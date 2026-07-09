/**
 * useN2PropertyTax — N2-9 房产税测算表 composable
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 3.4
 * Requirements: 6.1-6.4
 *
 * 职责：
 * - 各房产逐行：计税方式(从价/从租) + 计税依据 + 应交
 * - Uses calcPropertyTaxByValue, calcPropertyTaxByRent from useN2MultiTaxEngine
 * - 扣除比例地区配置(10%~30%)
 * - 动态行
 *
 * 公式：从价=原值×(1-扣除比例)×1.2%；从租=租金收入×12%
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { calcPropertyTaxByValue, calcPropertyTaxByRent } from './useN2MultiTaxEngine'
import { calcSubtotal } from './useN2FormulaEngine'
import type { ChecklistResponse } from './useN2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 计税方式 */
export type PropertyTaxMethod = '从价' | '从租'

/** 房产税测算行 */
export interface N2PropertyTaxRow {
  /** 行ID */
  id: string
  /** 房产名称/描述 */
  propertyName: string
  /** 计税方式 */
  method: PropertyTaxMethod
  /** 房产原值（从价时使用） */
  originalValue: number
  /** 租金收入（从租时使用） */
  rentIncome: number
  /** 扣除比例（从价时使用，0.10~0.30） */
  deductRate: number
  /** 应交房产税（公式列） */
  taxAmount: number
}

/** 房产税汇总 */
export interface N2PropertyTaxSummary {
  /** 从价计征合计 */
  byValueTotal: number
  /** 从租计征合计 */
  byRentTotal: number
  /** 应交房产税合计 */
  total: number
  /** 房产数量 */
  propertyCount: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 常见扣除比例配置（各省份） */
export const DEDUCT_RATE_OPTIONS: Array<{ label: string; value: number }> = [
  { label: '10%', value: 0.10 },
  { label: '15%', value: 0.15 },
  { label: '20%', value: 0.20 },
  { label: '25%', value: 0.25 },
  { label: '30%', value: 0.30 },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function generateRowId(): string {
  return `prop-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseN2PropertyTaxOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
}

export function useN2PropertyTax(options: UseN2PropertyTaxOptions) {
  const { allResponses, saveField, getField } = options

  // ─── 1. 地区扣除比例配置 ──────────────────────────────────────────────────

  /** 当前地区默认扣除比例 */
  const defaultDeductRate: ComputedRef<number> = computed(() => {
    const stored = getField('9', 'default-deduct-rate')
    const rate = parseNum(stored)
    // 有效范围 10%~30%
    return (rate >= 0.10 && rate <= 0.30) ? rate : 0.20
  })

  // ─── 2. 房产税测算行数据 ──────────────────────────────────────────────────

  /** 各房产测算行（公式列自动计算） */
  const rows: ComputedRef<N2PropertyTaxRow[]> = computed(() => {
    const itemId = 'N2-9-property-rows'
    const resp = allResponses.value.get(itemId)
    let raw: any[] = []
    if (resp?.conclusion) {
      try { raw = JSON.parse(resp.conclusion) } catch { raw = [] }
    }

    return raw.map((r: any) => {
      const method: PropertyTaxMethod = r.method === '从租' ? '从租' : '从价'
      const originalValue = parseNum(r.originalValue)
      const rentIncome = parseNum(r.rentIncome)
      const deductRate = parseNum(r.deductRate) || defaultDeductRate.value

      // 根据计税方式计算
      const taxAmount = method === '从价'
        ? calcPropertyTaxByValue(originalValue, deductRate)
        : calcPropertyTaxByRent(rentIncome)

      return {
        id: r.id || generateRowId(),
        propertyName: r.propertyName || '',
        method,
        originalValue,
        rentIncome,
        deductRate,
        taxAmount,
      }
    })
  })

  // ─── 3. 汇总 ──────────────────────────────────────────────────────────────

  const summary: ComputedRef<N2PropertyTaxSummary> = computed(() => {
    const r = rows.value
    const byValueRows = r.filter(x => x.method === '从价')
    const byRentRows = r.filter(x => x.method === '从租')
    const byValueTotal = calcSubtotal(byValueRows.map(x => x.taxAmount))
    const byRentTotal = calcSubtotal(byRentRows.map(x => x.taxAmount))
    return {
      byValueTotal,
      byRentTotal,
      total: byValueTotal + byRentTotal,
      propertyCount: r.length,
    }
  })

  // ─── 4. 动态行操作 ────────────────────────────────────────────────────────

  /**
   * 新增房产行（先ElMessageBox.prompt输入房产名称）
   */
  async function addRow(propertyName: string, method: PropertyTaxMethod = '从价'): Promise<void> {
    const stored = getField('9', 'property-rows') || []
    const raw: any[] = Array.isArray(stored) ? [...stored] : []

    raw.push({
      id: generateRowId(),
      propertyName,
      method,
      originalValue: 0,
      rentIncome: 0,
      deductRate: defaultDeductRate.value,
    })

    await saveField('9', 'property-rows', raw)
  }

  /**
   * 删除指定行
   */
  async function removeRow(rowId: string): Promise<void> {
    const stored = getField('9', 'property-rows') || []
    const raw: any[] = Array.isArray(stored) ? [...stored] : []
    const filtered = raw.filter(r => r.id !== rowId)
    await saveField('9', 'property-rows', filtered)
  }

  /**
   * 更新指定行字段
   */
  async function updateRow(
    rowId: string,
    field: 'propertyName' | 'method' | 'originalValue' | 'rentIncome' | 'deductRate',
    value: any,
  ): Promise<void> {
    const stored = getField('9', 'property-rows') || []
    const raw: any[] = Array.isArray(stored) ? [...stored] : []
    const idx = raw.findIndex(r => r.id === rowId)
    if (idx >= 0) {
      raw[idx] = { ...raw[idx], [field]: value }
      await saveField('9', 'property-rows', raw)
    }
  }

  /**
   * 设置地区默认扣除比例
   */
  async function setDefaultDeductRate(rate: number): Promise<void> {
    await saveField('9', 'default-deduct-rate', rate)
  }

  /**
   * 同步房产税合计到独立字段（供N2-1回填 + N4联动）
   */
  async function syncTotal(): Promise<void> {
    await saveField('9', 'property-tax-total', summary.value.total)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    defaultDeductRate,
    rows,
    summary,
    addRow,
    removeRow,
    updateRow,
    setDefaultDeductRate,
    syncTotal,
  }
}

export default useN2PropertyTax
