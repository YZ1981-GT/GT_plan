/**
 * useG4SppiTest — G4-6 合同现金流量特征分析（SPPI测试）
 *
 * 对齐源模板六段产品表 + 提示知识库：
 * (一)债券/委托贷款 (二)银行理财三步 (三)优先股永续债
 * (四)可转债 (五)项目收益债/信托 (六)ABS
 * + 与 G4-5 业务模式勾稽 → 综合分类
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  determineSPPIConclusion,
  determineFinalClassification,
  determineBusinessModel,
  suggestAbsSppiByTranche,
  suggestFinancialStep1Conclusion,
  suggestFinancialStep2Conclusion,
  type SPPIResult,
  type BusinessModelResult,
  type BusinessModelAnswers,
} from '@/composables/useG4SppiFormulaEngine'
import type { ChecklistResponse } from '@/composables/useG4SppiFormData'
import { ENRICHED_METHODOLOGY_MAP } from '@/composables/g4SppiGuidance'
import { api } from '@/services/apiProxy'
import http from '@/utils/http'
import {
  G4_CLASSIFICATION_WRITEBACK_EVENT,
  applyG4ClassificationUpdates,
  deriveG4MeasurementClassification,
  fetchCanonicalRowsFromWorkpaper,
  resolveG4MainWorkpaperId,
  saveCanonicalRowsToWorkpaper,
  type G4ClassificationUpdate,
} from '@/components/workpaper/composables/g4CrossHelpers'
import { G4_ITEM_IDS } from '@/components/workpaper/composables/g4StorageContract'

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
  /** 偿付顺序（源模板列） */
  repaymentOrder: string
  hasEarlyRedemption: boolean
  hasExtension: boolean
  hasEquityConversion: boolean
  hasLeverage: boolean
  conclusion: SPPIConclusionValue
  conclusionOverridden: boolean
  analysisType: AnalysisType | null
  methodologyText: string
}

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
  conclusionOverridden: boolean
}

export interface FinancialStep2Item {
  id: string
  investProject: string
  fixedReturnRate: number
  floatingMethod: string
  baseVariableHistory: string
  isUnrealistic: boolean
  conclusion: 'PASS' | 'FAIL' | null
  conclusionOverridden: boolean
}

export interface FinancialStep3Item {
  id: string
  investProject: string
  underlyingAssetType: string
  underlyingSppiFeature: string
  conclusion: 'PASS' | 'FAIL' | null
}

/** 部分(三) 优先股、永续债 */
export interface PreferredPerpetualItem {
  id: string
  investProject: string
  totalAmount: number
  term: string
  couponRate: string
  deferredInterest: boolean
  interestCumulative: boolean
  rateStepUp: string
  convertibleToEquity: boolean
  conclusion: SPPIConclusionValue
  judgmentNote: string
}

/** 部分(四) 可转换债券 */
export interface ConvertibleBondItem {
  id: string
  investProject: string
  totalAmount: number
  term: string
  couponRate: string
  conversionPrice: string
  conclusion: SPPIConclusionValue
  judgmentNote: string
}

/** 部分(五) 项目收益债、信托计划 */
export interface ProjectTrustItem {
  id: string
  investProject: string
  totalAmount: number
  term: string
  couponRate: string
  underlyingCashFlow: string
  conclusion: SPPIConclusionValue
  judgmentNote: string
}

/** 部分(六) 资产支持证券 */
export interface AbsItem {
  id: string
  investProject: string
  shareAmount: number
  term: string
  couponRate: string
  tranche: string
  underlyingCashFlow: string
  creditRiskSharing: string
  conclusion: SPPIConclusionValue
  conclusionOverridden: boolean
  judgmentNote: string
}

