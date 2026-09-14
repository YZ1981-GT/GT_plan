/**
 * useH8Measurement — H8-6 初始及后续计量 composable（按年/按月共用逻辑）
 *
 * H8-6双分支：
 * - 按年计量（59行13列9公式）→ H8TabMeasurementAnnual.vue
 * - 按月计量（361行16列）→ H8TabMeasurementMonthly.vue
 *
 * 共用逻辑：
 * - CAS21初始计量公式：使用权资产 = H9初始 + 直接费用 - 激励
 * - 分支切换 state
 * - 计量参数管理（折现率、租赁期、租金）
 * - 从 H8-5 带入租赁期 / 与 H8-5 差异提示
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/
 * Task: 3.4
 * Requirements: 5.1-5.6
 */
import { ref, computed, watch, type Ref } from 'vue'
import { calcInitialMeasurement } from './useH8CAS21Engine'
import {
  generateSchedule,
  validateSchedule,
  type AmortizationRow,
} from './useH9AmortizationEngine'
import {
  mergeLeaseTermIntoH86Params,
  listLeaseTermsFromH85Raw,
  pickH85TermOption,
  type H85TermOption,
} from './useH8LeaseTerm'

export type { H85TermOption, AmortizationRow }
export { listLeaseTermsFromH85Raw, pickH85TermOption }

// ─── Types ───────────────────────────────────────────────────────────────────

/** H8-6计量分支 */
export type H8MeasurementBranch = '按年计量' | '按月计量'

/** 计量参数 */
export interface H8MeasurementParams {
  /** 租赁负债初始确认（H9） */
  leaseLiabilityInitial: number
  /** 初始直接费用 */
  directCost: number
  /** 租赁激励 */
  incentive: number
  /** 折现率(%) */
  discountRate: number
  /** 租赁期（月） */
  leaseTermMonths: number
  /** 每期租金 */
  rentalPerPeriod: number
  /** 付款方式：期初/期末 */
  paymentTiming: '期初' | '期末'
  /** 租赁期来源合同号（自 H8-5 带入时写入） */
  leaseTermSourceContract?: string
  /** 租赁期同步来源标记 */
  leaseTermSyncedFrom?: string
}

export interface H86PullFromH85Result {
  ok: boolean
  reason?: string
  contractNo?: string
  months?: number
  previousMonths?: number
  shortTermHint?: boolean
}

/** H8-6 摊销表生成参数（与分支无关的纯函数输入） */
export interface H86AmortInput {
  leaseLiabilityInitial: number
  discountRate: number
  leaseTermMonths: number
  /** 每期租金：按月分支=月租金；按年分支亦存月租金（表单统一） */
  rentalPerPeriod: number
  branch: H8MeasurementBranch
}

/**
 * 按 CAS21 实际利率法生成 H8-6 负债摊销表（复用 H9 generateSchedule）。
 * - 按年：期数=ceil(月/12)，年付款=月租金×12，年利率
 * - 按月：期数=月数，月付款=月租金，月利率=年利率/12
 */
export function buildH86AmortSchedule(input: H86AmortInput): {
  rows: AmortizationRow[]
  periods: number
  periodRate: number
  periodPayment: number
  validation: { isValid: boolean; tailDiff: number }
  totalInterest: number
  totalPayment: number
} {
  const initial = Number(input.leaseLiabilityInitial) || 0
  const months = Math.max(0, Math.floor(Number(input.leaseTermMonths) || 0))
  const monthlyRent = Number(input.rentalPerPeriod) || 0
  const annualRate = (Number(input.discountRate) || 0) / 100

  let periods = 0
  let periodRate = 0
  let periodPayment = 0
  if (input.branch === '按月计量') {
    periods = months
    periodRate = annualRate / 12
    periodPayment = monthlyRent
  } else {
    periods = months > 0 ? Math.ceil(months / 12) : 0
    periodRate = annualRate
    periodPayment = monthlyRent * 12
  }

  if (initial <= 0 || periods <= 0 || periodPayment < 0) {
    return {
      rows: [],
      periods,
      periodRate,
      periodPayment,
      validation: { isValid: true, tailDiff: 0 },
      totalInterest: 0,
      totalPayment: 0,
    }
  }

  const rows = generateSchedule(initial, periodPayment, periodRate, periods)
  const validation = validateSchedule(rows)
  const totalInterest = rows.reduce((s, r) => s + r.interest, 0)
  const totalPayment = rows.reduce((s, r) => s + r.payment, 0)
  return { rows, periods, periodRate, periodPayment, validation, totalInterest, totalPayment }
}

// ─── Constants ───────────────────────────────────────────────────────────────

const BRANCH_KEY = 'H8-6-branch'
export const H86_PARAMS_KEY = 'H8-6-params'
const INITIAL_MEASUREMENT_KEY = 'H8-6-initial-measurement'
const H85_RECORDS_KEY = 'H8-5-records'

