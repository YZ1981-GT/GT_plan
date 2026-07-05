/**
 * useF5MonthlyDetail — F5-2 主营业务成本月度明细（24列拆2区段）
 *
 * Spec: .kiro/specs/f5-cost-of-sales/ Task 5.1
 *
 * 上半年区段(13列)：品种|1~6月|上半年合计|占比|月均|最高月|最低月|波动系数
 * 下半年区段(11列)：7~12月|下半年合计|全年合计|上期合计|变动额|变动率
 * 公式链：上半年合计=1~6月SUM / 下半年合计=7~12月SUM / 全年=上半年+下半年 / 变动额/率 / 波动系数
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcSubtotal,
  calcChangeAmount,
  calcChangeRate,
  calcCoeffOfVariation,
} from './useF5CosOfFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface UseF5MonthlyDetailOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

/** 月度明细行（24列，含2区段计算字段） */
export interface MonthlyDetailRow {
  id: string
  product: string
  // 上半年
  month1: number
  month2: number
  month3: number
  month4: number
  month5: number
  month6: number
  halfYear1Total: number // 公式=1~6月SUM
  halfYear1Ratio: number | 'N/A' // 占比(公式)：本品种全年/所有品种全年
  halfYear1Avg: number // 月均(公式)=上半年合计/6
  halfYear1Max: number // 最高月(1~6)
  halfYear1Min: number // 最低月(1~6)
  coeffOfVariation: number // 波动系数(公式)=stddev/mean(全12月)
  // 下半年
  month7: number
  month8: number
  month9: number
  month10: number
  month11: number
  month12: number
  halfYear2Total: number // 公式=7~12月SUM
  yearTotal: number // 公式=上半年+下半年
  priorYearTotal: number // 上期合计
  changeAmount: number // 变动额(公式)
  changeRate: number | 'N/A' // 变动率(公式)
}

/** 持久化用（仅原始输入字段） */
interface StoredMonthlyRow {
  id: string
  product: string
  months: number[] // 长度12
  priorYearTotal: number
}

const STORAGE_KEY = 'F5-2-monthly-rows'
const HIGH_VOLATILITY_THRESHOLD = 0.5
const CHANGE_RATE_THRESHOLD = 20

/** 上半年区段列配置（13列） */
export const FIRST_HALF_COLUMNS = [
  { key: 'product', label: '品种', editable: true },
  { key: 'month1', label: '1月', editable: true },
  { key: 'month2', label: '2月', editable: true },
  { key: 'month3', label: '3月', editable: true },
  { key: 'month4', label: '4月', editable: true },
  { key: 'month5', label: '5月', editable: true },
  { key: 'month6', label: '6月', editable: true },
  { key: 'halfYear1Total', label: '上半年合计', editable: false, formula: '1月+…+6月' },
  { key: 'halfYear1Ratio', label: '上半年占比', editable: false, formula: '本品种全年/合计全年×100' },
  { key: 'halfYear1Avg', label: '上半年月均', editable: false, formula: '上半年合计/6' },
  { key: 'halfYear1Max', label: '最高月', editable: false },
  { key: 'halfYear1Min', label: '最低月', editable: false },
  { key: 'coeffOfVariation', label: '波动系数', editable: false, formula: '标准差/均值(12月)' },
] as const

/** 下半年+合计区段列配置（11列） */
export const SECOND_HALF_COLUMNS = [
  { key: 'product', label: '品种', editable: false },
  { key: 'month7', label: '7月', editable: true },
  { key: 'month8', label: '8月', editable: true },
  { key: 'month9', label: '9月', editable: true },
  { key: 'month10', label: '10月', editable: true },
  { key: 'month11', label: '11月', editable: true },
  { key: 'month12', label: '12月', editable: true },
  { key: 'halfYear2Total', label: '下半年合计', editable: false, formula: '7月+…+12月' },
  { key: 'yearTotal', label: '全年合计', editable: false, formula: '上半年+下半年' },
  { key: 'priorYearTotal', label: '上期合计', editable: true },
  { key: 'changeAmount', label: '变动额', editable: false, formula: '全年-上期' },
  { key: 'changeRate', label: '变动率%', editable: false, formula: '变动额/上期×100' },
] as const

function safeParse(jsonStr: string | null | undefined): StoredMonthlyRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: any) => ({
      id: String(r.id ?? Date.now()),
      product: String(r.product ?? ''),
      months: Array.isArray(r.months) ? r.months.slice(0, 12).map(parseNum) : new Array(12).fill(0),
      priorYearTotal: parseNum(r.priorYearTotal),
    }))
  } catch {
    return []
  }
}

