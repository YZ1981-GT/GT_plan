/**
 * useD1NotesReceivable — D1 应收票据核心逻辑 composable
 *
 * Spec: .kiro/specs/d1-notes-receivable/
 * Tasks: 3.1 ~ 3.13
 *
 * 职责：
 * - Tab 管理 + localStorage 持久化
 * - 审定表 D1-1 计算（公式 + 跨 sheet 引用）
 * - 程序表 D1A 状态/结论/进度
 * - ECL 坏账准备（迁徙率法/个别认定）
 * - 业务模式分析（SPPI + 到期分析）
 * - 背书贴现 CRUD + 终止确认
 * - 贴息计算
 * - 监盘倒推
 * - 质押检查
 * - 关联方检查
 * - 附注披露
 * - 调整分录 CRUD + 审定表同步
 * - EventBus 联动（发布 + 监听 + 卸载注销）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type ProcedureStatus = '未开始' | '执行中' | '已完成' | '不适用'
export type EclMethod = '组合评估' | '个别认定'
export type BusinessModelType =
  | '以摊余成本计量'
  | '以公允价值计量且变动计入其他综合收益'
  | '以公允价值计量且变动计入当期损益'
export type DerecognitionResult = '终止确认' | '不终止确认'
export type DisclosureConclusion = '已披露且准确' | '已披露但需修改' | '未披露需补充' | '不适用'
export type CheckConclusion = '符合' | '不符合' | '不适用'
export type TabStatus = 'completed' | 'in-progress' | 'not-started'
export type AdjustmentType = 'AJE' | 'RJE'

export interface AdjudicationRow {
  rowKey: string
  label: string
  priorPeriod: number
  currentUnadjusted: number
  periodChange: number
  ajeDebit: number
  ajeCredit: number
  rjeDebit: number
  rjeCredit: number
  auditedAmount: number
  changeRate: number | null | ''
  isFromCrossSheet: boolean
}

export interface CrossSheetRefValues {
  d12_B14: number
  d12_C14: number
  d12_D14: number
  d12_B13: number
  d12_C13: number
  d12_D13: number
  d14_B23: number
  d14_C23: number
}

export interface ProcedureStep {
  stepOrder: number
  stepName: string
  description: string
  status: ProcedureStatus
  executor: string
  executeDate: string
  wpIndexRef: string
  findings: string
  conclusion: string
  isRequired: boolean
  relatedTab: string | null
}

export interface RiskIndicator {
  level: 'H' | 'M' | 'L'
  description: string
}

export interface AgingBand {
  bandKey: string
  label: string
  priorBalance: number
  currentProvision: number
  currentReversal: number
  currentWriteOff: number
  endBalance: number
  expectedLossRate: number
  shouldProvision: number
  actualProvision: number
  difference: number
}

export interface MigrationRateRow {
  fromBand: string
  toBand: string
  year1Rate: number
  year2Rate: number
  year3Rate: number
  averageRate: number
}

export interface EclSummary {
  totalEndBalance: number
  totalShouldProvision: number
  totalActualProvision: number
  totalDifference: number
  exceedsMateriality: boolean
}

export interface MaturityGroup {
  groupKey: string
  label: string
  amount: number
  percentage: number
}

export interface EndorsementItem {
  index: number
  noteNo: string
  drawer: string
  amount: number
  maturityDate: string
  endorseDate: string
  transferee: string
  derecognition: DerecognitionResult | null
  remark: string
}

export interface EndorsementSummary {
  endorsedNotMatured: number
  discountedNotMatured: number
  derecognizedAmount: number
  notDerecognizedAmount: number
}

export interface DiscountInterestItem {
  index: number
  discountAmount: number
  discountRate: number
  discountDays: number
  auditeeInterest: number
  auditorInterest: number
  difference: number
}

export interface InventoryReconciliation {
  countDate: string
  countLocation: string
  countBalance: number
  additions: number
  deductions: number
  bsDateBalance: number
  bookBalance: number
  difference: number
}

export interface PledgeItem {
  index: number
  noteNo: string
  amount: number
  pledgee: string
  purpose: string
  releaseDate: string
  isRestricted: boolean
}

export interface RelatedPartyItem {
  index: number
  partyName: string
  relationType: string
  transactionAmount: number
  noteNo: string
  isNormalTerms: boolean
  remark: string
}

export interface DisclosureCheckItem {
  index: number
  checkItem: string
  conclusion: DisclosureConclusion | null
  remark: string
}

export interface AdjustmentEntry {
  index: number
  type: AdjustmentType
  debitAccount: string
  creditAccount: string
  amount: number
  description: string
  isPushedToAdjTable: boolean
}

export interface LinkageRef {
  label: string
  targetWpCode: string
  icon: string
}

export interface SubstantiveAdjudicatedPayload {
  wpCode: string
  accountCode: string
  auditedAmount: number
  priorAmount: number
  changeRate: number | null
}

export interface AdjustmentCreatedPayload {
  wpCode: string
  entryType: AdjustmentType
  debitAccount: string
  creditAccount: string
  amount: number
  description: string
}

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

// ─── Constants ───────────────────────────────────────────────────────────────

export const TAB_NAMES = [
  'directory', 'procedure', 'adjudication', 'disclosure',
  'detail-category', 'detail-customer', 'bad-debt', 'adjustment',
  'business-model', 'ledger-reconciliation', 'endorsement', 'interest',
  'inventory', 'related-party', 'pledge', 'general-check',
  'ecl-policy', 'ecl-test', 'writeoff',
] as const

export const PROCEDURE_STEPS_CONFIG: Array<{
  stepName: string
  description: string
  isRequired: boolean
  relatedTab: string | null
}> = [
  { stepName: '获取明细', description: '获取应收票据明细表，检查与总账/明细账一致性', isRequired: true, relatedTab: 'detail-category' },
  { stepName: '核对总账', description: '核对应收票据总账余额与明细账合计数', isRequired: true, relatedTab: 'adjudication' },
  { stepName: '票据验真', description: '对重要票据执行真伪验证程序', isRequired: true, relatedTab: 'general-check' },
  { stepName: '到期分析', description: '按到期日分组分析票据，关注逾期情况', isRequired: true, relatedTab: 'business-model' },
  { stepName: '背书贴现', description: '检查已背书/已贴现票据的终止确认处理', isRequired: true, relatedTab: 'endorsement' },
  { stepName: '减值评估', description: '评估应收票据预期信用损失计提充分性', isRequired: true, relatedTab: 'bad-debt' },
  { stepName: '披露检查', description: '检查应收票据相关附注披露完整性和准确性', isRequired: true, relatedTab: 'disclosure' },
  { stepName: '结论', description: '汇总应收票据审计发现，形成整体结论', isRequired: false, relatedTab: null },
]

export const AGING_BANDS_CONFIG: Array<{ bandKey: string; label: string }> = [
  { bandKey: 'not-overdue', label: '未逾期' },
  { bandKey: 'overdue-1-30', label: '逾期1-30天' },
  { bandKey: 'overdue-31-90', label: '逾期31-90天' },
  { bandKey: 'overdue-91-180', label: '逾期91-180天' },
  { bandKey: 'overdue-181-365', label: '逾期181-365天' },
  { bandKey: 'overdue-1year', label: '逾期1年以上' },
]

export const ADJUDICATION_ROWS_CONFIG: Array<{ rowKey: string; label: string }> = [
  { rowKey: 'bank-acceptance', label: '应收票据-银行承兑汇票' },
  { rowKey: 'commercial-acceptance', label: '应收票据-商业承兑汇票' },
  { rowKey: 'bad-debt', label: '坏账准备' },
  { rowKey: 'book-value', label: '账面价值' },
]

const LOCALSTORAGE_TAB_KEY = 'd1-notes-receivable-active-tab'

// ─── Pure Functions (exported for testing) ───────────────────────────────────

/**
 * 审定数 = 期末未审数 + AJE借方 - AJE贷方 + RJE借方 - RJE贷方
 */
