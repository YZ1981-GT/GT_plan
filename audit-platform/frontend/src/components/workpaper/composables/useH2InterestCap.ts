/**
 * useH2InterestCap — H2-10/11 利息资本化共用 composable
 *
 * 互斥分支：H2-10 无专门借款 | H2-11 有专门借款
 * - H2-10：一般借款加权资本化率 × 月度加权支出（xlsx 半月平均法）
 * - H2-11：专门借款(利息-闲置收益) + 超出部分×一般借款利率
 * 一般借款明细可从 H2-10 带入 H2-11 补充段，避免重复录入
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.12 | Requirements: 10.1-10.10
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcWeightedCapRate,
  calcWeightedExpenditure,
  calcCapAmountNoBorrow,
  calcSpecialLoanCap,
  calcGeneralLoanSupp,
  calcTotalCapWithBorrow,
  calcWeightedPrincipal,
  calcCapRateFromActualInterest,
  calcMonthlyWeightedExpChain,
  calcExpTotal,
  annualRateToMonthly,
  calcExcessWeightedExp,
  calcCapDiffRate,
  type MonthlyExpInput,
} from './useH2InterestCapEngine'
import { calcSubtotal } from './useH2FormulaEngine'
import {
  H2_INTEREST_BRANCH_KEY,
  inactiveInterestCapResultKey,
  type InterestCapBranch as BranchFromHelper,
} from './h2InterestCapBranch'
import { pullL1LoansForH2, normalizeL1RateToPercent } from './h2L1LoanPull'

// ─── Types ───────────────────────────────────────────────────────────────────

export type InterestCapBranch = BranchFromHelper

export interface LoanItem {
  rowId: string
  lender: string
  principal: number
  /** 年利率（百分数，如 5 表示 5%） */
  rate: number
  days: number
  /** 当期天数（年口径常用 360/365） */
  periodDays: number
  /** 账面实际利息费用（优先于本金×利率匡算） */
  actualInterest: number
  /** 公式：本金×利率×天数/365（rate 为百分数） */
  interest: number
  /** 公式：本金×计息天数/当期天数 */
  weightedPrincipal: number
  startDate: string
  endDate: string
  remark: string
}

export interface ExpenditureItem {
  rowId: string
  month: string
  amount: number
  days: number
  weightedAmount: number
}

/** 月度工程支出行（对齐 xlsx H2-10） */
export interface MonthlyExpRow extends MonthlyExpInput {
  rowId: string
  /** opening | 1..12 | total | transfer | ending */
  rowType: 'opening' | 'month' | 'total' | 'transfer' | 'ending'
  monthLabel: string
  /** 公式列 */
  expTotal: number
  weightedExp: number
  capAmount: number
  remark: string
}

export interface SpecialLoanData {
  specialInterest: number
  idleIncome: number
  specialLoanAmount: number
  excessWeightedExp: number
}

export interface InterestCapResult {
  totalCap: number
  byProject: Record<string, number>
  capRate: number
  branch: InterestCapBranch
}

// ─── Constants ───────────────────────────────────────────────────────────────

const BRANCH_KEY = H2_INTEREST_BRANCH_KEY
const LOANS_KEY_10 = 'H2-10-loans'
const EXPENDITURES_KEY_10 = 'H2-10-expenditures'
const MONTHLY_KEY_10 = 'H2-10-monthly-exp'
const MONTHLY_RATE_KEY_10 = 'H2-10-monthly-cap-rate'
const CLIENT_CAP_KEY_10 = 'H2-10-client-cap'
const LOANS_KEY_11 = 'H2-11-loans'
const SPECIAL_KEY_11 = 'H2-11-special-data'
const MONTHLY_KEY_11 = 'H2-11-monthly-exp'
const MONTHLY_RATE_KEY_11 = 'H2-11-monthly-cap-rate'
const CLIENT_CAP_KEY_11 = 'H2-11-client-cap'
const RESULT_KEY_10 = 'H2-10-cap-result'
const RESULT_KEY_11 = 'H2-11-cap-result'
const NOTE_KEY = 'H2-10-audit-note'
const CONCLUSION_KEY = 'H2-10-audit-conclusion'
const TOTAL_DAYS = 365

const MONTH_LABELS = [
  '1月', '2月', '3月', '4月', '5月', '6月',
  '7月', '8月', '9月', '10月', '11月', '12月',
]

function _emptyExpFields(): MonthlyExpInput {
  return {
    prelimDev: 0, engCost: 0, borrowCost: 0, install: 0, land: 0,
    decrease: 0, prepaid: 0, specialLoanUsed: 0,
  }
}

function _newMonthlyRows(): MonthlyExpRow[] {
  const rows: MonthlyExpRow[] = [
    {
      rowId: 'opening', rowType: 'opening', monthLabel: '年初余额',
      ..._emptyExpFields(), expTotal: 0, weightedExp: 0, capAmount: 0, remark: '',
    },
  ]
  for (let i = 0; i < 12; i++) {
    rows.push({
      rowId: `m${i + 1}`, rowType: 'month', monthLabel: MONTH_LABELS[i],
      ..._emptyExpFields(), expTotal: 0, weightedExp: 0, capAmount: 0, remark: '',
    })
  }
  return rows
}

