/**
 * F2 合同履约成本测试表（示例）— 源模板编制参考数据
 */
export const F2_CONTRACT_COST_TEST_EXAMPLE_TITLE = '合同履约成本测试表（编制参考示例）'

export const F2_CONTRACT_COST_TEST_OBJECTIVES = [
  '验证合同履约成本资本化判断的合理性；',
  '对资本化成本执行摊销测试，核对本期及累计摊销金额。',
]

export interface CapitalizationExampleRow {
  component: string
  amount: number
  capitalized: '是' | '否'
  indexRef: string
}

export interface AmortizationExampleRow {
  component: string
  initialAmount: number
  monthsBefore: number
  cumulativeMonths: number
  amortTerm: number
  bookPeriodAmort: number
}

export const CAPITALIZATION_EXAMPLE_ROWS: CapitalizationExampleRow[] = [
  { component: '设计服务', amount: 50000, capitalized: '是', indexRef: '' },
  { component: '审计', amount: 200000, capitalized: '否', indexRef: '' },
  { component: '软件', amount: 50000, capitalized: '否', indexRef: '' },
  { component: '数据中心测试', amount: 50000, capitalized: '是', indexRef: '' },
]

export const AMORTIZATION_EXAMPLE_ROWS: AmortizationExampleRow[] = [
  {
    component: '设计服务',
    initialAmount: 50000,
    monthsBefore: 12,
    cumulativeMonths: 24,
    amortTerm: 60,
    bookPeriodAmort: 10000,
  },
  {
    component: '数据中心测试',
    initialAmount: 50000,
    monthsBefore: 6,
    cumulativeMonths: 18,
    amortTerm: 60,
    bookPeriodAmort: 10000,
  },
]

export const F2_CONTRACT_COST_TEST_FORMULAS = [
  { no: '⑥', label: '测试本期摊销金额', formula: '（初始金额 ÷ 摊销期限）×（累计摊销月份 − 本期前已摊月份）' },
  { no: '⑧', label: '本期摊销差异', formula: '测试本期摊销金额 − 账面本期摊销金额' },
  { no: '⑨', label: '累计应摊销额', formula: '（初始金额 ÷ 摊销期限）× 累计摊销月份' },
  { no: '⑪', label: '累计摊销差异', formula: '累计应摊销额 − 账面累计摊销额' },
]

export function calcPeriodAmort(
  initial: number,
  term: number,
  cumulativeMonths: number,
  monthsBefore: number,
): number {
  if (!term) return 0
  return (initial / term) * (cumulativeMonths - monthsBefore)
}

export function calcCumulativeAmort(
  initial: number,
  term: number,
  cumulativeMonths: number,
): number {
  if (!term) return 0
  return (initial / term) * cumulativeMonths
}

export interface EnrichedAmortizationExampleRow extends AmortizationExampleRow {
  testedPeriodAmort: number
  periodVariance: number
  cumulativeShouldAmort: number
  bookCumulative: number
  cumulativeVariance: number
}

export function enrichAmortizationRows(
  rows: AmortizationExampleRow[],
): EnrichedAmortizationExampleRow[] {
  return rows.map((r) => {
    const testedPeriodAmort = calcPeriodAmort(
      r.initialAmount,
      r.amortTerm,
      r.cumulativeMonths,
      r.monthsBefore,
    )
    const cumulativeShouldAmort = calcCumulativeAmort(
      r.initialAmount,
      r.amortTerm,
      r.cumulativeMonths,
    )
    const bookCumulative = (r.initialAmount / r.amortTerm) * r.monthsBefore + r.bookPeriodAmort
    return {
      ...r,
      testedPeriodAmort,
      periodVariance: testedPeriodAmort - r.bookPeriodAmort,
      cumulativeShouldAmort,
      bookCumulative,
      cumulativeVariance: cumulativeShouldAmort - bookCumulative,
    }
  })
}

export function sumCapitalization(rows: CapitalizationExampleRow[]): number {
  return rows.reduce((s, r) => s + r.amount, 0)
}

export function isContractCostTestExampleSheet(sheetName?: string): boolean {
  if (!sheetName) return false
  return /合同履约成本测试.*示例|示例.*合同履约成本测试/.test(sheetName)
}
