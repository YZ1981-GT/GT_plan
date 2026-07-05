/**
 * useG4SppiTest — G4-6 合同现金流量特征分析（SPPI测试）
 *
 * Spec: .kiro/specs/g4-bond-investment-sppi/ Task 6.1
 * Requirements: 3.1~3.12, 6.2
 *
 * 职责：
 * - 管理 Part 1: 债券投资及委托贷款 SPPI分析（bondItems，10列，动态行）
 * - 管理 Part 2: 银行理财产品 三步判断（step1/step2/step3 → 各自结论）
 * - 4 布尔标志: hasEarlyRedemption/hasExtension/hasEquityConversion/hasLeverage
 * - watch 4布尔标志变化 → 调用 determineSPPIConclusion → 自动设结论（用户可覆盖）
 * - 动态行增删（ElMessageBox.prompt 输入投资项目名称）
 * - 分析项目选择 → METHODOLOGY_MAP 动态映射判断逻辑文本
 */
import { ref, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { determineSPPIConclusion, type SPPIResult } from '@/composables/useG4SppiFormulaEngine'
import type { ChecklistResponse } from '@/composables/useG4SppiFormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type AnalysisType =
  | 'simple'
  | 'floating_rate'
  | 'rate_adjustment'
  | 'prepayment'
  | 'extension'
  | 'non_recourse'
  | 'linked_instrument'

export type SPPIConclusionValue = 'PASS' | 'FAIL' | 'FURTHER_ANALYSIS' | null

/** 部分(一) 债券投资SPPI行 */
export interface BondSppiItem {
  id: string
  investProject: string
  faceValue: number
  couponRate: number
  hasEarlyRedemption: boolean
  hasExtension: boolean
  hasEquityConversion: boolean
  hasLeverage: boolean
  conclusion: SPPIConclusionValue
  analysisType: AnalysisType | null
  methodologyText: string
}

/** 部分(二) 第一步: 保本保收益 */
export interface FinancialStep1Item {
  id: string
  investProject: string
  totalAmount: number
  guaranteesPrincipal: boolean
  hasFixedReturn: boolean
  fixedReturnRate: number
  hasFloatingReturn: boolean
  floatingReturnRate: number
  conclusion: 'PASS' | 'FAIL' | null
}

/** 部分(二) 第二步: 浮动收益不现实 */
export interface FinancialStep2Item {
  id: string
  investProject: string
  fixedReturnRate: number
  floatingMethod: string
  baseVariableHistory: string
  isUnrealistic: boolean
  conclusion: 'PASS' | 'FAIL' | null
}

/** 部分(二) 第三步: 穿透底层资产 */
export interface FinancialStep3Item {
  id: string
  investProject: string
  underlyingAssetType: string
  underlyingSppiFeature: string
  conclusion: 'PASS' | 'FAIL' | null
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY_BOND_ITEMS = 'G4-6-bond-items'
const STORAGE_KEY_BOND_CONCLUSION = 'G4-6-bond-conclusion'
const STORAGE_KEY_STEP1 = 'G4-6-step1-items'
const STORAGE_KEY_STEP2 = 'G4-6-step2-items'
const STORAGE_KEY_STEP3 = 'G4-6-step3-items'
const STORAGE_KEY_FINANCIAL_CONCLUSION = 'G4-6-financial-conclusion'

const MAX_ROWS = 200

/** 分析项目选项 */
export const ANALYSIS_TYPE_OPTIONS: Array<{ value: AnalysisType; label: string }> = [
  { value: 'simple', label: '简单条款直接分析' },
  { value: 'floating_rate', label: '浮动利率' },
  { value: 'rate_adjustment', label: '利率调整' },
  { value: 'prepayment', label: '提前偿付特征' },
  { value: 'extension', label: '展期选择权' },
  { value: 'non_recourse', label: '无追索权' },
  { value: 'linked_instrument', label: '合同挂钩工具' },
]

/** SPPI结论选项 */
export const SPPI_CONCLUSION_OPTIONS: Array<{ value: SPPIConclusionValue; label: string }> = [
  { value: 'PASS', label: '通过' },
  { value: 'FAIL', label: '不通过' },
  { value: 'FURTHER_ANALYSIS', label: '需进一步分析' },
]

/** 方法论上下文映射（按分析项目类型） */
export const METHODOLOGY_MAP: Record<AnalysisType, string> = {
  simple: '合同现金流量仅为对本金和以未偿付本金金额为基础的利息的支付（即仅包含货币时间价值、信用风险对价和其他基本贷款风险和成本的对价，以及利润率），则通过SPPI测试。',
  floating_rate: '如果浮动利率仅包含对货币时间价值、信用风险、流动性风险和管理成本的对价，且不含杠杆特征，则浮动利率条款不影响SPPI通过。',
  rate_adjustment: '如果利率调整条款的时间与利率重置频率不匹配，需评估合同现金流量差异是否显著。差异不显著时，仍可通过SPPI测试。',
  prepayment: '如果提前偿付金额基本代表未偿付的本金及以未偿付本金为基础的利息（可能包含提前终止的合理补偿），则不影响SPPI判断。',
  extension: '如果展期选择权使得在展期期间的合同现金流量仍为对本金和利息的支付，且不含杠杆特征，则展期条款不影响SPPI通过。',
  non_recourse: '无追索权特征不必然导致SPPI测试不通过。需穿透至底层资产，评估底层资产现金流量特征。',
  linked_instrument: '如果合同挂钩工具的现金流量与基本贷款安排不一致（如挂钩权益工具或商品价格），则SPPI测试不通过。',
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateId(): string {
  return `g4sp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function createEmptyBondItem(name: string): BondSppiItem {
  return {
    id: generateId(),
    investProject: name,
    faceValue: 0,
    couponRate: 0,
    hasEarlyRedemption: false,
    hasExtension: false,
    hasEquityConversion: false,
    hasLeverage: false,
    conclusion: null,
    analysisType: null,
    methodologyText: '',
  }
}

function createEmptyStep1(name: string): FinancialStep1Item {
  return {
    id: generateId(),
    investProject: name,
    totalAmount: 0,
    guaranteesPrincipal: false,
    hasFixedReturn: false,
    fixedReturnRate: 0,
    hasFloatingReturn: false,
    floatingReturnRate: 0,
    conclusion: null,
  }
}

function createEmptyStep2(name: string): FinancialStep2Item {
  return {
    id: generateId(),
    investProject: name,
    fixedReturnRate: 0,
    floatingMethod: '',
    baseVariableHistory: '',
    isUnrealistic: false,
    conclusion: null,
  }
}

function createEmptyStep3(name: string): FinancialStep3Item {
  return {
    id: generateId(),
    investProject: name,
    underlyingAssetType: '',
    underlyingSppiFeature: '',
    conclusion: null,
  }
}

function safeParseJson<T>(jsonStr: string | null | undefined): T | null {
  if (!jsonStr) return null
  try {
    return JSON.parse(jsonStr) as T
  } catch {
    return null
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseG4SppiTestOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}

export function useG4SppiTest(opts: UseG4SppiTestOptions) {
  const { allResponses, debouncedSave, isReadonly } = opts

  // ─── Part 1: 债券投资 SPPI ─────────────────────────────────────────────────
  const bondItems = ref<BondSppiItem[]>([createEmptyBondItem('示例投资项目')])
  const bondConclusion = ref('')

  // ─── Part 2: 银行理财产品三步 ──────────────────────────────────────────────
  const step1Items = ref<FinancialStep1Item[]>([createEmptyStep1('示例理财产品')])
  const step2Items = ref<FinancialStep2Item[]>([createEmptyStep2('示例理财产品')])
  const step3Items = ref<FinancialStep3Item[]>([createEmptyStep3('示例理财产品')])
  const financialConclusion = ref('')

  // ─── 从 allResponses 加载 ────────────────────────────────────────────────

  function loadFromResponses(): void {
    const bondResp = allResponses.value.get(STORAGE_KEY_BOND_ITEMS)
    const bondParsed = safeParseJson<BondSppiItem[]>(bondResp?.remark)
    if (bondParsed && Array.isArray(bondParsed) && bondParsed.length > 0) {
      bondItems.value = bondParsed
    }

    const bondConcResp = allResponses.value.get(STORAGE_KEY_BOND_CONCLUSION)
    bondConclusion.value = bondConcResp?.remark || ''

    const s1Resp = allResponses.value.get(STORAGE_KEY_STEP1)
    const s1Parsed = safeParseJson<FinancialStep1Item[]>(s1Resp?.remark)
    if (s1Parsed && Array.isArray(s1Parsed) && s1Parsed.length > 0) {
      step1Items.value = s1Parsed
    }

    const s2Resp = allResponses.value.get(STORAGE_KEY_STEP2)
    const s2Parsed = safeParseJson<FinancialStep2Item[]>(s2Resp?.remark)
    if (s2Parsed && Array.isArray(s2Parsed) && s2Parsed.length > 0) {
      step2Items.value = s2Parsed
    }

    const s3Resp = allResponses.value.get(STORAGE_KEY_STEP3)
    const s3Parsed = safeParseJson<FinancialStep3Item[]>(s3Resp?.remark)
    if (s3Parsed && Array.isArray(s3Parsed) && s3Parsed.length > 0) {
      step3Items.value = s3Parsed
    }

    const finConcResp = allResponses.value.get(STORAGE_KEY_FINANCIAL_CONCLUSION)
    financialConclusion.value = finConcResp?.remark || ''
  }

  // allResponses 异步加载完成后回填
  watch(
    () => allResponses.value.get(STORAGE_KEY_BOND_ITEMS)?.remark,
    () => loadFromResponses(),
    { immediate: true },
  )

  // ─── watch 4布尔标志 → 自动计算 SPPI 结论 ─────────────────────────────────

  watch(
    () => bondItems.value.map((item) => [
      item.hasEarlyRedemption,
      item.hasExtension,
      item.hasEquityConversion,
      item.hasLeverage,
    ]),
    (newFlags) => {
      for (let i = 0; i < bondItems.value.length; i++) {
        const item = bondItems.value[i]
        const autoResult = determineSPPIConclusion(
          item.hasEarlyRedemption,
          item.hasExtension,
          item.hasEquityConversion,
          item.hasLeverage,
        )
        // 自动设结论（仅当用户未手动设置时才覆盖）
        // 策略：始终自动设，用户可后续手动覆盖
        item.conclusion = autoResult
      }
    },
    { deep: true },
  )

  // watch 分析项目变化 → 更新方法论文本
  watch(
    () => bondItems.value.map((item) => item.analysisType),
    () => {
      for (const item of bondItems.value) {
        item.methodologyText = item.analysisType
          ? METHODOLOGY_MAP[item.analysisType] || ''
          : ''
      }
    },
    { deep: true, immediate: true },
  )

  // ─── 持久化 ──────────────────────────────────────────────────────────────

  function persistBondItems(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_BOND_ITEMS, {
      remark: JSON.stringify(bondItems.value),
    })
  }

  function persistBondConclusion(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_BOND_CONCLUSION, { remark: bondConclusion.value })
  }

  function persistStep1(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_STEP1, { remark: JSON.stringify(step1Items.value) })
  }

  function persistStep2(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_STEP2, { remark: JSON.stringify(step2Items.value) })
  }

  function persistStep3(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_STEP3, { remark: JSON.stringify(step3Items.value) })
  }

  function persistFinancialConclusion(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_FINANCIAL_CONCLUSION, { remark: financialConclusion.value })
  }

  // ─── Part 1 操作 ──────────────────────────────────────────────────────────

  function updateBondItem(id: string, patch: Partial<BondSppiItem>): void {
    if (isReadonly.value) return
    bondItems.value = bondItems.value.map((item) =>
      item.id === id ? { ...item, ...patch } : item,
    )
    persistBondItems()
  }

  /** 手动覆盖结论（优先级高于自动） */
  function setBondConclusion(id: string, value: SPPIConclusionValue): void {
    if (isReadonly.value) return
    const item = bondItems.value.find((i) => i.id === id)
    if (item) {
      item.conclusion = value
      persistBondItems()
    }
  }

  async function addBondItem(): Promise<void> {
    if (isReadonly.value) return
    if (bondItems.value.length >= MAX_ROWS) {
      ElMessageBox.alert(`行数已达上限（${MAX_ROWS}行），无法继续新增。`, '提示')
      return
    }
    try {
      const { value: name } = await ElMessageBox.prompt(
        '请输入投资项目名称',
        '新增投资项目',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '投资项目名称不能为空',
        },
      )
      bondItems.value = [...bondItems.value, createEmptyBondItem(name)]
      persistBondItems()
    } catch {
      /* cancelled */
    }
  }

  function removeBondItem(id: string): void {
    if (isReadonly.value || bondItems.value.length <= 1) return
    bondItems.value = bondItems.value.filter((item) => item.id !== id)
    persistBondItems()
  }

  function setBondAuditConclusion(value: string): void {
    if (isReadonly.value) return
    bondConclusion.value = value
    persistBondConclusion()
  }

  // ─── Part 2 操作 ──────────────────────────────────────────────────────────

  function updateStep1Item(id: string, patch: Partial<FinancialStep1Item>): void {
    if (isReadonly.value) return
    step1Items.value = step1Items.value.map((item) =>
      item.id === id ? { ...item, ...patch } : item,
    )
    persistStep1()
  }

  function updateStep2Item(id: string, patch: Partial<FinancialStep2Item>): void {
    if (isReadonly.value) return
    step2Items.value = step2Items.value.map((item) =>
      item.id === id ? { ...item, ...patch } : item,
    )
    persistStep2()
  }

  function updateStep3Item(id: string, patch: Partial<FinancialStep3Item>): void {
    if (isReadonly.value) return
    step3Items.value = step3Items.value.map((item) =>
      item.id === id ? { ...item, ...patch } : item,
    )
    persistStep3()
  }

  async function addFinancialItem(): Promise<void> {
    if (isReadonly.value) return
    try {
      const { value: name } = await ElMessageBox.prompt(
        '请输入理财产品名称',
        '新增理财产品',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '理财产品名称不能为空',
        },
      )
      step1Items.value = [...step1Items.value, createEmptyStep1(name)]
      step2Items.value = [...step2Items.value, createEmptyStep2(name)]
      step3Items.value = [...step3Items.value, createEmptyStep3(name)]
      persistStep1()
      persistStep2()
      persistStep3()
    } catch {
      /* cancelled */
    }
  }

  function removeFinancialItem(id: string): void {
    if (isReadonly.value) return
    // 跨三步同时删除（同project名匹配）
    const target = step1Items.value.find((i) => i.id === id)
    if (!target) return
    const projName = target.investProject
    step1Items.value = step1Items.value.filter((i) => i.id !== id)
    step2Items.value = step2Items.value.filter((i) => i.investProject !== projName)
    step3Items.value = step3Items.value.filter((i) => i.investProject !== projName)
    persistStep1()
    persistStep2()
    persistStep3()
  }

  function setFinancialAuditConclusion(value: string): void {
    if (isReadonly.value) return
    financialConclusion.value = value
    persistFinancialConclusion()
  }

  return {
    // Part 1
    bondItems,
    bondConclusion,
    // Part 2
    step1Items,
    step2Items,
    step3Items,
    financialConclusion,
    // Part 1 操作
    updateBondItem,
    setBondConclusion,
    addBondItem,
    removeBondItem,
    setBondAuditConclusion,
    // Part 2 操作
    updateStep1Item,
    updateStep2Item,
    updateStep3Item,
    addFinancialItem,
    removeFinancialItem,
    setFinancialAuditConclusion,
    // 加载
    loadFromResponses,
    // 持久化
    persistBondItems,
    persistStep1,
    persistStep2,
    persistStep3,
  }
}

export default useG4SppiTest
