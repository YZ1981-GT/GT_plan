/**
 * useH9Amortization — 摊销表 composable（合同筛选+完整表生成，前端计算视图）
 *
 * H9 摊销表是 H9 的核心计算视图（非物理sheet，纯前端计算）：
 * - 从H9-2合同下拉选择
 * - 使用 useH9AmortizationEngine + useH9PVEngine 生成完整摊销表
 * - 验证最后一期期末余额≈0
 * - 与H9-1审定表本期利息费用交叉验证（本期口径，非全期）
 *
 * Spec: .kiro/specs/h9-lease-liabilities/
 * Task: 3.4
 * Requirements: 4.1-4.8
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { generateSchedule, validateSchedule, type AmortizationRow } from './useH9AmortizationEngine'
import { calcAnnuityPV } from './useH9PVEngine'
import { calcSubtotal } from './useH9FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 合同选项（来自H9-2） */
export interface ContractOption {
  contractNo: string
  lessor: string
  initialBalance: number
  /** 年利率小数（已归一：5.5 → 0.055） */
  ibrRate: number
  leaseTerm: number
  /** 本期偿还（通常为年付款额；月摊销时 /12） */
  annualPayment: number
}

/** 摊销表校验结果 */
export interface ScheduleValidation {
  isValid: boolean
  tailDiff: number
  /** 全期利息合计 */
  totalInterest: number
  /** 本期利息（前 min(12,期数) 期，年报口径） */
  currentPeriodInterest: number
  totalPrincipal: number
  warning: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 新键；兼容读历史 H9-4-selected-contract */
const SELECTED_CONTRACT_KEY = 'H9-amort-selected-contract'
const SELECTED_CONTRACT_KEY_LEGACY = 'H9-4-selected-contract'
const TOTAL_INTEREST_KEY = 'H9-amort-total-interest'
const CURRENT_INTEREST_KEY = 'H9-amort-current-interest'

/** IBR：>1 视为百分数（5.5 → 0.055） */
export function normalizeIbrRate(raw: number): number {
  const n = Number(raw) || 0
  if (n > 1) return n / 100
  return n
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH9Amortization(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  const selectedContractNo = ref('')
  const contracts = ref<ContractOption[]>([])

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
    const h9DetailData = _getJson('H9-2-rows')
    if (Array.isArray(h9DetailData)) {
      contracts.value = h9DetailData.map((r: any) => ({
        contractNo: r.contractNo ?? '',
        lessor: r.lessor ?? '',
        initialBalance: Number(r.beginBalance) || 0,
        ibrRate: normalizeIbrRate(Number(r.ibrRate) || 0),
        leaseTerm: Number(r.leaseTerm) || 0,
        annualPayment: Number(r.repayment) || 0,
      })).filter((c: ContractOption) => c.contractNo)
    } else {
      contracts.value = []
    }
    selectedContractNo.value =
      _getString(SELECTED_CONTRACT_KEY)
      || _getString(SELECTED_CONTRACT_KEY_LEGACY)
      || (contracts.value[0]?.contractNo ?? '')
  }

  watch(allResponses, () => load(), { immediate: true })

  const selectedContract: ComputedRef<ContractOption | null> = computed(() =>
    contracts.value.find(c => c.contractNo === selectedContractNo.value) ?? null,
  )

  const schedule: ComputedRef<AmortizationRow[]> = computed(() => {
    const contract = selectedContract.value
    if (!contract || contract.initialBalance <= 0 || contract.leaseTerm <= 0) {
      return []
    }
    const monthlyRate = contract.ibrRate / 12
    const monthlyPayment = contract.annualPayment / 12
    return generateSchedule(contract.initialBalance, monthlyPayment, monthlyRate, contract.leaseTerm)
  })

  const computedPV: ComputedRef<number> = computed(() => {
    const contract = selectedContract.value
    if (!contract || contract.leaseTerm <= 0) return 0
    const monthlyRate = contract.ibrRate / 12
    const monthlyPayment = contract.annualPayment / 12
    return calcAnnuityPV(monthlyPayment, monthlyRate, contract.leaseTerm)
  })

  const validation: ComputedRef<ScheduleValidation> = computed(() => {
    const s = schedule.value
    if (s.length === 0) {
      return {
        isValid: true, tailDiff: 0, totalInterest: 0,
        currentPeriodInterest: 0, totalPrincipal: 0, warning: '',
      }
    }

    const { isValid, tailDiff } = validateSchedule(s)
    const totalInterest = calcSubtotal(s.map(r => r.interest))
    const totalPrincipal = calcSubtotal(s.map(r => r.principal))
    const periodsInYear = Math.min(12, s.length)
    const currentPeriodInterest = calcSubtotal(s.slice(0, periodsInYear).map(r => r.interest))
    const warning = isValid ? '' : `尾差过大：${tailDiff.toFixed(2)}元（允许±1元）`

    return { isValid, tailDiff, totalInterest, currentPeriodInterest, totalPrincipal, warning }
  })

  // 按数值浅比较持久化，避免 Map 回写触发死循环
  watch(
    () => validation.value.totalInterest,
    (total) => { onSave?.(TOTAL_INTEREST_KEY, total) },
  )
  watch(
    () => validation.value.currentPeriodInterest,
    (current) => { onSave?.(CURRENT_INTEREST_KEY, current) },
  )

  function selectContract(contractNo: string): void {
    selectedContractNo.value = contractNo
    onSave?.(SELECTED_CONTRACT_KEY, contractNo)
  }

  function save(): void {
    onSave?.(SELECTED_CONTRACT_KEY, selectedContractNo.value)
    onSave?.(TOTAL_INTEREST_KEY, validation.value.totalInterest)
    onSave?.(CURRENT_INTEREST_KEY, validation.value.currentPeriodInterest)
  }

  return {
    selectedContractNo, contracts, selectedContract,
    schedule, computedPV, validation,
    selectContract, save, load,
  }
}

export default useH9Amortization