/** 基准测试工作区状态 */
export interface BenchmarkWorkspace {
  investProject: string
  thresholdPct: number
  conclusion: SPPIResult
  conclusionOverridden: boolean
  remark: string
  rows: Array<{ period: number; contractCf: number; benchmarkCf: number }>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY_BOND_ITEMS = 'G4-6-bond-items'
const STORAGE_KEY_BOND_CONCLUSION = 'G4-6-bond-conclusion'
const STORAGE_KEY_STEP1 = 'G4-6-step1-items'
const STORAGE_KEY_STEP2 = 'G4-6-step2-items'
const STORAGE_KEY_STEP3 = 'G4-6-step3-items'
const STORAGE_KEY_FINANCIAL_CONCLUSION = 'G4-6-financial-conclusion'
const STORAGE_KEY_PREFERRED = 'G4-6-preferred-items'
const STORAGE_KEY_CONVERTIBLE = 'G4-6-convertible-items'
const STORAGE_KEY_PROJECT_TRUST = 'G4-6-project-trust-items'
const STORAGE_KEY_ABS = 'G4-6-abs-items'
const STORAGE_KEY_OVERALL_CONCLUSION = 'G4-6-overall-conclusion'
const STORAGE_KEY_AUDIT_NOTE = 'G4-6-sppitest-audit-note'
const STORAGE_KEY_BENCHMARK = 'G4-6-benchmark'

const MAX_ROWS = 200

export const ANALYSIS_TYPE_OPTIONS: Array<{ value: AnalysisType; label: string }> = [
  { value: 'simple', label: '简单条款直接分析' },
  { value: 'floating_rate', label: '浮动利率' },
  { value: 'rate_adjustment', label: '利率调整' },
  { value: 'prepayment', label: '提前偿付特征' },
  { value: 'extension', label: '展期选择权' },
  { value: 'non_recourse', label: '无追索权' },
  { value: 'linked_instrument', label: '合同挂钩工具' },
]

export const SPPI_CONCLUSION_OPTIONS: Array<{ value: SPPIConclusionValue; label: string }> = [
  { value: 'PASS', label: '通过SPPI测试' },
  { value: 'FAIL', label: '通不过SPPI测试' },
  { value: 'FURTHER_ANALYSIS', label: '需进一步分析' },
]

/** @deprecated 使用 ENRICHED_METHODOLOGY_MAP；保留导出兼容 */
export const METHODOLOGY_MAP: Record<AnalysisType, string> = {
  simple: ENRICHED_METHODOLOGY_MAP.simple,
  floating_rate: ENRICHED_METHODOLOGY_MAP.floating_rate,
  rate_adjustment: ENRICHED_METHODOLOGY_MAP.rate_adjustment,
  prepayment: ENRICHED_METHODOLOGY_MAP.prepayment,
  extension: ENRICHED_METHODOLOGY_MAP.extension,
  non_recourse: ENRICHED_METHODOLOGY_MAP.non_recourse,
  linked_instrument: ENRICHED_METHODOLOGY_MAP.linked_instrument,
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
    repaymentOrder: '不涉及',
    hasEarlyRedemption: false,
    hasExtension: false,
    hasEquityConversion: false,
    hasLeverage: false,
    conclusion: null,
    conclusionOverridden: false,
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
    conclusionOverridden: false,
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
    conclusionOverridden: false,
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

function createEmptyPreferred(name: string): PreferredPerpetualItem {
  return {
    id: generateId(),
    investProject: name,
    totalAmount: 0,
    term: '',
    couponRate: '',
    deferredInterest: false,
    interestCumulative: true,
    rateStepUp: '',
    convertibleToEquity: false,
    conclusion: null,
    judgmentNote: '',
  }
}

function createEmptyConvertible(name: string): ConvertibleBondItem {
  return {
    id: generateId(),
    investProject: name,
    totalAmount: 0,
    term: '',
    couponRate: '',
    conversionPrice: '',
    conclusion: 'FAIL',
    judgmentNote:
      '含权益转换特征，合同现金流量通常并非仅为对本金和利息的支付，默认通不过SPPI测试。',
  }
}

function createEmptyProjectTrust(name: string): ProjectTrustItem {
  return {
    id: generateId(),
    investProject: name,
    totalAmount: 0,
    term: '',
    couponRate: '',
    underlyingCashFlow: '',
    conclusion: null,
    judgmentNote: '',
  }
}

function createEmptyAbs(name: string): AbsItem {
  return {
    id: generateId(),
    investProject: name,
    shareAmount: 0,
    term: '',
    couponRate: '',
    tranche: '',
    underlyingCashFlow: '',
    creditRiskSharing: '',
    conclusion: null,
    conclusionOverridden: false,
    judgmentNote: '',
  }
}

function createEmptyBenchmark(): BenchmarkWorkspace {
  return {
    investProject: '',
    thresholdPct: 10,
    conclusion: 'PASS',
    conclusionOverridden: false,
    remark: '',
    rows: [{ period: 1, contractCf: 0, benchmarkCf: 0 }],
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

function worstSppi(results: SPPIConclusionValue[]): SPPIResult | 'INCOMPLETE' {
  const filled = results.filter((r): r is SPPIResult => r === 'PASS' || r === 'FAIL' || r === 'FURTHER_ANALYSIS')
  if (filled.length === 0) return 'INCOMPLETE'
  if (filled.some((r) => r === 'FAIL')) return 'FAIL'
  if (filled.some((r) => r === 'FURTHER_ANALYSIS')) return 'FURTHER_ANALYSIS'
  return 'PASS'
}

function mapBmFromQuestionnaireRemark(remark: string | null | undefined): BusinessModelResult {
  const parsed = safeParseJson<Array<{ id: string; answer: boolean | null }>>(remark)
  if (!parsed || !Array.isArray(parsed)) return 'INCOMPLETE'
  const get = (id: string): boolean | null => parsed.find((q) => q.id === id)?.answer ?? null
  const answers: BusinessModelAnswers = {
    q1: get('q1'),
    q2: get('q2'),
    q2_1: get('q2_1'),
    q2_2: get('q2_2'),
    q2_3: get('q2_3'),
    q3: get('q3'),
    q4: get('q4'),
    q5: get('q5'),
  }
  return determineBusinessModel(answers)
}

function readG45QuestionnaireRaw(
  responses: Map<string, ChecklistResponse>,
): string | null | undefined {
  const item = responses.get('G4-5-questionnaire')
  return item?.conclusion || item?.remark
}

function readG45SubPortfolioBm(
  responses: Map<string, ChecklistResponse>,
  investProject: string,
): { businessModelResult: BusinessModelResult; sourcePortfolioId?: string } | null {
  const subItem = responses.get('G4-5-sub-portfolios')
  const raw = subItem?.conclusion || subItem?.remark
  const parsed = safeParseJson<Array<{ id: string; name: string; conclusion?: BusinessModelResult }>>(raw)
  if (!parsed || !Array.isArray(parsed)) return null
  const key = investProject.replace(/\s+/g, '')
  const hit = parsed.find(p => String(p.name || '').replace(/\s+/g, '') === key)
  if (!hit || !hit.conclusion || hit.conclusion === 'INCOMPLETE') return null
  return { businessModelResult: hit.conclusion, sourcePortfolioId: hit.id }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseG4SppiTestOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
  wpId?: Ref<string>
  projectId?: Ref<string>
}

export function useG4SppiTest(opts: UseG4SppiTestOptions) {
  const { allResponses, debouncedSave, isReadonly, wpId, projectId } = opts

  const bondItems = ref<BondSppiItem[]>([createEmptyBondItem('')])
  const bondConclusion = ref('')
  const step1Items = ref<FinancialStep1Item[]>([createEmptyStep1('')])
  const step2Items = ref<FinancialStep2Item[]>([createEmptyStep2('')])
  const step3Items = ref<FinancialStep3Item[]>([createEmptyStep3('')])
  const financialConclusion = ref('')
  const preferredItems = ref<PreferredPerpetualItem[]>([])
  const convertibleItems = ref<ConvertibleBondItem[]>([])
  const projectTrustItems = ref<ProjectTrustItem[]>([])
  const absItems = ref<AbsItem[]>([])
  const overallConclusion = ref('')
  const auditNote = ref('')
  const benchmark = ref<BenchmarkWorkspace>(createEmptyBenchmark())

  function applyStep1Auto(item: FinancialStep1Item): void {
    if (item.conclusionOverridden) return
    const suggested = suggestFinancialStep1Conclusion({
      guaranteesPrincipal: item.guaranteesPrincipal,
      hasFixedReturn: item.hasFixedReturn,
      hasFloatingReturn: item.hasFloatingReturn,
    })
    if (suggested != null) {
      item.conclusion = suggested
      return
    }
    // 有浮动时：跟同名第二步结论
    if (item.hasFloatingReturn) {
      const s2 = step2Items.value.find((x) => x.investProject.trim() === item.investProject.trim())
      if (s2?.conclusion) item.conclusion = s2.conclusion
    }
  }

  function applyStep2Auto(item: FinancialStep2Item): void {
    if (item.conclusionOverridden) return
    const suggested = suggestFinancialStep2Conclusion(item.isUnrealistic)
    if (suggested != null) item.conclusion = suggested
  }

  function syncStep1FromStep2(projectName: string): void {
    const name = projectName.trim()
    if (!name) return
    const s2 = step2Items.value.find((x) => x.investProject.trim() === name)
    for (const s1 of step1Items.value) {
      if (s1.investProject.trim() !== name || s1.conclusionOverridden) continue
      if (!s1.hasFloatingReturn) continue
      if (s2?.conclusion) s1.conclusion = s2.conclusion
    }
  }

  function applyAbsAuto(item: AbsItem): void {
    if (item.conclusionOverridden) return
    const suggested = suggestAbsSppiByTranche(item.tranche)
    if (suggested != null) {
      item.conclusion = suggested
      if (suggested === 'FAIL' && !item.judgmentNote) {
        item.judgmentNote = '次级/劣后档优先吸收信用损失，风险特征通常不符合基本借贷安排，默认通不过SPPI测试。'
      }
    }
  }

  function readStoredRaw(itemId: string): string | null {
    const item = allResponses.value.get(itemId)
    const c = item?.conclusion
    if (c != null && String(c).trim() !== '') return String(c)
    const r = item?.remark
    if (r != null && String(r).trim() !== '') return String(r)
    return null
  }

  function loadFromResponses(): void {
    const bondParsed = safeParseJson<BondSppiItem[]>(readStoredRaw(STORAGE_KEY_BOND_ITEMS))
    if (bondParsed?.length) {
      bondItems.value = bondParsed.map((item) => ({
        ...createEmptyBondItem(item.investProject || ''),
        ...item,
        repaymentOrder: item.repaymentOrder ?? '不涉及',
        conclusionOverridden: Boolean(item.conclusionOverridden),
      }))
    }

    bondConclusion.value = readStoredRaw(STORAGE_KEY_BOND_CONCLUSION) || ''

    const s1 = safeParseJson<FinancialStep1Item[]>(readStoredRaw(STORAGE_KEY_STEP1))
    if (s1?.length) {
      step1Items.value = s1.map((item) => ({
        ...createEmptyStep1(item.investProject || ''),
        ...item,
        conclusionOverridden: Boolean(item.conclusionOverridden),
      }))
    }
    const s2 = safeParseJson<FinancialStep2Item[]>(readStoredRaw(STORAGE_KEY_STEP2))
    if (s2?.length) {
      step2Items.value = s2.map((item) => ({
        ...createEmptyStep2(item.investProject || ''),
        ...item,
        conclusionOverridden: Boolean(item.conclusionOverridden),
      }))
    }
    const s3 = safeParseJson<FinancialStep3Item[]>(readStoredRaw(STORAGE_KEY_STEP3))
    if (s3?.length) step3Items.value = s3

    financialConclusion.value = readStoredRaw(STORAGE_KEY_FINANCIAL_CONCLUSION) || ''

    const pref = safeParseJson<PreferredPerpetualItem[]>(readStoredRaw(STORAGE_KEY_PREFERRED))
    if (pref) preferredItems.value = pref
    const conv = safeParseJson<ConvertibleBondItem[]>(readStoredRaw(STORAGE_KEY_CONVERTIBLE))
    if (conv) convertibleItems.value = conv
    const pt = safeParseJson<ProjectTrustItem[]>(readStoredRaw(STORAGE_KEY_PROJECT_TRUST))
    if (pt) projectTrustItems.value = pt
    const abs = safeParseJson<AbsItem[]>(readStoredRaw(STORAGE_KEY_ABS))
    if (abs) {
      absItems.value = abs.map((item) => ({
        ...createEmptyAbs(item.investProject || ''),
        ...item,
        conclusionOverridden: Boolean(item.conclusionOverridden),
      }))
    }

    overallConclusion.value = readStoredRaw(STORAGE_KEY_OVERALL_CONCLUSION) || ''
    auditNote.value = readStoredRaw(STORAGE_KEY_AUDIT_NOTE) || ''

    const bm = safeParseJson<BenchmarkWorkspace>(readStoredRaw(STORAGE_KEY_BENCHMARK))
    if (bm) benchmark.value = { ...createEmptyBenchmark(), ...bm }
  }

  watch(
    () => [
      readStoredRaw(STORAGE_KEY_BOND_ITEMS),
      readStoredRaw(STORAGE_KEY_STEP1),
      readStoredRaw(STORAGE_KEY_STEP2),
      readStoredRaw(STORAGE_KEY_STEP3),
      readStoredRaw(STORAGE_KEY_PREFERRED),
      readStoredRaw(STORAGE_KEY_CONVERTIBLE),
      readStoredRaw(STORAGE_KEY_PROJECT_TRUST),
      readStoredRaw(STORAGE_KEY_ABS),
      readStoredRaw(STORAGE_KEY_AUDIT_NOTE),
      readStoredRaw(STORAGE_KEY_OVERALL_CONCLUSION),
      readStoredRaw(STORAGE_KEY_BENCHMARK),
    ],
    () => loadFromResponses(),
    { immediate: true },
  )

  watch(
    () => bondItems.value.map((item) => [
      item.hasEarlyRedemption,
      item.hasExtension,
      item.hasEquityConversion,
      item.hasLeverage,
    ]),
    () => {
      for (const item of bondItems.value) {
        if (item.conclusionOverridden) continue
        item.conclusion = determineSPPIConclusion(
          item.hasEarlyRedemption,
          item.hasExtension,
          item.hasEquityConversion,
          item.hasLeverage,
        )
      }
    },
    { deep: true },
  )

  watch(
    () => bondItems.value.map((item) => item.analysisType),
    () => {
      for (const item of bondItems.value) {
        item.methodologyText = item.analysisType
          ? (ENRICHED_METHODOLOGY_MAP[item.analysisType] || METHODOLOGY_MAP[item.analysisType] || '')
          : ''
      }
    },
    { deep: true, immediate: true },
  )

  watch(
    () => convertibleItems.value.map((i) => i.id),
    () => {
      for (const item of convertibleItems.value) {
        if (item.conclusion == null) item.conclusion = 'FAIL'
      }
    },
  )

  watch(
    () => preferredItems.value.map((i) => i.convertibleToEquity),
    () => {
      for (const item of preferredItems.value) {
        if (item.convertibleToEquity) item.conclusion = 'FAIL'
        else if (item.conclusion == null) item.conclusion = 'PASS'
      }
    },
    { deep: true },
  )

  const businessModelResult = computed<BusinessModelResult>(() =>
    mapBmFromQuestionnaireRemark(readG45QuestionnaireRaw(allResponses.value)),
  )

  const overallSppiResult = computed(() => {
    const all: SPPIConclusionValue[] = [
      ...bondItems.value.filter((i) => i.investProject.trim()).map((i) => i.conclusion),
      ...step1Items.value.filter((i) => i.investProject.trim()).map((i) => i.conclusion),
      ...step2Items.value.filter((i) => i.investProject.trim()).map((i) => i.conclusion),
      ...step3Items.value.filter((i) => i.investProject.trim()).map((i) => i.conclusion),
      ...preferredItems.value.filter((i) => i.investProject.trim()).map((i) => i.conclusion),
      ...convertibleItems.value.filter((i) => i.investProject.trim()).map((i) => i.conclusion),
      ...projectTrustItems.value.filter((i) => i.investProject.trim()).map((i) => i.conclusion),
      ...absItems.value.filter((i) => i.investProject.trim()).map((i) => i.conclusion),
    ]
    // 基准测试一旦填写项目或现金流，其结论参与综合
    if (
      benchmark.value.investProject.trim() ||
      benchmark.value.rows.some((r) => r.contractCf || r.benchmarkCf)
    ) {
      all.push(benchmark.value.conclusion)
    }
    return worstSppi(all)
  })

  const finalClassificationLabel = computed(() => {
    const sppi = overallSppiResult.value
    const bm = businessModelResult.value
    if (sppi === 'INCOMPLETE' || bm === 'INCOMPLETE') return '请完成 G4-5 业务模式与本表 SPPI 结论'
    return determineFinalClassification(bm, sppi)
  })

  const classificationWarning = computed(() => {
    if (overallSppiResult.value === 'FAIL') {
      return '存在通不过SPPI测试的项目：后续计量应为以公允价值计量且其变动计入当期损益（FVTPL），请核对科目归类是否仍适用债权投资(G4)。'
    }
    if (businessModelResult.value !== 'INCOMPLETE' && businessModelResult.value !== 'AC') {
      return 'G4-5 业务模式非「以收取合同现金流量为目标」：债权投资(G4)通常适用摊余成本(AC)。若为FVOCI/FVTPL，请确认是否应归入G6或其他科目。'
    }
    return ''
  })

  const totalProjectCount = computed(() => {
    const names = new Set<string>()
    const add = (n: string) => { if (n.trim()) names.add(n.trim()) }
    bondItems.value.forEach((i) => add(i.investProject))
    step1Items.value.forEach((i) => add(i.investProject))
    preferredItems.value.forEach((i) => add(i.investProject))
    convertibleItems.value.forEach((i) => add(i.investProject))
    projectTrustItems.value.forEach((i) => add(i.investProject))
    absItems.value.forEach((i) => add(i.investProject))
    return names.size
  })

  function persist(key: string, payload: string): void {
    if (isReadonly.value) return
    debouncedSave(key, { conclusion: payload, remark: payload })
  }

  function persistBondItems(): void {
    persist(STORAGE_KEY_BOND_ITEMS, JSON.stringify(bondItems.value))
  }
  function persistStep1(): void {
    persist(STORAGE_KEY_STEP1, JSON.stringify(step1Items.value))
  }
  function persistStep2(): void {
    persist(STORAGE_KEY_STEP2, JSON.stringify(step2Items.value))
  }
  function persistStep3(): void {
    persist(STORAGE_KEY_STEP3, JSON.stringify(step3Items.value))
  }
  function persistPreferred(): void {
    persist(STORAGE_KEY_PREFERRED, JSON.stringify(preferredItems.value))
  }
  function persistConvertible(): void {
    persist(STORAGE_KEY_CONVERTIBLE, JSON.stringify(convertibleItems.value))
  }
  function persistProjectTrust(): void {
    persist(STORAGE_KEY_PROJECT_TRUST, JSON.stringify(projectTrustItems.value))
  }
  function persistAbs(): void {
    persist(STORAGE_KEY_ABS, JSON.stringify(absItems.value))
  }

  async function promptName(title: string): Promise<string | null> {
    try {
      const { value: name } = await ElMessageBox.prompt('请输入投资项目名称', title, {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '投资项目名称不能为空',
      })
      return name
    } catch {
      return null
    }
  }

  function updateBondItem(id: string, patch: Partial<BondSppiItem>): void {
    if (isReadonly.value) return
    const flagKeys = ['hasEarlyRedemption', 'hasExtension', 'hasEquityConversion', 'hasLeverage'] as const
    const flagsChanged = flagKeys.some((k) => k in patch)
    bondItems.value = bondItems.value.map((item) => {
      if (item.id !== id) return item
      const next = { ...item, ...patch }
      if (flagsChanged && !('conclusion' in patch) && !('conclusionOverridden' in patch)) {
        next.conclusionOverridden = false
        next.conclusion = determineSPPIConclusion(
          next.hasEarlyRedemption,
          next.hasExtension,
          next.hasEquityConversion,
          next.hasLeverage,
        )
      }
      return next
    })
    persistBondItems()
  }

  function setBondConclusion(id: string, value: SPPIConclusionValue): void {
    if (isReadonly.value) return
    const item = bondItems.value.find((i) => i.id === id)
    if (item) {
      item.conclusion = value
      item.conclusionOverridden = true
      persistBondItems()
    }
  }

  async function addBondItem(): Promise<void> {
    if (isReadonly.value) return
    if (bondItems.value.length >= MAX_ROWS) {
      ElMessageBox.alert(`行数已达上限（${MAX_ROWS}行），无法继续新增。`, '提示')
      return
    }
    const name = await promptName('新增投资项目')
    if (!name) return
    bondItems.value = [...bondItems.value, createEmptyBondItem(name)]
    persistBondItems()
  }

  function removeBondItem(id: string): void {
    if (isReadonly.value || bondItems.value.length <= 1) return
    bondItems.value = bondItems.value.filter((item) => item.id !== id)
    persistBondItems()
  }

  function setBondAuditConclusion(value: string): void {
    if (isReadonly.value) return
    bondConclusion.value = value
    persist(STORAGE_KEY_BOND_CONCLUSION, value)
  }

  function updateStep1Item(id: string, patch: Partial<FinancialStep1Item>): void {
    if (isReadonly.value) return
    const flagKeys = ['guaranteesPrincipal', 'hasFixedReturn', 'hasFloatingReturn'] as const
    const flagsChanged = flagKeys.some((k) => k in patch)
    step1Items.value = step1Items.value.map((item) => {
      if (item.id !== id) return item
      const next = { ...item, ...patch }
      if ('conclusion' in patch && !('conclusionOverridden' in patch)) {
        next.conclusionOverridden = true
      }
      if (flagsChanged && !('conclusion' in patch)) {
        next.conclusionOverridden = false
        applyStep1Auto(next)
      } else if (!next.conclusionOverridden) {
        applyStep1Auto(next)
      }
      return next
    })
    persistStep1()
  }

  function updateStep2Item(id: string, patch: Partial<FinancialStep2Item>): void {
    if (isReadonly.value) return
    let projectName = ''
    step2Items.value = step2Items.value.map((item) => {
      if (item.id !== id) return item
      const next = { ...item, ...patch }
      if ('conclusion' in patch && !('conclusionOverridden' in patch)) {
        next.conclusionOverridden = true
      }
      if ('isUnrealistic' in patch && !('conclusion' in patch)) {
        next.conclusionOverridden = false
        applyStep2Auto(next)
      } else if (!next.conclusionOverridden) {
        applyStep2Auto(next)
      }
      projectName = next.investProject
      return next
    })
    persistStep2()
    if (projectName) {
      syncStep1FromStep2(projectName)
      persistStep1()
    }
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
    const name = await promptName('新增理财产品')
    if (!name) return
    step1Items.value = [...step1Items.value, createEmptyStep1(name)]
    step2Items.value = [...step2Items.value, createEmptyStep2(name)]
    step3Items.value = [...step3Items.value, createEmptyStep3(name)]
    persistStep1()
    persistStep2()
    persistStep3()
  }

  function removeFinancialItem(id: string): void {
    if (isReadonly.value) return
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
    persist(STORAGE_KEY_FINANCIAL_CONCLUSION, value)
  }

  function updatePreferredItem(id: string, patch: Partial<PreferredPerpetualItem>): void {
    if (isReadonly.value) return
    preferredItems.value = preferredItems.value.map((i) => (i.id === id ? { ...i, ...patch } : i))
    persistPreferred()
  }

  async function addPreferredItem(): Promise<void> {
    if (isReadonly.value) return
    const name = await promptName('新增优先股/永续债')
    if (!name) return
    preferredItems.value = [...preferredItems.value, createEmptyPreferred(name)]
    persistPreferred()
  }

  function removePreferredItem(id: string): void {
    if (isReadonly.value) return
    preferredItems.value = preferredItems.value.filter((i) => i.id !== id)
    persistPreferred()
  }

  function updateConvertibleItem(id: string, patch: Partial<ConvertibleBondItem>): void {
    if (isReadonly.value) return
    convertibleItems.value = convertibleItems.value.map((i) => (i.id === id ? { ...i, ...patch } : i))
    persistConvertible()
  }

  async function addConvertibleItem(): Promise<void> {
    if (isReadonly.value) return
    const name = await promptName('新增可转换债券')
    if (!name) return
    convertibleItems.value = [...convertibleItems.value, createEmptyConvertible(name)]
    persistConvertible()
  }

  function removeConvertibleItem(id: string): void {
    if (isReadonly.value) return
    convertibleItems.value = convertibleItems.value.filter((i) => i.id !== id)
    persistConvertible()
  }

  function updateProjectTrustItem(id: string, patch: Partial<ProjectTrustItem>): void {
    if (isReadonly.value) return
    projectTrustItems.value = projectTrustItems.value.map((i) => (i.id === id ? { ...i, ...patch } : i))
    persistProjectTrust()
  }

  async function addProjectTrustItem(): Promise<void> {
    if (isReadonly.value) return
    const name = await promptName('新增项目收益债/信托')
    if (!name) return
    projectTrustItems.value = [...projectTrustItems.value, createEmptyProjectTrust(name)]
    persistProjectTrust()
  }

  function removeProjectTrustItem(id: string): void {
    if (isReadonly.value) return
    projectTrustItems.value = projectTrustItems.value.filter((i) => i.id !== id)
    persistProjectTrust()
  }

  function updateAbsItem(id: string, patch: Partial<AbsItem>): void {
    if (isReadonly.value) return
    absItems.value = absItems.value.map((item) => {
      if (item.id !== id) return item
      const next = { ...item, ...patch }
      if ('conclusion' in patch && !('conclusionOverridden' in patch)) {
        next.conclusionOverridden = true
      }
      if ('tranche' in patch && !('conclusion' in patch)) {
        next.conclusionOverridden = false
        applyAbsAuto(next)
      } else if (!next.conclusionOverridden && 'tranche' in patch) {
        applyAbsAuto(next)
      }
      return next
    })
    persistAbs()
  }

  async function addAbsItem(): Promise<void> {
    if (isReadonly.value) return
    const name = await promptName('新增资产支持证券')
    if (!name) return
    absItems.value = [...absItems.value, createEmptyAbs(name)]
    persistAbs()
  }

  function removeAbsItem(id: string): void {
    if (isReadonly.value) return
    absItems.value = absItems.value.filter((i) => i.id !== id)
    persistAbs()
  }

  function setOverallConclusion(value: string): void {
    if (isReadonly.value) return
    overallConclusion.value = value
    persist(STORAGE_KEY_OVERALL_CONCLUSION, value)
  }

  function setAuditNote(value: string): void {
    if (isReadonly.value) return
    auditNote.value = value
    persist(STORAGE_KEY_AUDIT_NOTE, value)
  }

  function setBenchmark(value: BenchmarkWorkspace): void {
    if (isReadonly.value) return
    benchmark.value = value
    persist(STORAGE_KEY_BENCHMARK, JSON.stringify(value))
  }

  async function fetchG42RowsFromWp(targetWpId: string): Promise<Array<{ investProject?: string; investmentProject?: string; name?: string }> | null> {
    const res = await api.get(`/api/workpapers/${targetWpId}/checklist-responses`)
    const responses: any[] = Array.isArray(res) ? res : ((res as any)?.data ?? [])
    const rowResp = responses.find((r: any) => r.item_id === 'G4-2-rows')
    return safeParseJson(rowResp?.conclusion || rowResp?.remark)
  }

  async function resolveG4MainWpId(): Promise<string | null> {
    const pid = projectId?.value
    if (!pid) return null
    try {
      const { data } = await http.get('/api/acnr/resolve-instance', {
        params: { project_id: pid, parent: 'G4', sheet_code: 'G4-2' },
        _silent: true,
      } as any)
      const wp = data?.data?.wp_id ?? data?.wp_id
      if (wp) return String(wp)
      const { data: data2 } = await http.get('/api/acnr/resolve-instance', {
        params: { project_id: pid, parent: 'G4', sheet_code: 'G4' },
        _silent: true,
      } as any)
      const wp2 = data2?.data?.wp_id ?? data2?.wp_id
      return wp2 ? String(wp2) : null
    } catch {
      return null
    }
  }

  async function seedBondProjectsFromDetail(): Promise<void> {
    if (isReadonly.value || !wpId?.value) return
    try {
      let rows = await fetchG42RowsFromWp(wpId.value)
      let source = '本底稿'
      if (!rows?.length) {
        const altWp = await resolveG4MainWpId()
        if (altWp && altWp !== wpId.value) {
          rows = await fetchG42RowsFromWp(altWp)
          source = 'G4 主底稿'
        }
      }
      if (!rows?.length) {
        ElMessage.warning('未找到 G4-2 明细数据，请先在明细表填写后再带入')
        return
      }
      const existing = new Set(bondItems.value.map((i) => i.investProject.trim()).filter(Boolean))
      const names = rows
        .map((r) => (r.investProject || r.investmentProject || r.name || '').trim())
        .filter((n) => n && !existing.has(n))
      if (!names.length) {
        ElMessage.info('明细项目均已存在于部分(一)，无需带入')
        return
      }
      const filledEmpty = !bondItems.value[0]?.investProject?.trim()
      const base = filledEmpty ? [] : [...bondItems.value]
      bondItems.value = [
        ...base,
        ...names.slice(0, MAX_ROWS - base.length).map((n) => createEmptyBondItem(n)),
      ]
      if (!bondItems.value.length) bondItems.value = [createEmptyBondItem('')]
      persistBondItems()
      ElMessage.success(`已从${source}明细带入 ${names.length} 个投资项目`)
    } catch {
      ElMessage.warning('读取 G4-2 明细失败')
    }
  }

  function buildClassificationUpdates(): G4ClassificationUpdate[] {
    const ranked = new Map<string, G4ClassificationUpdate>()
    const rank = (value?: string) => value === 'FAIL' ? 3 : value === 'FURTHER_ANALYSIS' ? 2 : value === 'PASS' ? 1 : 0
    const add = (investProject: string, sppiResult: string | null | undefined, investmentId?: string) => {
      const name = investProject.trim()
      if (!name) return
      const key = name.replace(/\s+/g, '')
      const sub = readG45SubPortfolioBm(allResponses.value, name)
      const next: G4ClassificationUpdate = {
        investProject: name,
        investmentId: investmentId || undefined,
        crossSheetInvestmentId: investmentId || undefined,
        businessModelResult: sub?.businessModelResult || businessModelResult.value,
        sourcePortfolioId: sub?.sourcePortfolioId,
        sppiResult: sppiResult || 'INCOMPLETE',
        classificationSource: 'G4-5/G4-6',
      }
      if (rank(next.sppiResult) >= rank(ranked.get(key)?.sppiResult)) ranked.set(key, next)
    }
    bondItems.value.forEach(item => add(item.investProject, item.conclusion, item.id))
    step1Items.value.forEach(item => add(item.investProject, item.conclusion, item.id))
    step2Items.value.forEach(item => add(item.investProject, item.conclusion, item.id))
    step3Items.value.forEach(item => add(item.investProject, item.conclusion, item.id))
    preferredItems.value.forEach(item => add(item.investProject, item.conclusion, item.id))
    convertibleItems.value.forEach(item => add(item.investProject, item.conclusion, item.id))
    projectTrustItems.value.forEach(item => add(item.investProject, item.conclusion, item.id))
    absItems.value.forEach(item => add(item.investProject, item.conclusion, item.id))
    return Array.from(ranked.values())
  }

  async function writeClassificationToG42(): Promise<void> {
    if (isReadonly.value) return
    const updates = buildClassificationUpdates()
    if (!updates.length) {
      ElMessage.warning('无可回写的投资项目分类')
      return
    }
    const preview = updates.map(update => ({
      ...update,
      measurementClassification: deriveG4MeasurementClassification(
        update.businessModelResult,
        update.sppiResult,
      ),
    }))
    const needsReclassification = preview.some(update =>
      update.measurementClassification === 'FVOCI' || update.measurementClassification === 'FVTPL',
    )
    if (needsReclassification) {
      ElMessage.error(
        '检测到 FVOCI/FVTPL 计量分类：债权投资(G4)套件仅适用摊余成本(AC)。请先重分类至 G6/G1 后再回写，当前已阻断。',
      )
      return
    }
    try {
      await ElMessageBox.confirm(
        `将按项目名称回写 ${updates.length} 条分类至 G4-2（仅 AC）。`,
        '回写分类至 G4-2',
        { confirmButtonText: '确认回写', cancelButtonText: '取消', type: 'info' },
      )
    } catch {
      return
    }
    const targetWpId = await resolveG4MainWorkpaperId(projectId?.value || '', wpId?.value)
    if (!targetWpId) {
      ElMessage.error('未找到 G4 主底稿')
      return
    }
    try {
      const existing = await fetchCanonicalRowsFromWorkpaper(targetWpId, G4_ITEM_IDS.G4_2_ROWS)
      const result = applyG4ClassificationUpdates(existing, updates)
      await saveCanonicalRowsToWorkpaper(
        targetWpId,
        projectId?.value || '',
        G4_ITEM_IDS.G4_2_ROWS,
        result.rows,
      )
      window.dispatchEvent(new CustomEvent(G4_CLASSIFICATION_WRITEBACK_EVENT, {
        detail: { updates, matched: result.matched, unmatched: result.unmatched, source: 'G4-6' },
      }))
      const unmatched = result.unmatched.length ? `，未匹配 ${result.unmatched.length} 条` : ''
      ElMessage.success(`已回写 ${result.matched.length} 条分类至 G4-2${unmatched}`)
    } catch {
      ElMessage.error('分类回写 G4-2 失败')
    }
  }

  return {
    bondItems,
    bondConclusion,
    step1Items,
    step2Items,
    step3Items,
    financialConclusion,
    preferredItems,
    convertibleItems,
    projectTrustItems,
    absItems,
    overallConclusion,
    auditNote,
    benchmark,
    businessModelResult,
    overallSppiResult,
    finalClassificationLabel,
    classificationWarning,
    totalProjectCount,
    updateBondItem,
    setBondConclusion,
    addBondItem,
    removeBondItem,
    setBondAuditConclusion,
    updateStep1Item,
    updateStep2Item,
    updateStep3Item,
    addFinancialItem,
    removeFinancialItem,
    setFinancialAuditConclusion,
    updatePreferredItem,
    addPreferredItem,
    removePreferredItem,
    updateConvertibleItem,
    addConvertibleItem,
    removeConvertibleItem,
    updateProjectTrustItem,
    addProjectTrustItem,
    removeProjectTrustItem,
    updateAbsItem,
    addAbsItem,
    removeAbsItem,
    setOverallConclusion,
    setAuditNote,
    setBenchmark,
    seedBondProjectsFromDetail,
    buildClassificationUpdates,
    writeClassificationToG42,
    loadFromResponses,
    persistBondItems,
    persistStep1,
    persistStep2,
    persistStep3,
  }
}

export default useG4SppiTest
