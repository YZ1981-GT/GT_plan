/**
 * useH2InterestCap — H2-10/11 利息资本化共用 composable
 *
 * interestCapBranch状态(noBorrow/withBorrow) + 2分支共用数据
 * 调用InterestCapEngine计算 + 差异对比 + EventBus联动L
 * 从H2-2取数(各工程利息列) + 交叉验证
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.12
 * Requirements: 10.1-10.10
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcWeightedCapRate,
  calcWeightedExpenditure,
  calcCapAmountNoBorrow,
  calcSpecialLoanCap,
  calcGeneralLoanSupp,
  calcTotalCapWithBorrow,
} from './useH2InterestCapEngine'
import { calcSubtotal } from './useH2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type InterestCapBranch = 'noBorrow' | 'withBorrow'

export interface LoanItem {
  rowId: string
  /** 借款人/银行 */
  lender: string
  /** 借款本金 */
  principal: number
  /** 年利率 */
  rate: number
  /** 借款期限(天) */
  days: number
  /** 利息金额 (公式列: principal × rate × days / 365) */
  interest: number
  /** 起始日期 */
  startDate: string
  /** 到期日期 */
  endDate: string
  /** 备注 */
  remark: string
}

export interface ExpenditureItem {
  rowId: string
  /** 支出月份 */
  month: string
  /** 支出金额 */
  amount: number
  /** 占用天数 */
  days: number
  /** 加权金额 (公式列: amount × days) */
  weightedAmount: number
}

export interface SpecialLoanData {
  /** 专门借款利息合计 */
  specialInterest: number
  /** 闲置投资收益 */
  idleIncome: number
  /** 专门借款金额 */
  specialLoanAmount: number
  /** 超出专门借款部分的加权支出 */
  excessWeightedExp: number
}

export interface InterestCapResult {
  totalCap: number
  byProject: Record<string, number>
  capRate: number
  branch: InterestCapBranch
}

// ─── Constants ───────────────────────────────────────────────────────────────