export function getAuditedAmount(
  currentUnadjusted: number,
  ajeDebit: number,
  ajeCredit: number,
  rjeDebit: number,
  rjeCredit: number
): number {
  return currentUnadjusted + ajeDebit - ajeCredit + rjeDebit - rjeCredit
}

/**
 * 变动率三分支：
 * - 期初=0 且 审定数=0 → ''
 * - 期初=0 → 1
 * - 其他 → (审定数 - 期初) / 期初
 */
export function getChangeRate(priorPeriod: number, auditedAmount: number): number | '' {
  if (priorPeriod === 0 && auditedAmount === 0) return ''
  if (priorPeriod === 0) return 1
  return (auditedAmount - priorPeriod) / priorPeriod
}

/**
 * ECL 迁徙率法：预期损失率 = 各阶段平均迁徙率连乘
 */
export function calculateExpectedLossRate(migrationRates: number[]): number {
  if (migrationRates.length === 0) return 0
  return migrationRates.reduce((acc, rate) => acc * rate, 1)
}

/**
 * 应计提金额 = 余额 × 预期损失率
 */
export function calculateProvision(balance: number, lossRate: number): number {
  return balance * lossRate
}

/**
 * 差异 = 实际计提 - 应计提
 */
export function calculateDifference(actualProvision: number, shouldProvision: number): number {
  return actualProvision - shouldProvision
}

/**
 * 贴息 = P × R × D / 360
 */
export function calculateInterest(p: number, r: number, d: number): number {
  return p * r * d / 360
}

/**
 * 监盘倒推：资产负债表日余额 = 盘点日余额 + 期间增加 - 期间减少
 */
export function calculateBSDateBalance(countBalance: number, additions: number, deductions: number): number {
  return countBalance + additions - deductions
}

/**
 * Tab 完成状态判定
 */
export function getTabStatusFromResponses(tabResponses: ChecklistResponse[]): TabStatus {
  if (tabResponses.length === 0) return 'not-started'
  const hasValue = tabResponses.some(r => r.conclusion || r.remark)
  if (!hasValue) return 'not-started'
  const allComplete = tabResponses.every(r => r.conclusion || r.remark)
  return allComplete ? 'completed' : 'in-progress'
}

// ─── Main Composable ─────────────────────────────────────────────────────────

