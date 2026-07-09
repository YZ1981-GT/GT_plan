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
 * - OO渲染模式（主要展示，轻编辑）
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/
 * Task: 3.4
 * Requirements: 5.1-5.6
 */
import { ref, computed, watch, type Ref } from 'vue'
import { calcInitialMeasurement } from './useH8CAS21Engine'

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
}

// ─── Constants ───────────────────────────────────────────────────────────────

const BRANCH_KEY = 'H8-6-branch'
const PARAMS_KEY = 'H8-6-params'
const INITIAL_MEASUREMENT_KEY = 'H8-6-initial-measurement'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8Measurement(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const branch = ref<H8MeasurementBranch>('按年计量')
  const measurementParams = ref<H8MeasurementParams>({
    leaseLiabilityInitial: 0,
    directCost: 0,
    incentive: 0,
    discountRate: 0,
    leaseTermMonths: 0,
    rentalPerPeriod: 0,
    paymentTiming: '期末',
  })

  // ─── Helpers ───────────────────────────────────────────────────────────────

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

  // ─── Load ──────────────────────────────────────────────────────────────────

  function load(): void {
    const branchVal = _getString(BRANCH_KEY)
    if (branchVal === '按月计量') {
      branch.value = '按月计量'
    } else {
      branch.value = '按年计量'
    }

    const paramsData = _getJson(PARAMS_KEY)
    if (paramsData && typeof paramsData === 'object') {
      measurementParams.value = {
        leaseLiabilityInitial: Number(paramsData.leaseLiabilityInitial) || 0,
        directCost: Number(paramsData.directCost) || 0,
        incentive: Number(paramsData.incentive) || 0,
        discountRate: Number(paramsData.discountRate) || 0,
        leaseTermMonths: Number(paramsData.leaseTermMonths) || 0,
        rentalPerPeriod: Number(paramsData.rentalPerPeriod) || 0,
        paymentTiming: paramsData.paymentTiming === '期初' ? '期初' : '期末',
      }
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  /** CAS21初始计量值 = H9初始 + 直接费用 - 激励 */
  const initialMeasurement = computed(() =>
    calcInitialMeasurement(
      measurementParams.value.leaseLiabilityInitial,
      measurementParams.value.directCost,
      measurementParams.value.incentive,
    ),
  )

  /** 公式说明文本 */
  const formulaText = computed(() =>
    `使用权资产 = 租赁负债初始确认(${measurementParams.value.leaseLiabilityInitial}) + 初始直接费用(${measurementParams.value.directCost}) - 租赁激励(${measurementParams.value.incentive}) = ${initialMeasurement.value}`,
  )

  /** 年化租金 */
  const annualRental = computed(() => {
    const p = measurementParams.value
    if (p.leaseTermMonths <= 0) return 0
    return p.rentalPerPeriod * 12
  })

  // ─── Actions ───────────────────────────────────────────────────────────────

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
    _persist()
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    onSave(PARAMS_KEY, measurementParams.value)
    onSave(INITIAL_MEASUREMENT_KEY, initialMeasurement.value)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    branch, measurementParams,
    initialMeasurement, formulaText, annualRental,
    setBranch, updateParam, save, load,
  }
}

export default useH8Measurement