function emptyParams(): H8MeasurementParams {
  return {
    leaseLiabilityInitial: 0,
    directCost: 0,
    incentive: 0,
    discountRate: 0,
    leaseTermMonths: 0,
    rentalPerPeriod: 0,
    paymentTiming: '期末',
    leaseTermSourceContract: '',
    leaseTermSyncedFrom: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8Measurement(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  const branch = ref<H8MeasurementBranch>('按年计量')
  const measurementParams = ref<H8MeasurementParams>(emptyParams())

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function load(): void {
    const branchVal = _getString(BRANCH_KEY)
    if (branchVal === '按月计量') {
      branch.value = '按月计量'
    } else {
      branch.value = '按年计量'
    }

    const paramsData = _getJson(H86_PARAMS_KEY)
    if (paramsData && typeof paramsData === 'object') {
      measurementParams.value = {
        ...emptyParams(),
        leaseLiabilityInitial: Number(paramsData.leaseLiabilityInitial) || 0,
        directCost: Number(paramsData.directCost) || 0,
        incentive: Number(paramsData.incentive) || 0,
        discountRate: Number(paramsData.discountRate) || 0,
        leaseTermMonths: Number(paramsData.leaseTermMonths) || 0,
        rentalPerPeriod: Number(paramsData.rentalPerPeriod) || 0,
        paymentTiming: paramsData.paymentTiming === '期初' ? '期初' : '期末',
        leaseTermSourceContract: String(paramsData.leaseTermSourceContract ?? ''),
        leaseTermSyncedFrom: String(paramsData.leaseTermSyncedFrom ?? ''),
      }
    } else {
      measurementParams.value = emptyParams()
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  const initialMeasurement = computed(() =>
    calcInitialMeasurement(
      measurementParams.value.leaseLiabilityInitial,
      measurementParams.value.directCost,
      measurementParams.value.incentive,
    ),
  )

  const formulaText = computed(() =>
    `使用权资产 = 租赁负债初始确认(${measurementParams.value.leaseLiabilityInitial}) + 初始直接费用(${measurementParams.value.directCost}) - 租赁激励(${measurementParams.value.incentive}) = ${initialMeasurement.value}`,
  )

  const annualRental = computed(() => {
    const p = measurementParams.value
    if (p.leaseTermMonths <= 0) return 0
    return p.rentalPerPeriod * 12
  })

  /** HTML 摊销表（按当前分支自动年/月） */
  const amortSchedule = computed(() =>
    buildH86AmortSchedule({
      leaseLiabilityInitial: measurementParams.value.leaseLiabilityInitial,
      discountRate: measurementParams.value.discountRate,
      leaseTermMonths: measurementParams.value.leaseTermMonths,
      rentalPerPeriod: measurementParams.value.rentalPerPeriod,
      branch: branch.value,
    }),
  )

  /** H8-5 可选合同租赁期 */
  const h85TermOptions = computed(() => listLeaseTermsFromH85Raw(_getJson(H85_RECORDS_KEY)))

  /** 与来源合同有效租赁期是否不一致 */
  const h85TermMismatch = computed(() => {
    const src = measurementParams.value.leaseTermSourceContract
    if (!src) return null
    const opt = h85TermOptions.value.find(o => o.contractNo === src)
    if (!opt || opt.months <= 0) return null
    if (opt.months === measurementParams.value.leaseTermMonths) return null
    return {
      contractNo: src,
      h85Months: opt.months,
      h86Months: measurementParams.value.leaseTermMonths,
    }
  })

  function setBranch(b: H8MeasurementBranch): void {
    branch.value = b
    onSave?.(BRANCH_KEY, b)
  }

  function updateParam(field: keyof H8MeasurementParams, value: any): void {
    const numFields: (keyof H8MeasurementParams)[] = [
      'leaseLiabilityInitial', 'directCost', 'incentive',
      'discountRate', 'leaseTermMonths', 'rentalPerPeriod',
    ]
    if (numFields.includes(field)) {
      ;(measurementParams.value as any)[field] = Number(value) || 0
    } else {
      ;(measurementParams.value as any)[field] = String(value ?? '')
    }
    // 手改租赁期时清除同步标记来源（保留合同号便于再对齐）
    if (field === 'leaseTermMonths') {
      measurementParams.value.leaseTermSyncedFrom = ''
    }
    _persist()
  }

  /** 从 H8-5 带入租赁期（可指定合同号；默认取有结论/有月数的一条） */
  function pullLeaseTermFromH85(contractNo?: string): H86PullFromH85Result {
    const options = h85TermOptions.value
    if (!options.length) {
      return { ok: false, reason: 'H8-5 尚无租赁期记录，请先完成租赁期确定' }
    }
    const picked = pickH85TermOption(options, contractNo)
    if (!picked) {
      return {
        ok: false,
        reason: contractNo
          ? `未找到合同 ${contractNo} 的租赁期记录`
          : 'H8-5 记录中没有有效租赁期（月数>0）',
      }
    }
    if (picked.months <= 0) {
      return { ok: false, reason: `合同 ${picked.contractNo} 有效租赁期为 0` }
    }
    if (!onSave) return { ok: false, reason: '无法保存（只读或未挂载 onSave）' }

    const previousMonths = measurementParams.value.leaseTermMonths
    const merged = mergeLeaseTermIntoH86Params(
      measurementParams.value,
      picked.months,
      picked.contractNo,
    )
    measurementParams.value = {
      ...emptyParams(),
      ...merged,
      paymentTiming: merged.paymentTiming === '期初' ? '期初' : '期末',
    } as H8MeasurementParams
    _persist()

    const result: H86PullFromH85Result = {
      ok: true,
      contractNo: picked.contractNo,
      months: picked.months,
      previousMonths,
      shortTermHint: picked.months <= 12,
    }
    try {
      window.dispatchEvent(new CustomEvent('h8:lease-term-synced', {
        detail: { source: 'H8-6-pull', ...result },
      }))
    } catch { /* ignore */ }
    return result
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    onSave(H86_PARAMS_KEY, { ...measurementParams.value })
    onSave(INITIAL_MEASUREMENT_KEY, initialMeasurement.value)
  }

  return {
    branch, measurementParams,
    initialMeasurement, formulaText, annualRental,
    amortSchedule,
    h85TermOptions, h85TermMismatch,
    setBranch, updateParam, pullLeaseTermFromH85, save, load,
  }
}

export default useH8Measurement