export function useD1NotesReceivable(
  allResponses: Ref<Map<string, ChecklistResponse>>,
  wpId: Ref<string>,
  projectId: Ref<string>,
  year: Ref<number>,
  saveImmediate: SaveFn,
  externalReadonly: Ref<boolean>,
  loadSubWorkpaperData?: (subWpCode: string) => Promise<Record<string, string | number>>
) {
  // ─── Helpers ─────────────────────────────────────────────────────────────

  function getVal(itemId: string): ChecklistResponse {
    return allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
  }

  function setLocal(itemId: string, conclusion: string | null, remark: string | null = null): ChecklistItem {
    const item: ChecklistItem = { item_id: itemId, conclusion, remark }
    allResponses.value.set(itemId, item)
    return item
  }

  function parseNum(val: string | number | null | undefined): number {
    if (val === null || val === undefined || val === '') return 0
    const n = typeof val === 'number' ? val : parseFloat(val)
    return isNaN(n) ? 0 : n
  }


  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.1: Tab 管理 + localStorage 持久化 + linkageRefs
  // ═══════════════════════════════════════════════════════════════════════════

  const activeTab = ref<string>(restoreActiveTab())
  const tabVisited = ref<Set<string>>(new Set([activeTab.value]))

  function restoreActiveTab(): string {
    try {
      const saved = localStorage.getItem(LOCALSTORAGE_TAB_KEY)
      if (saved && (TAB_NAMES as readonly string[]).includes(saved)) return saved
    } catch { /* ignore */ }
    return 'directory'
  }

  function setActiveTab(tab: string): void {
    activeTab.value = tab
    tabVisited.value.add(tab)
    try {
      localStorage.setItem(LOCALSTORAGE_TAB_KEY, tab)
    } catch { /* ignore */ }
  }

  /** Tab 完成状态 */
  const tabCompletionStatus: ComputedRef<Map<string, TabStatus>> = computed(() => {
    const statusMap = new Map<string, TabStatus>()
    const prefixMap: Record<string, string[]> = {
      'procedure': ['D1-proc-'],
      'adjudication': ['D1-adj-'],
      'bad-debt': ['D1-ecl-'],
      'adjustment': ['D1-entry-'],
      'business-model': ['D1-sppi-', 'D1-biz-', 'D1-maturity-'],
      'endorsement': ['D1-endorse-'],
      'interest': ['D1-interest-'],
      'inventory': ['D1-inventory-'],
      'related-party': ['D1-rp-'],
      'pledge': ['D1-pledge-'],
      'general-check': ['D1-check-'],
      'ecl-policy': ['D1-policy-'],
      'ecl-test': ['D1-ecltest-'],
      'writeoff': ['D1-writeoff-'],
      'disclosure': ['D1-disc-'],
    }

    for (const [tabName, prefixes] of Object.entries(prefixMap)) {
      const tabResponses: ChecklistResponse[] = []
      for (const [key, val] of allResponses.value.entries()) {
        if (prefixes.some(p => key.startsWith(p))) {
          tabResponses.push(val)
        }
      }
      statusMap.set(tabName, getTabStatusFromResponses(tabResponses))
    }
    // Tabs without prefix mapping default to not-started
    for (const tab of TAB_NAMES) {
      if (!statusMap.has(tab)) statusMap.set(tab, 'not-started')
    }
    return statusMap
  })

  /** 联动面板引用 */
  const linkageRefs: ComputedRef<LinkageRef[]> = computed(() => [
    { label: '试算平衡表', targetWpCode: 'trial_balance', icon: '📊' },
    { label: 'B50 风险评估', targetWpCode: 'B50', icon: '⚠️' },
    { label: 'C2 控制测试', targetWpCode: 'C2', icon: '🔒' },
    { label: 'A13 错报汇总', targetWpCode: 'A13', icon: '📋' },
  ])

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.2: 审定表 D1-1 计算逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  const crossSheetData = ref<Record<string, string | number>>({})
  const d14Data = ref<Record<string, string | number>>({})

  const crossSheetValues: ComputedRef<CrossSheetRefValues> = computed(() => ({
    d12_B14: parseNum(crossSheetData.value['D1-2-B14']),
    d12_C14: parseNum(crossSheetData.value['D1-2-C14']),
    d12_D14: parseNum(crossSheetData.value['D1-2-D14']),
    d12_B13: parseNum(crossSheetData.value['D1-2-B13']),
    d12_C13: parseNum(crossSheetData.value['D1-2-C13']),
    d12_D13: parseNum(crossSheetData.value['D1-2-D13']),
    d14_B23: parseNum(d14Data.value['D1-4-B23'] ?? getVal('D1-ecl-total-prior').remark),
    d14_C23: parseNum(d14Data.value['D1-4-C23'] ?? getVal('D1-ecl-total-current').remark),
  }))

  async function refreshCrossSheetData(): Promise<void> {
    if (!loadSubWorkpaperData) return
    try {
      const d12 = await loadSubWorkpaperData('D1-2')
      crossSheetData.value = Object.fromEntries(
        Object.entries(d12).map(([k, v]) => [`D1-2-${k}`, v])
      )
    } catch { /* handled by useD1FormData */ }
    try {
      const d14 = await loadSubWorkpaperData('D1-4')
      d14Data.value = Object.fromEntries(
        Object.entries(d14).map(([k, v]) => [`D1-4-${k}`, v])
      )
    } catch { /* handled by useD1FormData */ }
  }

  /** 审定表各行数据 */
  const adjudicationRows: ComputedRef<AdjudicationRow[]> = computed(() => {
    return ADJUDICATION_ROWS_CONFIG.map(({ rowKey, label }) => {
      let priorPeriod: number
      let currentUnadjusted: number

      // 跨 sheet 引用
      if (rowKey === 'bank-acceptance') {
        priorPeriod = crossSheetValues.value.d12_B14 || parseNum(getVal(`D1-adj-${rowKey}-prior`).remark)
        currentUnadjusted = crossSheetValues.value.d12_C14 || parseNum(getVal(`D1-adj-${rowKey}-current`).remark)
      } else if (rowKey === 'commercial-acceptance') {
        priorPeriod = crossSheetValues.value.d12_B13 || parseNum(getVal(`D1-adj-${rowKey}-prior`).remark)
        currentUnadjusted = crossSheetValues.value.d12_C13 || parseNum(getVal(`D1-adj-${rowKey}-current`).remark)
      } else if (rowKey === 'bad-debt') {
        priorPeriod = crossSheetValues.value.d14_B23 || parseNum(getVal(`D1-adj-${rowKey}-prior`).remark)
        currentUnadjusted = crossSheetValues.value.d14_C23 || parseNum(getVal(`D1-adj-${rowKey}-current`).remark)
      } else {
        priorPeriod = parseNum(getVal(`D1-adj-${rowKey}-prior`).remark)
        currentUnadjusted = parseNum(getVal(`D1-adj-${rowKey}-current`).remark)
      }

      const ajeDebit = parseNum(getVal(`D1-adj-${rowKey}-aje-dr`).remark)
      const ajeCredit = parseNum(getVal(`D1-adj-${rowKey}-aje-cr`).remark)
      const rjeDebit = parseNum(getVal(`D1-adj-${rowKey}-rje-dr`).remark)
      const rjeCredit = parseNum(getVal(`D1-adj-${rowKey}-rje-cr`).remark)
      const audited = getAuditedAmount(currentUnadjusted, ajeDebit, ajeCredit, rjeDebit, rjeCredit)
      const rate = getChangeRate(priorPeriod, audited)
      const isFromCrossSheet = ['bank-acceptance', 'commercial-acceptance', 'bad-debt'].includes(rowKey)

      return {
        rowKey,
        label,
        priorPeriod,
        currentUnadjusted,
        periodChange: currentUnadjusted - priorPeriod,
        ajeDebit,
        ajeCredit,
        rjeDebit,
        rjeCredit,
        auditedAmount: audited,
        changeRate: rate,
        isFromCrossSheet,
      }
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.3: 程序表 D1A 逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  const riskIndicators = ref<Map<number, RiskIndicator>>(new Map())
  const overallConclusion = ref<string>(getVal('D1-proc-overall').remark || '')

  const procedureSteps: ComputedRef<ProcedureStep[]> = computed(() => {
    return PROCEDURE_STEPS_CONFIG.map((cfg, idx) => {
      const n = idx + 1
      return {
        stepOrder: n,
        stepName: cfg.stepName,
        description: cfg.description,
        status: (getVal(`D1-proc-${n}-status`).conclusion as ProcedureStatus) || '未开始',
        executor: getVal(`D1-proc-${n}-executor`).remark || '',
        executeDate: getVal(`D1-proc-${n}-date`).remark || '',
        wpIndexRef: getVal(`D1-proc-${n}-wpindex`).remark || '',
        findings: getVal(`D1-proc-${n}-findings`).remark || '',
        conclusion: getVal(`D1-proc-${n}-conclusion`).remark || '',
        isRequired: cfg.isRequired,
        relatedTab: cfg.relatedTab,
      }
    })
  })

  function setProcedureStatus(stepIndex: number, status: ProcedureStatus): void {
    const n = stepIndex + 1
    const item = setLocal(`D1-proc-${n}-status`, status)
    saveImmediate([item])
  }

  function setProcedureConclusion(stepIndex: number, conclusion: string): void {
    const n = stepIndex + 1
    const item = setLocal(`D1-proc-${n}-conclusion`, null, conclusion)
    saveImmediate([item])
  }

  const procedureProgress: ComputedRef<{ completed: number; total: number }> = computed(() => {
    const steps = procedureSteps.value
    const total = steps.length
    const completed = steps.filter(s => s.status === '已完成' || s.status === '不适用').length
    return { completed, total }
  })

  const canInputOverallConclusion: ComputedRef<boolean> = computed(() => {
    return procedureSteps.value
      .filter(s => s.isRequired)
      .every(s => s.status === '已完成' || s.status === '不适用')
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.4: ECL 坏账准备逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  const eclMethod: ComputedRef<EclMethod> = computed(() => {
    return (getVal('D1-ecl-method').conclusion as EclMethod) || '组合评估'
  })

  function setEclMethod(method: EclMethod): void {
    const item = setLocal('D1-ecl-method', method)
    saveImmediate([item])
  }

  const agingBands: ComputedRef<AgingBand[]> = computed(() => {
    return AGING_BANDS_CONFIG.map(({ bandKey, label }) => {
      const endBalance = parseNum(getVal(`D1-ecl-${bandKey}-balance`).remark)
      const rateVal = parseNum(getVal(`D1-ecl-${bandKey}-rate`).remark) / 100
      const expectedLossRate = Math.max(0, Math.min(1, rateVal))
      const shouldProvision = calculateProvision(endBalance, expectedLossRate)
      const actualProvision = parseNum(getVal(`D1-ecl-${bandKey}-actual`).remark)
      const difference = calculateDifference(actualProvision, shouldProvision)

      return {
        bandKey,
        label,
        priorBalance: parseNum(getVal(`D1-ecl-${bandKey}-prior`).remark),
        currentProvision: parseNum(getVal(`D1-ecl-${bandKey}-provision`).remark),
        currentReversal: parseNum(getVal(`D1-ecl-${bandKey}-reversal`).remark),
        currentWriteOff: parseNum(getVal(`D1-ecl-${bandKey}-writeoff`).remark),
        endBalance,
        expectedLossRate,
        shouldProvision,
        actualProvision,
        difference,
      }
    })
  })

  const migrationRateMatrix: ComputedRef<MigrationRateRow[]> = computed(() => {
    const rows: MigrationRateRow[] = []
    for (let i = 0; i < AGING_BANDS_CONFIG.length - 1; i++) {
      const from = AGING_BANDS_CONFIG[i].bandKey
      const to = AGING_BANDS_CONFIG[i + 1].bandKey
      const y1 = parseNum(getVal(`D1-ecl-migration-${from}-${to}-y1`).remark) / 100
      const y2 = parseNum(getVal(`D1-ecl-migration-${from}-${to}-y2`).remark) / 100
      const y3 = parseNum(getVal(`D1-ecl-migration-${from}-${to}-y3`).remark) / 100
      const avg = (y1 + y2 + y3) / 3
      rows.push({ fromBand: from, toBand: to, year1Rate: y1, year2Rate: y2, year3Rate: y3, averageRate: avg })
    }
    return rows
  })

  function getExpectedLossRateForBand(bandIndex: number): number {
    const matrix = migrationRateMatrix.value
    // Loss rate = product of average migration rates from this band to the end
    const rates = matrix.slice(bandIndex).map(r => r.averageRate)
    return calculateExpectedLossRate(rates)
  }

  function getProvisionForBand(bandIndex: number): number {
    const band = agingBands.value[bandIndex]
    if (!band) return 0
    return calculateProvision(band.endBalance, band.expectedLossRate)
  }

  function getDifferenceForBand(bandIndex: number): number {
    const band = agingBands.value[bandIndex]
    if (!band) return 0
    return band.difference
  }

  function isDifferenceExceedsMateriality(bandIndex: number): boolean {
    const band = agingBands.value[bandIndex]
    if (!band) return false
    const materiality = parseNum(getVal('D1-ecl-materiality').remark)
    if (materiality <= 0) return false
    return Math.abs(band.difference) > materiality
  }

  const eclSummary: ComputedRef<EclSummary> = computed(() => {
    const bands = agingBands.value
    const totalEndBalance = bands.reduce((s, b) => s + b.endBalance, 0)
    const totalShouldProvision = bands.reduce((s, b) => s + b.shouldProvision, 0)
    const totalActualProvision = bands.reduce((s, b) => s + b.actualProvision, 0)
    const totalDifference = totalActualProvision - totalShouldProvision
    const materiality = parseNum(getVal('D1-ecl-materiality').remark)
    const exceedsMateriality = materiality > 0 && Math.abs(totalDifference) > materiality

    return { totalEndBalance, totalShouldProvision, totalActualProvision, totalDifference, exceedsMateriality }
  })


  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.5: 业务模式分析逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  const sppiTestResult: ComputedRef<'Y' | 'N' | null> = computed(() => {
    const val = getVal('D1-sppi-result').conclusion
    if (val === 'Y' || val === 'N') return val
    return null
  })

  function setSppiTestResult(result: 'Y' | 'N'): void {
    const item = setLocal('D1-sppi-result', result)
    saveImmediate([item])
  }

  const businessModelChoice: ComputedRef<BusinessModelType | null> = computed(() => {
    const val = getVal('D1-biz-model').conclusion as BusinessModelType | null
    return val || null
  })

  function setBusinessModelChoice(model: BusinessModelType): void {
    const item = setLocal('D1-biz-model', model)
    saveImmediate([item])
  }

  const maturityAnalysis: ComputedRef<MaturityGroup[]> = computed(() => {
    const groups: Array<{ groupKey: string; label: string }> = [
      { groupKey: 'not-overdue', label: '未到期' },
      { groupKey: 'overdue-30', label: '逾期≤30天' },
      { groupKey: 'overdue-31-90', label: '逾期31-90天' },
      { groupKey: 'overdue-90-plus', label: '逾期>90天' },
    ]
    const amounts = groups.map(g => parseNum(getVal(`D1-maturity-${g.groupKey}-amount`).remark))
    const total = amounts.reduce((s, a) => s + a, 0)

    return groups.map((g, i) => ({
      groupKey: g.groupKey,
      label: g.label,
      amount: amounts[i],
      percentage: total > 0 ? amounts[i] / total : 0,
    }))
  })

  const suggestedClassification: ComputedRef<string | null> = computed(() => {
    const sppi = sppiTestResult.value
    const model = businessModelChoice.value
    if (sppi === null || model === null) return null
    if (sppi === 'Y' && model === '以摊余成本计量') {
      return '分类正确：以摊余成本计量的金融资产'
    }
    if (sppi === 'N') {
      return '注意：SPPI 测试未通过，应以公允价值计量'
    }
    return null
  })

  const hasOverdue90Plus: ComputedRef<boolean> = computed(() => {
    const group = maturityAnalysis.value.find(g => g.groupKey === 'overdue-90-plus')
    return (group?.amount ?? 0) > 0
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.6: 背书贴现逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  function getEndorsementCount(): number {
    return parseNum(getVal('D1-endorse-count').remark) || 0
  }

  const endorsementItems: ComputedRef<EndorsementItem[]> = computed(() => {
    const count = getEndorsementCount()
    const items: EndorsementItem[] = []
    for (let i = 1; i <= count; i++) {
      items.push({
        index: i,
        noteNo: getVal(`D1-endorse-${i}-noteNo`).remark || '',
        drawer: getVal(`D1-endorse-${i}-drawer`).remark || '',
        amount: parseNum(getVal(`D1-endorse-${i}-amount`).remark),
        maturityDate: getVal(`D1-endorse-${i}-maturityDate`).remark || '',
        endorseDate: getVal(`D1-endorse-${i}-endorseDate`).remark || '',
        transferee: getVal(`D1-endorse-${i}-transferee`).remark || '',
        derecognition: (getVal(`D1-endorse-${i}-derecognition`).conclusion as DerecognitionResult | null) || null,
        remark: getVal(`D1-endorse-${i}-remark`).remark || '',
      })
    }
    return items
  })

  function addEndorsement(item: Partial<EndorsementItem>): void {
    const count = getEndorsementCount()
    if (count >= 100) return
    const n = count + 1
    const items: ChecklistItem[] = [setLocal('D1-endorse-count', null, String(n))]
    if (item.noteNo) items.push(setLocal(`D1-endorse-${n}-noteNo`, null, item.noteNo))
    if (item.drawer) items.push(setLocal(`D1-endorse-${n}-drawer`, null, item.drawer))
    if (item.amount !== undefined) items.push(setLocal(`D1-endorse-${n}-amount`, null, String(item.amount)))
    if (item.maturityDate) items.push(setLocal(`D1-endorse-${n}-maturityDate`, null, item.maturityDate))
    if (item.endorseDate) items.push(setLocal(`D1-endorse-${n}-endorseDate`, null, item.endorseDate))
    if (item.transferee) items.push(setLocal(`D1-endorse-${n}-transferee`, null, item.transferee))
    if (item.derecognition) items.push(setLocal(`D1-endorse-${n}-derecognition`, item.derecognition))
    if (item.remark) items.push(setLocal(`D1-endorse-${n}-remark`, null, item.remark))
    saveImmediate(items)
  }

  function removeEndorsement(index: number): void {
    const count = getEndorsementCount()
    if (index < 1 || index > count) return
    const items: ChecklistItem[] = []
    const fields = ['noteNo', 'drawer', 'amount', 'maturityDate', 'endorseDate', 'transferee', 'derecognition', 'remark']

    // Shift down
    for (let i = index; i < count; i++) {
      for (const f of fields) {
        const srcId = `D1-endorse-${i + 1}-${f}`
        const tgtId = `D1-endorse-${i}-${f}`
        const src = getVal(srcId)
        items.push(setLocal(tgtId, src.conclusion, src.remark))
      }
    }
    // Clear last
    for (const f of fields) {
      items.push(setLocal(`D1-endorse-${count}-${f}`, null, null))
    }
    items.push(setLocal('D1-endorse-count', null, String(count - 1)))
    saveImmediate(items)
  }

  const endorsementSummary: ComputedRef<EndorsementSummary> = computed(() => {
    const items = endorsementItems.value
    let endorsedNotMatured = 0
    let discountedNotMatured = 0
    let derecognizedAmount = 0
    let notDerecognizedAmount = 0

    for (const item of items) {
      if (item.derecognition === '终止确认') {
        derecognizedAmount += item.amount
      } else if (item.derecognition === '不终止确认') {
        notDerecognizedAmount += item.amount
      }
      // Categorize by type (endorsement vs discount based on transferee pattern)
      endorsedNotMatured += item.amount
    }

    return { endorsedNotMatured, discountedNotMatured, derecognizedAmount, notDerecognizedAmount }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.7: 贴息计算逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  function getDiscountInterestCount(): number {
    return parseNum(getVal('D1-interest-count').remark) || 0
  }

  const discountInterestItems: ComputedRef<DiscountInterestItem[]> = computed(() => {
    const count = getDiscountInterestCount()
    const items: DiscountInterestItem[] = []
    for (let i = 1; i <= count; i++) {
      const p = parseNum(getVal(`D1-interest-${i}-amount`).remark)
      const r = parseNum(getVal(`D1-interest-${i}-rate`).remark) / 100
      const d = parseNum(getVal(`D1-interest-${i}-days`).remark)
      const auditeeInterest = parseNum(getVal(`D1-interest-${i}-auditee`).remark)
      const auditorInterest = calculateInterest(p, r, d)
      items.push({
        index: i,
        discountAmount: p,
        discountRate: r,
        discountDays: d,
        auditeeInterest,
        auditorInterest,
        difference: auditeeInterest - auditorInterest,
      })
    }
    return items
  })

  function addDiscountInterest(item: Partial<DiscountInterestItem>): void {
    const count = getDiscountInterestCount()
    const n = count + 1
    const items: ChecklistItem[] = [setLocal('D1-interest-count', null, String(n))]
    if (item.discountAmount !== undefined) items.push(setLocal(`D1-interest-${n}-amount`, null, String(item.discountAmount)))
    if (item.discountRate !== undefined) items.push(setLocal(`D1-interest-${n}-rate`, null, String(item.discountRate * 100)))
    if (item.discountDays !== undefined) items.push(setLocal(`D1-interest-${n}-days`, null, String(item.discountDays)))
    if (item.auditeeInterest !== undefined) items.push(setLocal(`D1-interest-${n}-auditee`, null, String(item.auditeeInterest)))
    saveImmediate(items)
  }

  function removeDiscountInterest(index: number): void {
    const count = getDiscountInterestCount()
    if (index < 1 || index > count) return
    const items: ChecklistItem[] = []
    const fields = ['amount', 'rate', 'days', 'auditee']
    for (let i = index; i < count; i++) {
      for (const f of fields) {
        const src = getVal(`D1-interest-${i + 1}-${f}`)
        items.push(setLocal(`D1-interest-${i}-${f}`, src.conclusion, src.remark))
      }
    }
    for (const f of fields) {
      items.push(setLocal(`D1-interest-${count}-${f}`, null, null))
    }
    items.push(setLocal('D1-interest-count', null, String(count - 1)))
    saveImmediate(items)
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.8: 监盘倒推逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  const inventoryReconciliation: ComputedRef<InventoryReconciliation> = computed(() => {
    const countBalance = parseNum(getVal('D1-inventory-countBalance').remark)
    const additions = parseNum(getVal('D1-inventory-additions').remark)
    const deductions = parseNum(getVal('D1-inventory-deductions').remark)
    const bsDateBalance = calculateBSDateBalance(countBalance, additions, deductions)
    const bookBalance = parseNum(getVal('D1-inventory-bookBalance').remark)

    return {
      countDate: getVal('D1-inventory-countDate').remark || '',
      countLocation: getVal('D1-inventory-countLocation').remark || '',
      countBalance,
      additions,
      deductions,
      bsDateBalance,
      bookBalance,
      difference: bookBalance - bsDateBalance,
    }
  })

  const inventoryDifference: ComputedRef<number> = computed(() => {
    return inventoryReconciliation.value.difference
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.9: 质押检查逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  function getPledgeCount(): number {
    return parseNum(getVal('D1-pledge-count').remark) || 0
  }

  const pledgeItems: ComputedRef<PledgeItem[]> = computed(() => {
    const count = getPledgeCount()
    const items: PledgeItem[] = []
    for (let i = 1; i <= count; i++) {
      items.push({
        index: i,
        noteNo: getVal(`D1-pledge-${i}-noteNo`).remark || '',
        amount: parseNum(getVal(`D1-pledge-${i}-amount`).remark),
        pledgee: getVal(`D1-pledge-${i}-pledgee`).remark || '',
        purpose: getVal(`D1-pledge-${i}-purpose`).remark || '',
        releaseDate: getVal(`D1-pledge-${i}-releaseDate`).remark || '',
        isRestricted: getVal(`D1-pledge-${i}-restricted`).conclusion === 'Y',
      })
    }
    return items
  })

  function addPledge(item: Partial<PledgeItem>): void {
    const count = getPledgeCount()
    const n = count + 1
    const items: ChecklistItem[] = [setLocal('D1-pledge-count', null, String(n))]
    if (item.noteNo) items.push(setLocal(`D1-pledge-${n}-noteNo`, null, item.noteNo))
    if (item.amount !== undefined) items.push(setLocal(`D1-pledge-${n}-amount`, null, String(item.amount)))
    if (item.pledgee) items.push(setLocal(`D1-pledge-${n}-pledgee`, null, item.pledgee))
    if (item.purpose) items.push(setLocal(`D1-pledge-${n}-purpose`, null, item.purpose))
    if (item.releaseDate) items.push(setLocal(`D1-pledge-${n}-releaseDate`, null, item.releaseDate))
    if (item.isRestricted !== undefined) items.push(setLocal(`D1-pledge-${n}-restricted`, item.isRestricted ? 'Y' : 'N'))
    saveImmediate(items)
  }

  function removePledge(index: number): void {
    const count = getPledgeCount()
    if (index < 1 || index > count) return
    const items: ChecklistItem[] = []
    const fields = ['noteNo', 'amount', 'pledgee', 'purpose', 'releaseDate', 'restricted']
    for (let i = index; i < count; i++) {
      for (const f of fields) {
        const src = getVal(`D1-pledge-${i + 1}-${f}`)
        items.push(setLocal(`D1-pledge-${i}-${f}`, src.conclusion, src.remark))
      }
    }
    for (const f of fields) {
      items.push(setLocal(`D1-pledge-${count}-${f}`, null, null))
    }
    items.push(setLocal('D1-pledge-count', null, String(count - 1)))
    saveImmediate(items)
  }

  const pledgeTotalAmount: ComputedRef<number> = computed(() => {
    return pledgeItems.value.reduce((s, p) => s + p.amount, 0)
  })

  const pledgeRatio: ComputedRef<number> = computed(() => {
    // Ratio = pledged / total notes receivable (book value row)
    const bookValue = adjudicationRows.value.find(r => r.rowKey === 'book-value')
    const total = bookValue?.auditedAmount || 0
    if (total <= 0) return 0
    return pledgeTotalAmount.value / total
  })

  const isPledgeRatioWarning: ComputedRef<boolean> = computed(() => {
    return pledgeRatio.value > 0.5
  })


  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.10: 关联方检查逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  function getRelatedPartyCount(): number {
    return parseNum(getVal('D1-rp-count').remark) || 0
  }

  const relatedPartyItems: ComputedRef<RelatedPartyItem[]> = computed(() => {
    const count = getRelatedPartyCount()
    const items: RelatedPartyItem[] = []
    for (let i = 1; i <= count; i++) {
      items.push({
        index: i,
        partyName: getVal(`D1-rp-${i}-name`).remark || '',
        relationType: getVal(`D1-rp-${i}-relation`).remark || '',
        transactionAmount: parseNum(getVal(`D1-rp-${i}-amount`).remark),
        noteNo: getVal(`D1-rp-${i}-noteNo`).remark || '',
        isNormalTerms: getVal(`D1-rp-${i}-normalTerms`).conclusion === 'Y',
        remark: getVal(`D1-rp-${i}-remark`).remark || '',
      })
    }
    return items
  })

  function addRelatedParty(item: Partial<RelatedPartyItem>): void {
    const count = getRelatedPartyCount()
    const n = count + 1
    const items: ChecklistItem[] = [setLocal('D1-rp-count', null, String(n))]
    if (item.partyName) items.push(setLocal(`D1-rp-${n}-name`, null, item.partyName))
    if (item.relationType) items.push(setLocal(`D1-rp-${n}-relation`, null, item.relationType))
    if (item.transactionAmount !== undefined) items.push(setLocal(`D1-rp-${n}-amount`, null, String(item.transactionAmount)))
    if (item.noteNo) items.push(setLocal(`D1-rp-${n}-noteNo`, null, item.noteNo))
    if (item.isNormalTerms !== undefined) items.push(setLocal(`D1-rp-${n}-normalTerms`, item.isNormalTerms ? 'Y' : 'N'))
    if (item.remark) items.push(setLocal(`D1-rp-${n}-remark`, null, item.remark))
    saveImmediate(items)
  }

  function removeRelatedParty(index: number): void {
    const count = getRelatedPartyCount()
    if (index < 1 || index > count) return
    const items: ChecklistItem[] = []
    const fields = ['name', 'relation', 'amount', 'noteNo', 'normalTerms', 'remark']
    for (let i = index; i < count; i++) {
      for (const f of fields) {
        const src = getVal(`D1-rp-${i + 1}-${f}`)
        items.push(setLocal(`D1-rp-${i}-${f}`, src.conclusion, src.remark))
      }
    }
    for (const f of fields) {
      items.push(setLocal(`D1-rp-${count}-${f}`, null, null))
    }
    items.push(setLocal('D1-rp-count', null, String(count - 1)))
    saveImmediate(items)
  }

  /** 自动匹配关联方（从项目关联方清单匹配出票人/承兑人） */
  const matchedRelatedParties: ComputedRef<string[]> = computed(() => {
    // Match endorsement drawers against known related party names
    const rpNames = relatedPartyItems.value.map(rp => rp.partyName).filter(Boolean)
    const endorseDrawers = endorsementItems.value.map(e => e.drawer).filter(Boolean)
    // Return matching names
    return endorseDrawers.filter(d => rpNames.includes(d))
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.11: 附注披露逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  const disclosureTemplate: ComputedRef<'listed' | 'soe' | 'general'> = computed(() => {
    // Determined by project attributes; fallback to 'general'
    const val = getVal('D1-disc-template').conclusion
    if (val === 'listed' || val === 'soe' || val === 'general') return val
    return 'general'
  })

  function setDisclosureTemplate(template: 'listed' | 'soe' | 'general'): void {
    const item = setLocal('D1-disc-template', template)
    saveImmediate([item])
  }

  const LISTED_DISCLOSURE_ITEMS = [
    '应收票据分类及账面价值',
    '坏账准备变动',
    '已质押票据',
    '已背书未到期',
    '已贴现未到期',
    '前五名出票人',
    '关联方票据',
    '会计政策说明',
  ]

  const SOE_DISCLOSURE_ITEMS = [
    '应收票据基本情况',
    '坏账准备计提情况',
    '重大单项计提',
    '已背书/已贴现情况',
    '受限资产情况',
    '关联方票据交易',
  ]

  const disclosureItems: ComputedRef<DisclosureCheckItem[]> = computed(() => {
    const template = disclosureTemplate.value
    const checkItems = template === 'listed' ? LISTED_DISCLOSURE_ITEMS
      : template === 'soe' ? SOE_DISCLOSURE_ITEMS
      : LISTED_DISCLOSURE_ITEMS // general uses listed as base

    const prefix = template === 'soe' ? 'D1-disc-soe' : 'D1-disc-listed'
    return checkItems.map((item, idx) => {
      const n = idx + 1
      return {
        index: n,
        checkItem: item,
        conclusion: (getVal(`${prefix}-${n}`).conclusion as DisclosureConclusion | null) || null,
        remark: getVal(`${prefix}-${n}`).remark || '',
      }
    })
  })

  const hasUndisclosedItems: ComputedRef<boolean> = computed(() => {
    return disclosureItems.value.some(item => item.conclusion === '未披露需补充')
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.12: 调整分录逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  function getAdjustmentCount(): number {
    return parseNum(getVal('D1-entry-count').remark) || 0
  }

  const adjustmentEntries: ComputedRef<AdjustmentEntry[]> = computed(() => {
    const count = getAdjustmentCount()
    const entries: AdjustmentEntry[] = []
    for (let i = 1; i <= count; i++) {
      entries.push({
        index: i,
        type: (getVal(`D1-entry-${i}-type`).conclusion as AdjustmentType) || 'AJE',
        debitAccount: getVal(`D1-entry-${i}-debit`).remark || '',
        creditAccount: getVal(`D1-entry-${i}-credit`).remark || '',
        amount: parseNum(getVal(`D1-entry-${i}-amount`).remark),
        description: getVal(`D1-entry-${i}-desc`).remark || '',
        isPushedToAdjTable: getVal(`D1-entry-${i}-pushed`).conclusion === 'Y',
      })
    }
    return entries
  })

  const ajeTotal: ComputedRef<number> = computed(() => {
    return adjustmentEntries.value
      .filter(e => e.type === 'AJE')
      .reduce((s, e) => s + e.amount, 0)
  })

  const rjeTotal: ComputedRef<number> = computed(() => {
    return adjustmentEntries.value
      .filter(e => e.type === 'RJE')
      .reduce((s, e) => s + e.amount, 0)
  })

  function addAdjustment(entry: Partial<AdjustmentEntry>): void {
    const count = getAdjustmentCount()
    const n = count + 1
    const items: ChecklistItem[] = [setLocal('D1-entry-count', null, String(n))]
    const entryType = entry.type || 'AJE'
    items.push(setLocal(`D1-entry-${n}-type`, entryType))
    if (entry.debitAccount) items.push(setLocal(`D1-entry-${n}-debit`, null, entry.debitAccount))
    if (entry.creditAccount) items.push(setLocal(`D1-entry-${n}-credit`, null, entry.creditAccount))
    if (entry.amount !== undefined) items.push(setLocal(`D1-entry-${n}-amount`, null, String(entry.amount)))
    if (entry.description) items.push(setLocal(`D1-entry-${n}-desc`, null, entry.description))
    saveImmediate(items)

    // Publish EventBus adjustment:created
    publishAdjustmentCreated({
      index: n,
      type: entryType,
      debitAccount: entry.debitAccount || '',
      creditAccount: entry.creditAccount || '',
      amount: entry.amount || 0,
      description: entry.description || '',
      isPushedToAdjTable: false,
    })
  }

  function removeAdjustment(index: number): void {
    const count = getAdjustmentCount()
    if (index < 1 || index > count) return
    const items: ChecklistItem[] = []
    const fields = ['type', 'debit', 'credit', 'amount', 'desc', 'pushed']
    for (let i = index; i < count; i++) {
      for (const f of fields) {
        const src = getVal(`D1-entry-${i + 1}-${f}`)
        items.push(setLocal(`D1-entry-${i}-${f}`, src.conclusion, src.remark))
      }
    }
    for (const f of fields) {
      items.push(setLocal(`D1-entry-${count}-${f}`, null, null))
    }
    items.push(setLocal('D1-entry-count', null, String(count - 1)))
    saveImmediate(items)
  }

  function updateAdjustment(index: number, data: Partial<AdjustmentEntry>): void {
    const count = getAdjustmentCount()
    if (index < 1 || index > count) return
    const items: ChecklistItem[] = []
    if (data.type !== undefined) items.push(setLocal(`D1-entry-${index}-type`, data.type))
    if (data.debitAccount !== undefined) items.push(setLocal(`D1-entry-${index}-debit`, null, data.debitAccount))
    if (data.creditAccount !== undefined) items.push(setLocal(`D1-entry-${index}-credit`, null, data.creditAccount))
    if (data.amount !== undefined) items.push(setLocal(`D1-entry-${index}-amount`, null, String(data.amount)))
    if (data.description !== undefined) items.push(setLocal(`D1-entry-${index}-desc`, null, data.description))
    if (data.isPushedToAdjTable !== undefined) items.push(setLocal(`D1-entry-${index}-pushed`, data.isPushedToAdjTable ? 'Y' : null))
    if (items.length > 0) saveImmediate(items)
  }

  // Bidirectional sync: adjustment entries ↔ adjudication table AJE/RJE columns
  // The adjudicationRows computed already reads from individual D1-adj-*-aje-dr/cr fields.
  // When adjustments change, sync totals into the adjudication row fields.
  watch([ajeTotal, rjeTotal], ([newAje, newRje]) => {
    // Sync AJE total into bank-acceptance row (primary substantive account)
    const items: ChecklistItem[] = []
    items.push(setLocal('D1-adj-bank-acceptance-aje-dr', null, String(newAje)))
    items.push(setLocal('D1-adj-bank-acceptance-rje-dr', null, String(newRje)))
    // Don't call saveImmediate here to avoid circular save loops;
    // the adjudicationRows computed will re-derive from allResponses reactively.
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.13: EventBus 联动
  // ═══════════════════════════════════════════════════════════════════════════

  let previousAuditedAmount: number | null = null
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  /** 发布 substantive:adjudicated */
  function publishAdjudicated(accountCode: string, auditedAmount: number, priorAmount: number, changeRate: number | null): void {
    const payload: SubstantiveAdjudicatedPayload = {
      wpCode: 'D1',
      accountCode,
      auditedAmount,
      priorAmount,
      changeRate,
    }
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', { detail: payload }))
    } catch {
      console.warn('[D1NotesReceivable] EventBus publish substantive:adjudicated failed')
    }
  }

  /** 发布 adjustment:created */
  function publishAdjustmentCreated(entry: AdjustmentEntry): void {
    const payload: AdjustmentCreatedPayload = {
      wpCode: 'D1',
      entryType: entry.type,
      debitAccount: entry.debitAccount,
      creditAccount: entry.creditAccount,
      amount: entry.amount,
      description: entry.description,
    }
    try {
      window.dispatchEvent(new CustomEvent('adjustment:created', { detail: payload }))
    } catch {
      console.warn('[D1NotesReceivable] EventBus publish adjustment:created failed')
    }
  }

  // Watch audited amount changes to publish event
  watch(adjudicationRows, (rows) => {
    const bookValueRow = rows.find(r => r.rowKey === 'book-value')
    if (!bookValueRow) return
    const current = bookValueRow.auditedAmount
    if (previousAuditedAmount !== null && previousAuditedAmount !== current) {
      const rate = bookValueRow.changeRate
      publishAdjudicated(
        '1121',  // 应收票据标准科目编码
        current,
        bookValueRow.priorPeriod,
        typeof rate === 'number' ? rate : null
      )
    }
    previousAuditedAmount = current
  }, { deep: true })

  /** 监听 risk:assessed（B50 → riskIndicators） */
  function onRiskAssessed(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (!detail) return
    // Store risk indicators by step number
    if (detail.stepIndex !== undefined && detail.level) {
      riskIndicators.value.set(detail.stepIndex, {
        level: detail.level,
        description: detail.description || '',
      })
    }
  }

  /** 监听 control:test-concluded（C2 → 程序表提示） */
  function onControlTestConcluded(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (!detail || detail.wpCode !== 'C2') return
    // Store control test hint in findings of step 1 (获取明细) or relevant step
    // This is informational — displayed in procedure table UI
    const hintKey = 'D1-proc-control-hint'
    const conclusion = detail.conclusion || ''
    setLocal(hintKey, null, conclusion)
  }

  // Register event listeners
  function registerEventListeners(): void {
    const riskHandler = (e: Event) => onRiskAssessed(e)
    const controlHandler = (e: Event) => onControlTestConcluded(e)

    window.addEventListener('risk:assessed', riskHandler)
    window.addEventListener('control:test-concluded', controlHandler)

    eventListeners.push(
      { event: 'risk:assessed', handler: riskHandler },
      { event: 'control:test-concluded', handler: controlHandler },
    )
  }

  /** 注销所有事件监听（组件卸载时调用） */
  function unregisterEventListeners(): void {
    for (const { event, handler } of eventListeners) {
      window.removeEventListener(event, handler)
    }
    eventListeners.length = 0
  }

  // Register on creation
  registerEventListeners()

  // Unsubscribe on unmount
  onBeforeUnmount(() => {
    unregisterEventListeners()
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Return
  // ═══════════════════════════════════════════════════════════════════════════

  return {
    // Task 3.1: Tab 管理
    activeTab,
    setActiveTab,
    tabCompletionStatus,
    tabVisited,
    linkageRefs,

    // Task 3.2: 审定表 D1-1
    adjudicationRows,
    crossSheetValues,
    refreshCrossSheetData,

    // Task 3.3: 程序表 D1A
    procedureSteps,
    setProcedureStatus,
    setProcedureConclusion,
    procedureProgress,
    canInputOverallConclusion,
    overallConclusion,
    riskIndicators,

    // Task 3.4: ECL 坏账准备
    eclMethod,
    setEclMethod,
    agingBands,
    migrationRateMatrix,
    getExpectedLossRateForBand,
    getProvisionForBand,
    getDifferenceForBand,
    isDifferenceExceedsMateriality,
    eclSummary,

    // Task 3.5: 业务模式分析
    maturityAnalysis,
    sppiTestResult,
    setSppiTestResult,
    businessModelChoice,
    setBusinessModelChoice,
    suggestedClassification,
    hasOverdue90Plus,

    // Task 3.6: 背书贴现
    endorsementItems,
    addEndorsement,
    removeEndorsement,
    endorsementSummary,

    // Task 3.7: 贴息计算
    discountInterestItems,
    addDiscountInterest,
    removeDiscountInterest,

    // Task 3.8: 监盘倒推
    inventoryReconciliation,
    inventoryDifference,

    // Task 3.9: 质押检查
    pledgeItems,
    addPledge,
    removePledge,
    pledgeTotalAmount,
    pledgeRatio,
    isPledgeRatioWarning,

    // Task 3.10: 关联方检查
    relatedPartyItems,
    addRelatedParty,
    removeRelatedParty,
    matchedRelatedParties,

    // Task 3.11: 附注披露
    disclosureTemplate,
    setDisclosureTemplate,
    disclosureItems,
    hasUndisclosedItems,

    // Task 3.12: 调整分录
    adjustmentEntries,
    addAdjustment,
    removeAdjustment,
    updateAdjustment,
    ajeTotal,
    rjeTotal,

    // Task 3.13: EventBus
    publishAdjudicated,
    publishAdjustmentCreated,
    unregisterEventListeners,
  }
}

export default useD1NotesReceivable
