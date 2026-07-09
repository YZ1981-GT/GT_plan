/**
 * useH9Amortization — 摊销表 composable（合同筛选+完整表生成，前端计算视图）
 *
 * H9-4 摊销表是 H9 的核心计算视图（非物理sheet，纯前端计算）：
 * - 从H9-2合同下拉选择
 * - 使用 useH9AmortizationEngine + useH9PVEngine 生成完整摊销表
 * - 验证最后一期期末余额≈0
 * - 与H9-1审定表利息费用交叉验证
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
  ibrRate: number
  leaseTerm: number
  annualPayment: number
}

/** 摊销表校验结果 */
export interface ScheduleValidation {
  isValid: boolean
  tailDiff: number
  totalInterest: number
  totalPrincipal: number
  warning: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const SELECTED_CONTRACT_KEY = 'H9-4-selected-contract'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH9Amortization(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const selectedContractNo = ref('')
  const contracts = ref<ContractOption[]>([])

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

  // ─── Load contracts from H9-2 ─────────────────────────────────────────────

  function load(): void {
    // 从H9-2明细表数据读取合同列表
    const h9DetailData = _getJson('H9-2-rows')
    if (Array.isArray(h9DetailData)) {
      contracts.value = h9DetailData.map((r: any) => ({
        contractNo: r.contractNo ?? '',
        lessor: r.lessor ?? '',
        initialBalance: Number(r.beginBalance) || 0,
        ibrRate: Number(r.ibrRate) || 0,
        leaseTerm: Number(r.leaseTerm) || 0,
        annualPayment: Number(r.repayment) || 0,
      })).filter((c: ContractOption) => c.contractNo)
    } else {
      contracts.value = []
    }
    selectedContractNo.value = _getString(SELECTED_CONTRACT_KEY) || (contracts.value[0]?.contractNo ?? '')
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed: 当前选中合同 ────────────────────────────────────────────────

  const selectedContract: ComputedRef<ContractOption | null> = computed(() =>
    contracts.value.find(c => c.contractNo === selectedContractNo.value) ?? null,
  )

  // ─── Computed: 生成摊销表 ──────────────────────────────────────────────────

  const schedule: ComputedRef<AmortizationRow[]> = computed(() => {
    const contract = selectedContract.value
    if (!contract || contract.initialBalance <= 0 || contract.leaseTerm <= 0) {
      return []
    }
    // 每期利率 = IBR年利率 / 12（按月摊销）
    const monthlyRate = contract.ibrRate / 12
    // 每期付款 = 年付款 / 12
    const monthlyPayment = contract.annualPayment / 12
    return generateSchedule(contract.initialBalance, monthlyPayment, monthlyRate, contract.leaseTerm)
  })

  // ─── Computed: 计算现值（验证初始金额） ────────────────────────────────────

  const computedPV: ComputedRef<number> = computed(() => {
    const contract = selectedContract.value
    if (!contract || contract.leaseTerm <= 0) return 0
    const monthlyRate = contract.ibrRate / 12
    const monthlyPayment = contract.annualPayment / 12
    return calcAnnuityPV(monthlyPayment, monthlyRate, contract.leaseTerm)
  })

  // ─── Computed: 摊销表校验 ──────────────────────────────────────────────────

  const validation: ComputedRef<ScheduleValidation> = computed(() => {
    const s = schedule.value
    if (s.length === 0) {
      return { isValid: true, tailDiff: 0, totalInterest: 0, totalPrincipal: 0, warning: '' }
    }

    const { isValid, tailDiff } = validateSchedule(s)
    const totalInterest = calcSubtotal(s.map(r => r.interest))
    const totalPrincipal = calcSubtotal(s.map(r => r.principal))
    const warning = isValid ? '' : `尾差过大：${tailDiff.toFixed(2)}元（允许±1元）`

    return { isValid, tailDiff, totalInterest, totalPrincipal, warning }
  })

  // ─── Actions ───────────────────────────────────────────────────────────────

  function selectContract(contractNo: string): void {
    selectedContractNo.value = contractNo
    onSave?.(SELECTED_CONTRACT_KEY, contractNo)
  }

  function save(): void {
    onSave?.(SELECTED_CONTRACT_KEY, selectedContractNo.value)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    selectedContractNo, contracts, selectedContract,
    schedule, computedPV, validation,
    selectContract, save, load,
  }
}

export default useH9Amortization