function _mapMonthlyRow(r: any, idx: number): MonthlyExpRow {
  return {
    rowId: r.rowId ?? (idx === 0 ? 'opening' : `m${idx}`),
    rowType: (r.rowType ?? (idx === 0 ? 'opening' : 'month')) as MonthlyExpRow['rowType'],
    monthLabel: r.monthLabel ?? (idx === 0 ? '年初余额' : MONTH_LABELS[idx - 1] ?? `${idx}月`),
    prelimDev: Number(r.prelimDev) || 0,
    engCost: Number(r.engCost) || 0,
    borrowCost: Number(r.borrowCost) || 0,
    install: Number(r.install) || 0,
    land: Number(r.land) || 0,
    decrease: Number(r.decrease) || 0,
    prepaid: Number(r.prepaid) || 0,
    specialLoanUsed: Number(r.specialLoanUsed) || 0,
    expTotal: 0,
    weightedExp: 0,
    capAmount: 0,
    remark: r.remark ?? '',
  }
}

/** rate 百分数 → 小数 */
function _toDecimalRate(ratePct: number): number {
  return (Number(ratePct) || 0) / 100
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2InterestCap(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  interestCapForDetail?: ComputedRef<{ totalCap: number; byProject: Record<string, number> }>
  onSave?: (itemId: string, value: any) => void
  onPublishEvent?: (event: string, payload: any) => void
}) {
  const branch = ref<InterestCapBranch>('noBorrow')

  const loansNoBorrow = ref<LoanItem[]>([])
  const expenditures = ref<ExpenditureItem[]>([])
  const monthlyRows = ref<MonthlyExpRow[]>(_newMonthlyRows())
  /** 月资本化率覆盖（百分数）；空则用年利率/12 */
  const monthlyCapRatePct = ref<number | null>(null)
  const clientCapAmount = ref(0)
  /** L1 借款带入状态 */
  const l1Pulling = ref(false)

  const loansWithBorrow = ref<LoanItem[]>([])
  const specialLoanData = ref<SpecialLoanData>({
    specialInterest: 0,
    idleIncome: 0,
    specialLoanAmount: 0,
    excessWeightedExp: 0,
  })
  /** H2-11 月度支出（含 SP 列），与 H2-10 独立存储 */
  const monthlyRows11 = ref<MonthlyExpRow[]>(_newMonthlyRows())
  const monthlyCapRatePct11 = ref<number | null>(null)
  const clientCapAmount11 = ref(0)

  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return typeof raw === 'object' ? raw : null }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _getNumber(itemId: string): number | null {
    const item = options.allResponses.value.get(itemId)
    const raw = item?.remark ?? item?.conclusion
    if (raw == null || raw === '') return null
    const n = Number(raw)
    return Number.isFinite(n) ? n : null
  }

  /** 兼容历史：rate≤1 视为小数并转为百分数 */
  function _normalizeRatePct(raw: number): number {
    const n = Number(raw) || 0
    if (n > 0 && n <= 1) return n * 100
    return n
  }

  function _recalcLoan(loan: LoanItem): void {
    const days = loan.days || 0
    const period = loan.periodDays || TOTAL_DAYS
    loan.weightedPrincipal = calcWeightedPrincipal(loan.principal, days, period)
    const computed = loan.principal * _toDecimalRate(loan.rate) * days / TOTAL_DAYS
    // 若未填账面利息，用匡算值；已填则以账面为准（资本化率倒算口径）
    if (!loan.actualInterest) {
      loan.actualInterest = computed
    }
    loan.interest = loan.actualInterest || computed
  }

  function _recalcExpenditure(exp: ExpenditureItem): void {
    exp.weightedAmount = exp.amount * exp.days
  }

  function _mapLoan(r: any): LoanItem {
    const loan: LoanItem = {
      rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      lender: r.lender ?? '',
      principal: Number(r.principal) || 0,
      rate: _normalizeRatePct(Number(r.rate) || 0),
      days: Number(r.days) || 0,
      periodDays: Number(r.periodDays) || TOTAL_DAYS,
      actualInterest: Number(r.actualInterest) || 0,
      interest: 0,
      weightedPrincipal: 0,
      startDate: r.startDate ?? '',
      endDate: r.endDate ?? '',
      remark: r.remark ?? '',
    }
    _recalcLoan(loan)
    return loan
  }

  function _daysBetween(start: string, end: string): number {
    if (!start || !end) return 0
    const a = new Date(start)
    const b = new Date(end)
    if (Number.isNaN(a.getTime()) || Number.isNaN(b.getTime())) return 0
    const diff = Math.round((b.getTime() - a.getTime()) / 86400000)
    return Math.max(diff, 0)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  function initFromAllResponses(): void {
    const branchVal = _getString(BRANCH_KEY)
    branch.value = branchVal === 'withBorrow' ? 'withBorrow' : 'noBorrow'

    const loans10 = _getJson(LOANS_KEY_10)
    if (Array.isArray(loans10)) {
      loansNoBorrow.value = loans10.map(_mapLoan)
    }

    const exps = _getJson(EXPENDITURES_KEY_10)
    if (Array.isArray(exps)) {
      expenditures.value = exps.map((r: any) => {
        const exp: ExpenditureItem = {
          rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
          month: r.month ?? '',
          amount: Number(r.amount) || 0,
          days: Number(r.days) || 0,
          weightedAmount: 0,
        }
        _recalcExpenditure(exp)
        return exp
      })
    }

    const monthly = _getJson(MONTHLY_KEY_10)
    if (Array.isArray(monthly) && monthly.length >= 13) {
      monthlyRows.value = monthly.map(_mapMonthlyRow)
    } else if (monthlyRows.value.length < 13) {
      monthlyRows.value = _newMonthlyRows()
    }

    const mRate = _getNumber(MONTHLY_RATE_KEY_10)
    monthlyCapRatePct.value = mRate

    const clientCap = _getNumber(CLIENT_CAP_KEY_10)
    if (clientCap != null) clientCapAmount.value = clientCap

    const loans11 = _getJson(LOANS_KEY_11)
    if (Array.isArray(loans11)) {
      loansWithBorrow.value = loans11.map(_mapLoan)
    }

    const special = _getJson(SPECIAL_KEY_11)
    if (special && typeof special === 'object') {
      specialLoanData.value = {
        specialInterest: Number(special.specialInterest) || 0,
        idleIncome: Number(special.idleIncome) || 0,
        specialLoanAmount: Number(special.specialLoanAmount) || 0,
        excessWeightedExp: Number(special.excessWeightedExp) || 0,
      }
    }

    const monthly11 = _getJson(MONTHLY_KEY_11)
    if (Array.isArray(monthly11) && monthly11.length >= 13) {
      monthlyRows11.value = monthly11.map(_mapMonthlyRow)
    } else if (monthlyRows11.value.length < 13) {
      monthlyRows11.value = _newMonthlyRows()
    }

    const mRate11 = _getNumber(MONTHLY_RATE_KEY_11)
    monthlyCapRatePct11.value = mRate11

    const clientCap11 = _getNumber(CLIENT_CAP_KEY_11)
    if (clientCap11 != null) clientCapAmount11.value = clientCap11

    // 账面资本化：优先手工录入；否则从 H2-2 利息列合计兜底
    if (clientCap == null) {
      const h2_2_resp = options.allResponses.value.get('H2-2-rows')
      const h2_2_raw = h2_2_resp?.remark ?? h2_2_resp?.conclusion
      if (h2_2_raw) {
        try {
          const h2Rows = JSON.parse(h2_2_raw)
          if (Array.isArray(h2Rows)) {
            clientCapAmount.value = calcSubtotal(h2Rows.map((r: any) => Number(r.increaseInterest) || 0))
          }
        } catch { /* ignore */ }
      }
    }
    if (clientCap11 == null && clientCapAmount.value) {
      clientCapAmount11.value = clientCapAmount.value
    }

    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed: H2-10 无专门借款 ────────────────────────────────────────────

  /** 年加权资本化率（小数）— 账面利息 / 本金加权平均 */
  const annualCapRate: ComputedRef<number> = computed(() =>
    calcCapRateFromActualInterest(loansNoBorrow.value.map(l => ({
      weightedPrincipal: l.weightedPrincipal,
      actualInterest: l.actualInterest || l.interest,
    }))),
  )

  /** 兼容旧口径：按名义利率加权 */
  const weightedCapRate: ComputedRef<number> = computed(() =>
    calcWeightedCapRate(loansNoBorrow.value.map(l => ({
      principal: l.principal, rate: _toDecimalRate(l.rate), days: l.days || TOTAL_DAYS,
    }))),
  )

  /** 有效年资本化率：有账面利息用倒算，否则用名义加权 */
  const effectiveAnnualCapRate: ComputedRef<number> = computed(() => {
    const fromActual = annualCapRate.value
    if (fromActual > 0) return fromActual
    return weightedCapRate.value
  })

  /** 月资本化率（小数） */
  const monthlyCapRate: ComputedRef<number> = computed(() => {
    if (monthlyCapRatePct.value != null && monthlyCapRatePct.value > 0) {
      return _toDecimalRate(monthlyCapRatePct.value)
    }
    return annualRateToMonthly(effectiveAnnualCapRate.value)
  })

  /** 刷新月度公式列并返回测算合计 */
  const monthlyCalc: ComputedRef<{
    rows: MonthlyExpRow[]
    yearCapTotal: number
    bookBorrowCost: number
    difference: number
  }> = computed(() => {
    const src = monthlyRows.value
    const opening = src.find(r => r.rowType === 'opening') ?? src[0]
    const months = src.filter(r => r.rowType === 'month')
    const chain = calcMonthlyWeightedExpChain(opening, months)
    const rate = monthlyCapRate.value

    const out: MonthlyExpRow[] = src.map((r) => {
      const expTotal = calcExpTotal(r)
      return { ...r, expTotal, weightedExp: r.weightedExp, capAmount: r.capAmount }
    })

    if (out[0]) {
      out[0].expTotal = calcExpTotal(opening)
      out[0].weightedExp = chain.openingWeighted
      out[0].capAmount = 0
    }
    months.forEach((_, i) => {
      const row = out[i + 1]
      if (!row) return
      row.expTotal = calcExpTotal(months[i])
      row.weightedExp = chain.monthlyWeighted[i] ?? 0
      row.capAmount = calcCapAmountNoBorrow(row.weightedExp, rate)
    })

    const yearCapTotal = calcSubtotal(out.filter(r => r.rowType === 'month').map(r => r.capAmount))
    const bookBorrowCost = calcSubtotal(months.map(m => m.borrowCost))
    return {
      rows: out,
      yearCapTotal,
      bookBorrowCost,
      difference: yearCapTotal - bookBorrowCost,
    }
  })

  const weightedExpenditure: ComputedRef<number> = computed(() => {
    const lastMonth = monthlyCalc.value.rows.filter(r => r.rowType === 'month').at(-1)
    if (lastMonth && lastMonth.weightedExp !== 0) return lastMonth.weightedExp
    return calcWeightedExpenditure(
      expenditures.value.map(e => ({ amount: e.amount, days: e.days })),
      TOTAL_DAYS,
    )
  })

  /** 测算资本化金额：优先月度链合计，否则日加权×年利率 */
  const capAmountNoBorrow: ComputedRef<number> = computed(() => {
    if (monthlyCalc.value.yearCapTotal !== 0) return monthlyCalc.value.yearCapTotal
    const hasMonthlyInput = monthlyRows.value.some(r =>
      r.prelimDev || r.engCost || r.borrowCost || r.install || r.land || r.prepaid || r.decrease,
    )
    if (hasMonthlyInput) return monthlyCalc.value.yearCapTotal
    return calcCapAmountNoBorrow(weightedExpenditure.value, effectiveAnnualCapRate.value)
  })

  const totalInterestNoBorrow: ComputedRef<number> = computed(() =>
    calcSubtotal(loansNoBorrow.value.map(l => l.actualInterest || l.interest)),
  )

  const expenseAmount: ComputedRef<number> = computed(() =>
    totalInterestNoBorrow.value - capAmountNoBorrow.value,
  )

  /** 与账面差异：测算 − 账面（账面优先取手工/H2-2，其次月表借款费用合计） */
  const bookCapForCompare: ComputedRef<number> = computed(() => {
    if (clientCapAmount.value) return clientCapAmount.value
    return monthlyCalc.value.bookBorrowCost
  })

  const capDifference: ComputedRef<number> = computed(() => {
    if (branch.value === 'noBorrow') {
      return capAmountNoBorrow.value - bookCapForCompare.value
    }
    return capAmountWithBorrow.value - bookCapForCompare11.value
  })

  const exceedsInterestCeiling: ComputedRef<boolean> = computed(() =>
    capAmountNoBorrow.value > totalInterestNoBorrow.value + 0.005,
  )

  // ─── Computed: H2-11 有专门借款 ────────────────────────────────────────────

  const specialLoanCap: ComputedRef<number> = computed(() =>
    calcSpecialLoanCap(specialLoanData.value.specialInterest, specialLoanData.value.idleIncome),
  )

  const generalCapRate: ComputedRef<number> = computed(() => {
    const fromActual = calcCapRateFromActualInterest(loansWithBorrow.value.map(l => ({
      weightedPrincipal: l.weightedPrincipal,
      actualInterest: l.actualInterest || l.interest,
    })))
    if (fromActual > 0) return fromActual
    return calcWeightedCapRate(loansWithBorrow.value.map(l => ({
      principal: l.principal, rate: _toDecimalRate(l.rate), days: l.days || TOTAL_DAYS,
    })))
  })

  /**
   * 超额加权支出：优先手工 excessWeightedExp；
   * 若为 0 且已填专门借款金额，则用「累计支出加权 − 专门借款」推导（对齐 CAS17）
   */
  const effectiveExcessWeightedExp: ComputedRef<number> = computed(() => {
    const manual = specialLoanData.value.excessWeightedExp
    if (manual > 0) return manual
    const derived = calcExcessWeightedExp(
      weightedExpenditure.value,
      specialLoanData.value.specialLoanAmount,
    )
    return derived
  })

  /** H2-11 月资本化率（小数）：覆盖优先，否则一般借款年利率/12 */
  const monthlyCapRate11: ComputedRef<number> = computed(() => {
    if (monthlyCapRatePct11.value != null && monthlyCapRatePct11.value > 0) {
      return _toDecimalRate(monthlyCapRatePct11.value)
    }
    return annualRateToMonthly(generalCapRate.value)
  })

  /** H2-11 月度链（扣 SP）：一般借款补充资本化 */
  const monthlyCalcWithBorrow: ComputedRef<{
    rows: MonthlyExpRow[]
    yearCapTotal: number
    bookBorrowCost: number
    yearEndWeighted: number
    hasInput: boolean
  }> = computed(() => {
    const src = monthlyRows11.value
    const opening = src.find(r => r.rowType === 'opening') ?? src[0]
    const months = src.filter(r => r.rowType === 'month')
    const chain = calcMonthlyWeightedExpChain(opening, months, true)
    const rate = monthlyCapRate11.value

    const out: MonthlyExpRow[] = src.map((r) => ({
      ...r,
      expTotal: calcExpTotal(r),
      weightedExp: r.weightedExp,
      capAmount: r.capAmount,
    }))

    if (out[0]) {
      out[0].expTotal = calcExpTotal(opening)
      out[0].weightedExp = chain.openingWeighted
      out[0].capAmount = 0
    }
    months.forEach((_, i) => {
      const row = out[i + 1]
      if (!row) return
      row.expTotal = calcExpTotal(months[i])
      row.weightedExp = chain.monthlyWeighted[i] ?? 0
      row.capAmount = calcCapAmountNoBorrow(row.weightedExp, rate)
    })

    const monthRows = out.filter(r => r.rowType === 'month')
    const yearCapTotal = calcSubtotal(monthRows.map(r => r.capAmount))
    const bookBorrowCost = calcSubtotal(months.map(m => m.borrowCost))
    const yearEndWeighted = monthRows.at(-1)?.weightedExp ?? chain.openingWeighted
    const hasInput = src.some(r =>
      r.prelimDev || r.engCost || r.borrowCost || r.install || r.land
      || r.prepaid || r.decrease || r.specialLoanUsed,
    )
    return { rows: out, yearCapTotal, bookBorrowCost, yearEndWeighted, hasInput }
  })

  /** 一般借款补充：优先月度表合计，否则超额×年利率 */
  const generalLoanSupp: ComputedRef<number> = computed(() => {
    if (monthlyCalcWithBorrow.value.hasInput) {
      return monthlyCalcWithBorrow.value.yearCapTotal
    }
    return calcGeneralLoanSupp(effectiveExcessWeightedExp.value, generalCapRate.value)
  })

  const capAmountWithBorrow: ComputedRef<number> = computed(() =>
    calcTotalCapWithBorrow(specialLoanCap.value, generalLoanSupp.value),
  )

  const totalCapAmount: ComputedRef<number> = computed(() =>
    branch.value === 'noBorrow' ? capAmountNoBorrow.value : capAmountWithBorrow.value,
  )

  /** H2-11 账面比对金额 */
  const bookCapForCompare11: ComputedRef<number> = computed(() => {
    if (clientCapAmount11.value) return clientCapAmount11.value
    if (monthlyCalcWithBorrow.value.bookBorrowCost) {
      return monthlyCalcWithBorrow.value.bookBorrowCost + specialLoanData.value.specialInterest
        - specialLoanData.value.idleIncome
    }
    return clientCapAmount.value
  })

  /** 差异率（分母为0 → null，避免 #DIV/0!） */
  const capDiffRate: ComputedRef<number | null> = computed(() =>
    calcCapDiffRate(
      branch.value === 'noBorrow'
        ? capDifference.value
        : capAmountWithBorrow.value - bookCapForCompare11.value,
      branch.value === 'noBorrow' ? totalCapAmount.value : capAmountWithBorrow.value,
    ),
  )

  const totalInterestWithBorrow: ComputedRef<number> = computed(() =>
    specialLoanData.value.specialInterest + calcSubtotal(loansWithBorrow.value.map(l => l.actualInterest || l.interest)),
  )

  const totalExpenseAmount: ComputedRef<number> = computed(() =>
    totalInterestWithBorrow.value - capAmountWithBorrow.value,
  )

  const crossValidation: ComputedRef<{ diff: number; isMatch: boolean }> = computed(() => {
    const diff = bookCapForCompare.value - totalCapAmount.value
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  /** 建议调整分录文案（测算−账面；负差=账面多计→冲回） */
  const suggestedAje: ComputedRef<{ needed: boolean; amount: number; text: string }> = computed(() => {
    const diff = capDifference.value
    const amount = Math.abs(diff)
    if (amount < 0.01) {
      return { needed: false, amount: 0, text: '测算与账面一致，无需调整。' }
    }
    if (diff < 0) {
      return {
        needed: true,
        amount,
        text: `借：财务费用—利息支出 ${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}\n贷：在建工程—期间费用—贷款利息 ${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
      }
    }
    return {
      needed: true,
      amount,
      text: `借：在建工程—期间费用—贷款利息 ${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}\n贷：财务费用—利息支出 ${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
    }
  })

  // ─── Actions ───────────────────────────────────────────────────────────────

  function setBranch(b: InterestCapBranch): void {
    if (options.isReadonly.value) return
    const prev = branch.value
    branch.value = b
    options.onSave?.(BRANCH_KEY, b)
    // 互斥：切换分支时清空非活跃侧 cap-result，避免 CrossSheet 串支
    if (prev !== b) {
      options.onSave?.(inactiveInterestCapResultKey(b), null)
    }
  }

  function addLoanNoBorrow(): void {
    if (options.isReadonly.value) return
    const loan: LoanItem = {
      rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      lender: '', principal: 0, rate: 0, days: TOTAL_DAYS, periodDays: TOTAL_DAYS,
      actualInterest: 0, interest: 0, weightedPrincipal: 0,
      startDate: '', endDate: '', remark: '',
    }
    loansNoBorrow.value.push(loan)
    _persistLoans10()
  }

  function removeLoanNoBorrow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = loansNoBorrow.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      loansNoBorrow.value.splice(idx, 1)
      _persistLoans10()
    }
  }

  /**
   * 从 L1 短期借款（L1-5 利息测算）带入一般借款明细。
   * 短期借款本身即一般借款，映射进 H2-10 一般借款表口径正确；专门借款判断由 H2-11 承担。
   * 账面利息优先取 L1 账载利息，其次测算利息；利率归一化为百分数。
   * fillEmpty：仅当一般借款表为空时带入（避免覆盖手工录入）；overwrite 强制替换。
   */
  async function pullGeneralLoansFromL1(
    projectId: string,
    mode: 'fillEmpty' | 'overwrite' = 'fillEmpty',
  ): Promise<{ ok: boolean; added: number; total: number; message: string }> {
    if (options.isReadonly.value) return { ok: false, added: 0, total: 0, message: '只读模式' }
    if (mode === 'fillEmpty' && loansNoBorrow.value.length > 0) {
      return { ok: false, added: 0, total: 0, message: '一般借款表已有录入，未覆盖（如需重置请先清空后再带入）' }
    }
    l1Pulling.value = true
    try {
      const result = await pullL1LoansForH2(projectId)
      if (result.status !== 'ok') {
        return { ok: false, added: 0, total: result.principalTotal, message: result.message }
      }
      const mapped: LoanItem[] = result.rows.map((r) => {
        const loan: LoanItem = {
          rowId: `row-l1-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
          lender: r.bank || r.contractNo || '短期借款',
          principal: r.principal,
          rate: normalizeL1RateToPercent(r.rate),
          days: r.days || TOTAL_DAYS,
          periodDays: TOTAL_DAYS,
          actualInterest: r.bookedInterest || r.calculatedInterest || 0,
          interest: 0,
          weightedPrincipal: 0,
          startDate: r.loanStart || '',
          endDate: r.loanEnd || '',
          remark: `来源:L1${r.contractNo ? ' ' + r.contractNo : ''}`,
        }
        _recalcLoan(loan)
        return loan
      })
      loansNoBorrow.value = mapped
      _persistLoans10()
      return {
        ok: true,
        added: mapped.length,
        total: result.principalTotal,
        message: `已从 L1 带入 ${mapped.length} 笔一般借款（本金合计 ${result.principalTotal.toLocaleString('zh-CN')}），请核对利率与账面利息口径`,
      }
    } catch (e: any) {
      return { ok: false, added: 0, total: 0, message: `带入失败：${e?.message || 'L1 底稿不可用'}` }
    } finally {
      l1Pulling.value = false
    }
  }

  function updateLoanNoBorrow(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const loan = loansNoBorrow.value.find(r => r.rowId === rowId)
    if (!loan) return
    const numFields = ['principal', 'rate', 'days', 'periodDays', 'actualInterest']
    if (numFields.includes(field)) {
      ;(loan as any)[field] = Number(value) || 0
    } else {
      ;(loan as any)[field] = String(value ?? '')
    }
    if (field === 'startDate' || field === 'endDate') {
      const d = _daysBetween(loan.startDate, loan.endDate)
      if (d > 0) loan.days = d
    }
    if (field === 'actualInterest') {
      loan.weightedPrincipal = calcWeightedPrincipal(
        loan.principal, loan.days || 0, loan.periodDays || TOTAL_DAYS,
      )
      loan.interest = loan.actualInterest
    } else {
      // 结构性字段变更：重算加权本金；账面利息若为0则回填匡算值
      const keepActual = loan.actualInterest
      const computed = loan.principal * _toDecimalRate(loan.rate) * (loan.days || 0) / TOTAL_DAYS
      loan.weightedPrincipal = calcWeightedPrincipal(
        loan.principal, loan.days || 0, loan.periodDays || TOTAL_DAYS,
      )
      if (!keepActual) {
        loan.actualInterest = computed
      }
      loan.interest = loan.actualInterest || computed
    }
    _persistLoans10()
  }

  function addExpenditure(): void {
    if (options.isReadonly.value) return
    expenditures.value.push({
      rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      month: '', amount: 0, days: 0, weightedAmount: 0,
    })
    _persistExpenditures()
  }

  function removeExpenditure(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = expenditures.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      expenditures.value.splice(idx, 1)
      _persistExpenditures()
    }
  }

  function updateExpenditure(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const exp = expenditures.value.find(r => r.rowId === rowId)
    if (!exp) return
    if (field === 'amount' || field === 'days') {
      ;(exp as any)[field] = Number(value) || 0
    } else {
      ;(exp as any)[field] = String(value ?? '')
    }
    _recalcExpenditure(exp)
    _persistExpenditures()
  }

  function updateMonthlyRow(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = monthlyRows.value.find(r => r.rowId === rowId)
    if (!row || row.rowType === 'total' || row.rowType === 'transfer' || row.rowType === 'ending') return
    const numFields = ['prelimDev', 'engCost', 'borrowCost', 'install', 'land', 'decrease', 'prepaid', 'specialLoanUsed']
    if (numFields.includes(field)) {
      ;(row as any)[field] = Number(value) || 0
    } else if (field === 'remark') {
      row.remark = String(value ?? '')
    }
    _persistMonthly()
  }

  function updateMonthlyRow11(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = monthlyRows11.value.find(r => r.rowId === rowId)
    if (!row || row.rowType === 'total' || row.rowType === 'transfer' || row.rowType === 'ending') return
    const numFields = ['prelimDev', 'engCost', 'borrowCost', 'install', 'land', 'decrease', 'prepaid', 'specialLoanUsed']
    if (numFields.includes(field)) {
      ;(row as any)[field] = Number(value) || 0
    } else if (field === 'remark') {
      row.remark = String(value ?? '')
    }
    _persistMonthly11()
  }

  function setMonthlyCapRatePct(v: number | null): void {
    if (options.isReadonly.value) return
    monthlyCapRatePct.value = v
    options.onSave?.(MONTHLY_RATE_KEY_10, v == null ? '' : String(v))
  }

  function setMonthlyCapRatePct11(v: number | null): void {
    if (options.isReadonly.value) return
    monthlyCapRatePct11.value = v
    options.onSave?.(MONTHLY_RATE_KEY_11, v == null ? '' : String(v))
  }

  function setClientCapAmount(v: number): void {
    if (options.isReadonly.value) return
    clientCapAmount.value = Number(v) || 0
    options.onSave?.(CLIENT_CAP_KEY_10, String(clientCapAmount.value))
  }

  function setClientCapAmount11(v: number): void {
    if (options.isReadonly.value) return
    clientCapAmount11.value = Number(v) || 0
    options.onSave?.(CLIENT_CAP_KEY_11, String(clientCapAmount11.value))
  }

  function addLoanWithBorrow(): void {
    if (options.isReadonly.value) return
    loansWithBorrow.value.push({
      rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      lender: '', principal: 0, rate: 0, days: TOTAL_DAYS, periodDays: TOTAL_DAYS,
      actualInterest: 0, interest: 0, weightedPrincipal: 0,
      startDate: '', endDate: '', remark: '',
    })
    _persistLoans11()
  }

  function removeLoanWithBorrow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = loansWithBorrow.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      loansWithBorrow.value.splice(idx, 1)
      _persistLoans11()
    }
  }

  function updateLoanWithBorrow(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const loan = loansWithBorrow.value.find(r => r.rowId === rowId)
    if (!loan) return
    const numFields = ['principal', 'rate', 'days', 'periodDays', 'actualInterest']
    if (numFields.includes(field)) {
      ;(loan as any)[field] = Number(value) || 0
    } else {
      ;(loan as any)[field] = String(value ?? '')
    }
    if (field === 'startDate' || field === 'endDate') {
      const d = _daysBetween(loan.startDate, loan.endDate)
      if (d > 0) loan.days = d
    }
    loan.actualInterest = field === 'actualInterest' ? (Number(value) || 0) : 0
    _recalcLoan(loan)
    if (field === 'actualInterest') {
      loan.actualInterest = Number(value) || 0
      loan.interest = loan.actualInterest
    }
    _persistLoans11()
  }

  function updateSpecialLoanData(field: keyof SpecialLoanData, value: number): void {
    if (options.isReadonly.value) return
    specialLoanData.value[field] = Number(value) || 0
    options.onSave?.(SPECIAL_KEY_11, specialLoanData.value)
  }

  /** 将 H2-10 一般借款明细带入 H2-11 补充段 */
  function importGeneralLoansFromH210(): number {
    if (options.isReadonly.value) return 0
    if (!loansNoBorrow.value.length) return 0
    loansWithBorrow.value = loansNoBorrow.value.map(l => ({
      ...l,
      rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}-${l.rowId}`,
    }))
    _persistLoans11()
    return loansWithBorrow.value.length
  }

  /** 将 H2-10 月度支出带入 H2-11（SP 列置 0，可再填专门借款占用） */
  function importMonthlyFromH210(): number {
    if (options.isReadonly.value) return 0
    const src = monthlyRows.value
    if (!src.length) return 0
    monthlyRows11.value = src.map(r => ({
      ...r,
      rowId: r.rowId,
      specialLoanUsed: 0,
      expTotal: 0,
      weightedExp: 0,
      capAmount: 0,
    }))
    _persistMonthly11()
    return monthlyRows11.value.length
  }

  function publishInterestCap(): void {
    if (!options.onPublishEvent) return
    const result: InterestCapResult = {
      totalCap: totalCapAmount.value,
      byProject: {},
      capRate: branch.value === 'noBorrow' ? effectiveAnnualCapRate.value : generalCapRate.value,
      branch: branch.value,
    }
    const resultKey = branch.value === 'noBorrow' ? RESULT_KEY_10 : RESULT_KEY_11
    options.onSave?.(BRANCH_KEY, branch.value)
    options.onSave?.(resultKey, result)
    options.onSave?.(inactiveInterestCapResultKey(branch.value), null)

    options.onPublishEvent('h2:interest-capitalized', {
      capAmount: totalCapAmount.value,
      totalInterest: branch.value === 'noBorrow'
        ? totalInterestNoBorrow.value
        : totalInterestWithBorrow.value,
      capRate: result.capRate,
      branch: branch.value,
    })
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options.onSave?.(CONCLUSION_KEY, conclusion)
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistLoans10(): void {
    options.onSave?.(LOANS_KEY_10, loansNoBorrow.value.map(l => ({
      rowId: l.rowId, lender: l.lender, principal: l.principal,
      rate: l.rate, days: l.days, periodDays: l.periodDays,
      actualInterest: l.actualInterest,
      startDate: l.startDate, endDate: l.endDate, remark: l.remark,
    })))
  }

  function _persistExpenditures(): void {
    options.onSave?.(EXPENDITURES_KEY_10, expenditures.value.map(e => ({
      rowId: e.rowId, month: e.month, amount: e.amount, days: e.days,
    })))
  }

  function _persistMonthly(): void {
    options.onSave?.(MONTHLY_KEY_10, monthlyRows.value.map(r => ({
      rowId: r.rowId, rowType: r.rowType, monthLabel: r.monthLabel,
      prelimDev: r.prelimDev, engCost: r.engCost, borrowCost: r.borrowCost,
      install: r.install, land: r.land, decrease: r.decrease, prepaid: r.prepaid,
      specialLoanUsed: r.specialLoanUsed ?? 0,
      remark: r.remark,
    })))
  }

  function _persistMonthly11(): void {
    options.onSave?.(MONTHLY_KEY_11, monthlyRows11.value.map(r => ({
      rowId: r.rowId, rowType: r.rowType, monthLabel: r.monthLabel,
      prelimDev: r.prelimDev, engCost: r.engCost, borrowCost: r.borrowCost,
      install: r.install, land: r.land, decrease: r.decrease, prepaid: r.prepaid,
      specialLoanUsed: r.specialLoanUsed ?? 0,
      remark: r.remark,
    })))
  }

  function _persistLoans11(): void {
    options.onSave?.(LOANS_KEY_11, loansWithBorrow.value.map(l => ({
      rowId: l.rowId, lender: l.lender, principal: l.principal,
      rate: l.rate, days: l.days, periodDays: l.periodDays,
      actualInterest: l.actualInterest,
      startDate: l.startDate, endDate: l.endDate, remark: l.remark,
    })))
  }

  return {
    branch,
    loansNoBorrow, expenditures, monthlyRows,
    monthlyCapRatePct, clientCapAmount,
    loansWithBorrow, specialLoanData,
    monthlyRows11, monthlyCapRatePct11, clientCapAmount11,
    auditNote, auditConclusion,
    // H2-10
    annualCapRate, weightedCapRate, effectiveAnnualCapRate, monthlyCapRate,
    monthlyCalc, weightedExpenditure, capAmountNoBorrow,
    totalInterestNoBorrow, expenseAmount, bookCapForCompare,
    exceedsInterestCeiling, suggestedAje,
    // H2-11
    specialLoanCap, generalCapRate, generalLoanSupp, capAmountWithBorrow,
    effectiveExcessWeightedExp, capDiffRate,
    monthlyCapRate11, monthlyCalcWithBorrow, bookCapForCompare11,
    totalCapAmount, capDifference, crossValidation,
    totalInterestWithBorrow, totalExpenseAmount,
    // Actions
    setBranch,
    l1Pulling,
    pullGeneralLoansFromL1,
    addLoanNoBorrow, removeLoanNoBorrow, updateLoanNoBorrow,
    addExpenditure, removeExpenditure, updateExpenditure,
    updateMonthlyRow, setMonthlyCapRatePct, setClientCapAmount,
    updateMonthlyRow11, setMonthlyCapRatePct11, setClientCapAmount11,
    addLoanWithBorrow, removeLoanWithBorrow, updateLoanWithBorrow,
    updateSpecialLoanData, importGeneralLoansFromH210, importMonthlyFromH210,
    publishInterestCap,
    saveNote, saveConclusion, initFromAllResponses,
  }
}

export default useH2InterestCap