function computeRow(stored: StoredMonthlyRow, allYearTotal: number): MonthlyDetailRow {
  const m = stored.months.concat(new Array(12).fill(0)).slice(0, 12)
  const h1 = calcSubtotal(m.slice(0, 6))
  const h2 = calcSubtotal(m.slice(6, 12))
  const year = h1 + h2
  const changeAmount = calcChangeAmount(year, stored.priorYearTotal)
  return {
    id: stored.id,
    product: stored.product,
    month1: m[0], month2: m[1], month3: m[2], month4: m[3], month5: m[4], month6: m[5],
    halfYear1Total: h1,
    halfYear1Ratio: allYearTotal === 0 ? 'N/A' : (year / allYearTotal) * 100,
    halfYear1Avg: h1 / 6,
    halfYear1Max: Math.max(...m.slice(0, 6)),
    halfYear1Min: Math.min(...m.slice(0, 6)),
    coeffOfVariation: calcCoeffOfVariation(m),
    month7: m[6], month8: m[7], month9: m[8], month10: m[9], month11: m[10], month12: m[11],
    halfYear2Total: h2,
    yearTotal: year,
    priorYearTotal: stored.priorYearTotal,
    changeAmount,
    changeRate: calcChangeRate(year, stored.priorYearTotal),
  }
}

export function useF5MonthlyDetail(options: UseF5MonthlyDetailOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? computed(() => false)

  const storedRows = computed<StoredMonthlyRow[]>(() =>
    safeParse(allResponses.value.get(STORAGE_KEY)?.remark),
  )

  const allYearTotal = computed(() =>
    calcSubtotal(storedRows.value.map((r) => calcSubtotal(r.months.slice(0, 12)))),
  )

  const rows: ComputedRef<MonthlyDetailRow[]> = computed(() =>
    storedRows.value.map((s) => computeRow(s, allYearTotal.value)),
  )

  /** 底部合计行 */
  const totalRow = computed(() => {
    const monthTotals = new Array(12).fill(0)
    let priorTotal = 0
    for (const r of storedRows.value) {
      for (let i = 0; i < 12; i++) monthTotals[i] += r.months[i] ?? 0
      priorTotal += r.priorYearTotal
    }
    const h1 = calcSubtotal(monthTotals.slice(0, 6))
    const h2 = calcSubtotal(monthTotals.slice(6, 12))
    const year = h1 + h2
    return {
      monthTotals,
      halfYear1Total: h1,
      halfYear2Total: h2,
      yearTotal: year,
      priorYearTotal: priorTotal,
      changeAmount: calcChangeAmount(year, priorTotal),
      changeRate: calcChangeRate(year, priorTotal),
    }
  })

  /** 高亮判定：变动率绝对值>20% 或 波动系数>0.5 */
  function isRowHighlighted(row: MonthlyDetailRow): boolean {
    const rateExceed = row.changeRate !== 'N/A' && Math.abs(row.changeRate) > CHANGE_RATE_THRESHOLD
    return rateExceed || row.coeffOfVariation > HIGH_VOLATILITY_THRESHOLD
  }

  function isVolatilityHigh(row: MonthlyDetailRow): boolean {
    return row.coeffOfVariation > HIGH_VOLATILITY_THRESHOLD
  }

  function persist(rows: StoredMonthlyRow[]): void {
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: JSON.stringify(rows) })
  }

  /** 更新单元格（区段间通过同一 storedRow 共享 → 行同步） */
  function updateCell(id: string, key: string, value: number | string): void {
    if (readonly.value) return
    const stored = safeParse(allResponses.value.get(STORAGE_KEY)?.remark)
    const idx = stored.findIndex((r) => r.id === id)
    if (idx === -1) return
    const monthMatch = /^month(\d{1,2})$/.exec(key)
    if (monthMatch) {
      const mIdx = Number(monthMatch[1]) - 1
      if (mIdx >= 0 && mIdx < 12) stored[idx].months[mIdx] = parseNum(value)
    } else if (key === 'priorYearTotal') {
      stored[idx].priorYearTotal = parseNum(value)
    } else if (key === 'product') {
      stored[idx].product = String(value ?? '')
    }
    persist(stored)
  }

  function addRow(product: string): void {
    if (readonly.value || !product) return
    const stored = safeParse(allResponses.value.get(STORAGE_KEY)?.remark)
    stored.push({ id: `m-${Date.now()}`, product, months: new Array(12).fill(0), priorYearTotal: 0 })
    persist(stored)
  }

  function removeRow(id: string): void {
    if (readonly.value) return
    const stored = safeParse(allResponses.value.get(STORAGE_KEY)?.remark).filter((r) => r.id !== id)
    persist(stored)
  }

  return {
    rows,
    totalRow,
    allYearTotal,
    firstHalfColumns: FIRST_HALF_COLUMNS,
    secondHalfColumns: SECOND_HALF_COLUMNS,
    isRowHighlighted,
    isVolatilityHigh,
    updateCell,
    addRow,
    removeRow,
  }
}

export default useF5MonthlyDetail