const BRANCH_KEY = 'H2-interest-cap-branch'
const LOANS_KEY_10 = 'H2-10-loans'
const EXPENDITURES_KEY_10 = 'H2-10-expenditures'
const LOANS_KEY_11 = 'H2-11-loans'
const SPECIAL_KEY_11 = 'H2-11-special-data'
const RESULT_KEY_10 = 'H2-10-cap-result'
const RESULT_KEY_11 = 'H2-11-cap-result'
const NOTE_KEY = 'H2-10-audit-note'
const CONCLUSION_KEY = 'H2-10-audit-conclusion'
const TOTAL_DAYS = 365

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2InterestCap(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  /** 从useH2CrossSheet.interestCapForDetail取数 */
  interestCapForDetail?: ComputedRef<{ totalCap: number; byProject: Record<string, number> }>
  onSave?: (itemId: string, value: any) => void
  onPublishEvent?: (event: string, payload: any) => void
}) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const branch = ref<InterestCapBranch>('noBorrow')

  // 无专门借款数据
  const loansNoBorrow = ref<LoanItem[]>([])
  const expenditures = ref<ExpenditureItem[]>([])

  // 有专门借款数据
  const loansWithBorrow = ref<LoanItem[]>([])
  const specialLoanData = ref<SpecialLoanData>({
    specialInterest: 0,
    idleIncome: 0,
    specialLoanAmount: 0,
    excessWeightedExp: 0,
  })

  const auditNote = ref('')
  const auditConclusion = ref('')

  /** 被审计单位账面资本化金额（用于差异对比） */
  const clientCapAmount = ref(0)

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _recalcLoan(loan: LoanItem): void {
    loan.interest = loan.principal * loan.rate * loan.days / 365
  }

  function _recalcExpenditure(exp: ExpenditureItem): void {
    exp.weightedAmount = exp.amount * exp.days
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  function initFromAllResponses(): void {
    const branchVal = _getString(BRANCH_KEY)
    branch.value = branchVal === 'withBorrow' ? 'withBorrow' : 'noBorrow'

    // 无专门借款: 借款明细
    const loans10 = _getJson(LOANS_KEY_10)
    if (Array.isArray(loans10)) {
      loansNoBorrow.value = loans10.map((r: any) => {
        const loan: LoanItem = {
          rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
          lender: r.lender ?? '',
          principal: Number(r.principal) || 0,
          rate: Number(r.rate) || 0,
          days: Number(r.days) || 0,
          interest: 0,
          startDate: r.startDate ?? '',
          endDate: r.endDate ?? '',
          remark: r.remark ?? '',
        }
        _recalcLoan(loan)
        return loan
      })
    }

    // 无专门借款: 支出明细
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

    // 有专门借款: 借款明细
    const loans11 = _getJson(LOANS_KEY_11)
    if (Array.isArray(loans11)) {
      loansWithBorrow.value = loans11.map((r: any) => {
        const loan: LoanItem = {
          rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
          lender: r.lender ?? '',
          principal: Number(r.principal) || 0,
          rate: Number(r.rate) || 0,
          days: Number(r.days) || 0,
          interest: 0,
          startDate: r.startDate ?? '',
          endDate: r.endDate ?? '',
          remark: r.remark ?? '',
        }
        _recalcLoan(loan)
        return loan
      })
    }

    // 有专门借款: 专门借款数据
    const special = _getJson(SPECIAL_KEY_11)
    if (special && typeof special === 'object') {
      specialLoanData.value = {
        specialInterest: Number(special.specialInterest) || 0,
        idleIncome: Number(special.idleIncome) || 0,
        specialLoanAmount: Number(special.specialLoanAmount) || 0,
        excessWeightedExp: Number(special.excessWeightedExp) || 0,
      }
    }

    // 被审计单位账面金额（从H2-2利息列合计取）
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

    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed: 无专门借款分支计算 ──────────────────────────────────────────

  /** 加权资本化率 */
  const weightedCapRate: ComputedRef<number> = computed(() =>
    calcWeightedCapRate(loansNoBorrow.value.map(l => ({
      principal: l.principal, rate: l.rate, days: l.days,
    }))),
  )

  /** 累计支出加权平均数 */
  const weightedExpenditure: ComputedRef<number> = computed(() =>
    calcWeightedExpenditure(
      expenditures.value.map(e => ({ amount: e.amount, days: e.days })),
      TOTAL_DAYS,
    ),
  )

  /** 无专门借款资本化金额 */
  const capAmountNoBorrow: ComputedRef<number> = computed(() =>
    calcCapAmountNoBorrow(weightedExpenditure.value, weightedCapRate.value),
  )

  // ─── Computed: 有专门借款分支计算 ──────────────────────────────────────────

  /** 专门借款资本化 */
  const specialLoanCap: ComputedRef<number> = computed(() =>
    calcSpecialLoanCap(specialLoanData.value.specialInterest, specialLoanData.value.idleIncome),
  )

  /** 一般借款加权资本化率 */
  const generalCapRate: ComputedRef<number> = computed(() =>
    calcWeightedCapRate(loansWithBorrow.value.map(l => ({
      principal: l.principal, rate: l.rate, days: l.days,
    }))),
  )

  /** 一般借款补充资本化 */
  const generalLoanSupp: ComputedRef<number> = computed(() =>
    calcGeneralLoanSupp(specialLoanData.value.excessWeightedExp, generalCapRate.value),
  )

  /** 有专门借款合计 */
  const capAmountWithBorrow: ComputedRef<number> = computed(() =>
    calcTotalCapWithBorrow(specialLoanCap.value, generalLoanSupp.value),
  )

  // ─── Computed: 当前分支结果 ────────────────────────────────────────────────

  /** 应予资本化金额（当前分支） */
  const totalCapAmount: ComputedRef<number> = computed(() =>
    branch.value === 'noBorrow' ? capAmountNoBorrow.value : capAmountWithBorrow.value,
  )

  /** 差异（审计测算 - 被审计单位账面） */
  const capDifference: ComputedRef<number> = computed(() =>
    totalCapAmount.value - clientCapAmount.value,
  )

  // ─── Computed: 利息费用化金额（利息总额 - 资本化金额） ──────────────────────

  /** 无专门借款分支：一般借款利息总额 */
  const totalInterestNoBorrow: ComputedRef<number> = computed(() =>
    calcSubtotal(loansNoBorrow.value.map(l => l.interest)),
  )

  /** 无专门借款分支：利息费用化金额 = 利息总额 - 资本化金额 */
  const expenseAmount: ComputedRef<number> = computed(() =>
    totalInterestNoBorrow.value - capAmountNoBorrow.value,
  )

  /** 有专门借款分支：利息总额 = 专门借款利息 + 一般借款利息合计 */
  const totalInterestWithBorrow: ComputedRef<number> = computed(() =>
    specialLoanData.value.specialInterest + calcSubtotal(loansWithBorrow.value.map(l => l.interest)),
  )

  /** 有专门借款分支：利息费用化金额 = 利息总额 - 资本化合计 */
  const totalExpenseAmount: ComputedRef<number> = computed(() =>
    totalInterestWithBorrow.value - capAmountWithBorrow.value,
  )

  /** 交叉验证H2-2（各工程利息列之和 vs 资本化金额） */
  const crossValidation: ComputedRef<{ diff: number; isMatch: boolean }> = computed(() => {
    const diff = clientCapAmount.value - totalCapAmount.value
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ─── Actions ───────────────────────────────────────────────────────────────

  function setBranch(b: InterestCapBranch): void {
    if (options.isReadonly.value) return
    branch.value = b
    options.onSave?.(BRANCH_KEY, b)
  }

  // — 无专门借款: 借款操作 —
  function addLoanNoBorrow(): void {
    if (options.isReadonly.value) return
    const loan: LoanItem = {
      rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      lender: '', principal: 0, rate: 0, days: 365, interest: 0,
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

  function updateLoanNoBorrow(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const loan = loansNoBorrow.value.find(r => r.rowId === rowId)
    if (!loan) return
    const numFields = ['principal', 'rate', 'days']
    if (numFields.includes(field)) {
      ;(loan as any)[field] = Number(value) || 0
    } else {
      ;(loan as any)[field] = String(value ?? '')
    }
    _recalcLoan(loan)
    _persistLoans10()
  }

  // — 无专门借款: 支出操作 —
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

  // — 有专门借款: 借款操作 —
  function addLoanWithBorrow(): void {
    if (options.isReadonly.value) return
    loansWithBorrow.value.push({
      rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      lender: '', principal: 0, rate: 0, days: 365, interest: 0,
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
    const numFields = ['principal', 'rate', 'days']
    if (numFields.includes(field)) {
      ;(loan as any)[field] = Number(value) || 0
    } else {
      ;(loan as any)[field] = String(value ?? '')
    }
    _recalcLoan(loan)
    _persistLoans11()
  }

  function updateSpecialLoanData(field: keyof SpecialLoanData, value: number): void {
    if (options.isReadonly.value) return
    specialLoanData.value[field] = Number(value) || 0
    options.onSave?.(SPECIAL_KEY_11, specialLoanData.value)
  }

  // — 联动L(财务费用) —
  function publishInterestCap(): void {
    if (!options.onPublishEvent) return
    const result: InterestCapResult = {
      totalCap: totalCapAmount.value,
      byProject: {},
      capRate: branch.value === 'noBorrow' ? weightedCapRate.value : generalCapRate.value,
      branch: branch.value,
    }
    // 保存结果
    const resultKey = branch.value === 'noBorrow' ? RESULT_KEY_10 : RESULT_KEY_11
    options.onSave?.(resultKey, result)

    options.onPublishEvent('h2:interest-capitalized', {
      capAmount: totalCapAmount.value,
      totalInterest: calcSubtotal(
        (branch.value === 'noBorrow' ? loansNoBorrow : loansWithBorrow).value.map(l => l.interest),
      ),
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
      rate: l.rate, days: l.days, startDate: l.startDate,
      endDate: l.endDate, remark: l.remark,
    })))
  }

  function _persistExpenditures(): void {
    options.onSave?.(EXPENDITURES_KEY_10, expenditures.value.map(e => ({
      rowId: e.rowId, month: e.month, amount: e.amount, days: e.days,
    })))
  }

  function _persistLoans11(): void {
    options.onSave?.(LOANS_KEY_11, loansWithBorrow.value.map(l => ({
      rowId: l.rowId, lender: l.lender, principal: l.principal,
      rate: l.rate, days: l.days, startDate: l.startDate,
      endDate: l.endDate, remark: l.remark,
    })))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    branch,
    loansNoBorrow, expenditures,
    loansWithBorrow, specialLoanData,
    clientCapAmount, auditNote, auditConclusion,
    // Computed: 无专门借款
    weightedCapRate, weightedExpenditure, capAmountNoBorrow,
    // Computed: 有专门借款
    specialLoanCap, generalCapRate, generalLoanSupp, capAmountWithBorrow,
    // Computed: 通用
    totalCapAmount, capDifference, crossValidation,
    totalInterestNoBorrow, expenseAmount,
    totalInterestWithBorrow, totalExpenseAmount,
    // Actions
    setBranch,
    addLoanNoBorrow, removeLoanNoBorrow, updateLoanNoBorrow,
    addExpenditure, removeExpenditure, updateExpenditure,
    addLoanWithBorrow, removeLoanWithBorrow, updateLoanWithBorrow,
    updateSpecialLoanData,
    publishInterestCap,
    saveNote, saveConclusion, initFromAllResponses,
  }
}

export default useH2InterestCap
