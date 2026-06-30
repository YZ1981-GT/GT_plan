/**
 * useD2AccountsReceivable — D2 应收账款核心逻辑 composable
 *
 * Spec: .kiro/specs/d2-accounts-receivable/
 * Tasks: 3.1 ~ 3.14
 *
 * 职责：
 * - Tab 管理 + localStorage 持久化
 * - 审定表 D2-1 SUMIF 三分类联动计算
 * - 程序表 D2A 状态/结论/进度（7步）
 * - ECL 坏账准备（迁徙率法/组合评估/个别认定）
 * - 截止测试（跨期判定）
 * - 保理分析（终止确认判断）
 * - 函证联动（D0 确认结果）
 * - 分析程序（周转率/周转天数/坏账率）
 * - 关联方检查
 * - 附注披露
 * - 调整分录 CRUD + 审定表同步
 * - EventBus 联动（发布 + 监听 + 卸载注销）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type ProcedureStatus = '未开始' | '执行中' | '已完成' | '不适用'
export type BadDebtMethod = '单项计提' | '账龄组合' | '客户类型组合'
export type DerecognitionResult = '终止确认' | '不终止确认'
export type DisclosureConclusion = '已披露且准确' | '已披露但需修改' | '未披露需补充' | '不适用'
export type CheckConclusion = '符合' | '不符合' | '不适用'
export type TabStatus = 'completed' | 'in-progress' | 'not-started'
export type AdjustmentType = 'AJE' | 'RJE'
export type CutoffResult = '跨期' | '未跨期'

export interface AdjudicationRow {
  rowKey: string
  label: string
  priorUnadjusted: number
  currentUnadjusted: number
  sumifPrior: number
  sumifChange: number
  sumifEnd: number
  ajeAdjustment: number
  rjeAdjustment: number
  auditedAmount: number
  changeRate: number | null | ''
  isFromSumif: boolean
}

export interface SumifAggregation {
  individual_prior: number
  individual_change: number
  individual_end: number
  agingCombo_prior: number
  agingCombo_change: number
  agingCombo_end: number
  customerCombo_prior: number
  customerCombo_change: number
  customerCombo_end: number
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

export interface CutoffTestSample {
  index: number
  invoiceNo: string
  revenueDate: string
  arBookingDate: string
  amount: number
  isCutoffError: boolean
  conclusion: CutoffResult
  remark: string
}

export interface FactoringItem {
  index: number
  category: '质押' | '保理'
  customerName: string
  amount: number
  counterparty: string
  contractNo: string
  startDate: string
  endDate: string
  derecognition: DerecognitionResult | null
  transferRisk: boolean | null
  retainControl: boolean | null
  remark: string
}

export interface FactoringSummary {
  pledgedTotal: number
  factoredTotal: number
  derecognizedAmount: number
  notDerecognizedAmount: number
  pledgeRatio: number
}

export interface ConfirmationSummary {
  sentCount: number
  receivedCount: number
  responseRate: number
  confirmedAmount: number
  differenceAmount: number
}

export interface AnalysisRatios {
  turnoverRate: number
  turnoverDays: number
  priorTurnoverDays: number
  turnoverDaysChangeRate: number
  badDebtRate: number
  priorBadDebtRate: number
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
  'detail-d2-2', 'bad-debt', 'cutoff-test', 'adjustment',
  'ecl-calculation', 'ecl-measurement', 'analysis',
  'related-party', 'factoring', 'general-check',
  'policy-check', 'writeoff-check', 'bizmodel-check',
] as const

export const PROCEDURE_STEPS_CONFIG: Array<{
  stepName: string
  description: string
  isRequired: boolean
  relatedTab: string | null
}> = [
  { stepName: '获取并核对明细', description: '获取应收账款明细表，检查与总账/明细账一致性', isRequired: true, relatedTab: 'detail-d2-2' },
  { stepName: '核对总账', description: '核对应收账款总账余额与明细账合计数', isRequired: true, relatedTab: 'adjudication' },
  { stepName: '函证', description: '对重要客户执行函证程序', isRequired: true, relatedTab: null },
  { stepName: '替代程序', description: '对未回函客户执行替代审计程序', isRequired: true, relatedTab: null },
  { stepName: '坏账准备', description: '评估应收账款预期信用损失计提充分性', isRequired: true, relatedTab: 'bad-debt' },
  { stepName: '截止测试', description: '检查收入确认截止日期的准确性', isRequired: true, relatedTab: 'cutoff-test' },
  { stepName: '结论', description: '汇总应收账款审计发现，形成整体结论', isRequired: false, relatedTab: null },
]

export const AGING_BANDS_CONFIG: Array<{ bandKey: string; label: string }> = [
  { bandKey: 'within-1y', label: '1年以内' },
  { bandKey: '1-2y', label: '1-2年' },
  { bandKey: '2-3y', label: '2-3年' },
  { bandKey: '3-4y', label: '3-4年' },
  { bandKey: '4-5y', label: '4-5年' },
  { bandKey: 'over-5y', label: '5年以上' },
]

export const ADJUDICATION_ROWS_CONFIG: Array<{ rowKey: string; label: string }> = [
  { rowKey: 'individual', label: '应收账款-单项计提' },
  { rowKey: 'aging-combo', label: '应收账款-账龄组合' },
  { rowKey: 'customer-combo', label: '应收账款-客户类型组合' },
  { rowKey: 'bad-debt', label: '坏账准备' },
  { rowKey: 'book-value', label: '账面价值' },
  { rowKey: 'total', label: '合计' },
]

const LOCALSTORAGE_TAB_KEY = 'd2-accounts-receivable-active-tab'

// ─── Pure Functions (exported for PBT testing) ───────────────────────────────

/**
 * 审定数 = 期末未审数 + AJE调整 + RJE调整
 */
export function getAuditedAmount(
  currentUnadjusted: number,
  ajeAdjustment: number,
  rjeAdjustment: number
): number {
  return currentUnadjusted + ajeAdjustment + rjeAdjustment
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
 * 质押比例 = P / T（T=0时返回0）
 */
export function calculatePledgeRatio(pledgedAmount: number, totalAR: number): number {
  if (totalAR === 0) return 0
  return pledgedAmount / totalAR
}

/**
 * 截止测试跨期判定：收入确认日在资产负债表日之后 → 跨期
 */
export function determineCutoff(revenueDate: string, bsDate: string): boolean {
  const rev = new Date(revenueDate)
  const bs = new Date(bsDate)
  if (isNaN(rev.getTime()) || isNaN(bs.getTime())) return false
  return rev > bs
}

/**
 * SUMIF 聚合：按分类过滤后求和
 */
export function sumif(
  rows: Array<{ AI: string; S: number; Z: number; AA: number }>,
  classification: string,
  valueColumn: 'S' | 'Z' | 'AA'
): number {
  return rows
    .filter(row => row.AI === classification)
    .reduce((sum, row) => sum + (Number(row[valueColumn]) || 0), 0)
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
// NOTE: Logic for individual tabs has been extracted to dedicated composables:
// - useD2Adjudication (审定表 D2-1)
// - useD2Detail (明细表 D2-2)
// - useD2BadDebt (坏账准备 D2-3)
// - useD2Adjustment (调整分录 D2-4)
// - useD2Analysis (分析程序 D2-5)
// - useD2RelatedParty (关联方 D2-6)
// - useD2VoucherCheck (凭证抽查 D2-7)
// - useD2PolicyCheck (政策检查 D2-8)
// - useD2Ecl (ECL测算 D2-9/D2-10)
// - useD2WriteoffCheck (转回核销 D2-11)
// - useD2PledgeCheck (质押保理 D2-12)
// - useD2BizModel (业务模式 D2-13)
// - useD2Cutoff (截止测试)
// - useD2Disclosure (附注披露)
// - useD2Procedure (程序表 D2A)
// - useD2ImportExport (导入导出)
// - useD2DualMode (双模式切换)
//
// This composable retains: Tab management, route sync, EventBus coordination,
// and backward-compatible exports consumed by the existing test suite.

export function useD2AccountsReceivable(
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

  function restoreActiveTab(): string {
    try {
      const saved = localStorage.getItem(LOCALSTORAGE_TAB_KEY)
      if (saved && (TAB_NAMES as readonly string[]).includes(saved)) return saved
    } catch { /* ignore */ }
    return 'directory'
  }

  function setActiveTab(tab: string): void {
    activeTab.value = tab
    try {
      localStorage.setItem(LOCALSTORAGE_TAB_KEY, tab)
    } catch { /* ignore */ }
  }

  /** Tab 完成状态 */
  const tabCompletionStatus: ComputedRef<Map<string, TabStatus>> = computed(() => {
    const statusMap = new Map<string, TabStatus>()
    const prefixMap: Record<string, string[]> = {
      'procedure': ['D2-proc-'],
      'adjudication': ['D2-adj-'],
      'bad-debt': ['D2-ecl-', 'D2-baddebt-'],
      'adjustment': ['D2-entry-'],
      'cutoff-test': ['D2-cutoff-'],
      'factoring': ['D2-factoring-'],
      'analysis': ['D2-analysis-'],
      'related-party': ['D2-rp-'],
      'general-check': ['D2-check7-'],
      'policy-check': ['D2-policy-'],
      'writeoff-check': ['D2-writeoff-'],
      'bizmodel-check': ['D2-bizmodel-'],
      'disclosure': ['D2-disc-'],
      'ecl-calculation': ['D2-ecl9-'],
      'ecl-measurement': ['D2-ecl10-'],
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
    for (const tab of TAB_NAMES) {
      if (!statusMap.has(tab)) statusMap.set(tab, 'not-started')
    }
    return statusMap
  })

  /** 联动面板引用（5 ref_chips） */
  const linkageRefs: ComputedRef<LinkageRef[]> = computed(() => [
    { label: '试算平衡表', targetWpCode: 'trial_balance', icon: '📊' },
    { label: 'D0 函证', targetWpCode: 'D0', icon: '📮' },
    { label: 'B50 风险评估', targetWpCode: 'B50', icon: '⚠️' },
    { label: 'C3 控制测试', targetWpCode: 'C3', icon: '🔒' },
    { label: 'A13 错报汇总', targetWpCode: 'A13', icon: '📋' },
  ])

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.2: 审定表 D2-1 SUMIF 联动计算逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  const d22RawData = ref<Array<{ AI: string; S: number; Z: number; AA: number }>>([])

  /** SUMIF 聚合值（从 D2-2 按分类聚合） */
  const sumifValues: ComputedRef<SumifAggregation> = computed(() => {
    const rows = d22RawData.value
    return {
      individual_prior: sumif(rows, '单项计提', 'S'),
      individual_change: sumif(rows, '单项计提', 'Z'),
      individual_end: sumif(rows, '单项计提', 'AA'),
      agingCombo_prior: sumif(rows, '账龄组合', 'S'),
      agingCombo_change: sumif(rows, '账龄组合', 'Z'),
      agingCombo_end: sumif(rows, '账龄组合', 'AA'),
      customerCombo_prior: sumif(rows, '客户类型组合', 'S'),
      customerCombo_change: sumif(rows, '客户类型组合', 'Z'),
      customerCombo_end: sumif(rows, '客户类型组合', 'AA'),
    }
  })

  /** 刷新 D2-2 SUMIF 源数据 */
  async function refreshSumifData(): Promise<void> {
    if (!loadSubWorkpaperData) return
    try {
      const raw = await loadSubWorkpaperData('D2-2')
      // Parse raw into structured rows
      const rows: Array<{ AI: string; S: number; Z: number; AA: number }> = []
      // Group by row index from item_ids like D2-2-row-{n}-AI, D2-2-row-{n}-S etc.
      const rowMap = new Map<string, { AI: string; S: number; Z: number; AA: number }>()
      for (const [key, value] of Object.entries(raw)) {
        const match = key.match(/^row-(\d+)-(.+)$/)
        if (match) {
          const rowIdx = match[1]
          const col = match[2]
          if (!rowMap.has(rowIdx)) rowMap.set(rowIdx, { AI: '', S: 0, Z: 0, AA: 0 })
          const row = rowMap.get(rowIdx)!
          if (col === 'AI') row.AI = String(value)
          else if (col === 'S') row.S = parseNum(value)
          else if (col === 'Z') row.Z = parseNum(value)
          else if (col === 'AA') row.AA = parseNum(value)
        }
      }
      d22RawData.value = Array.from(rowMap.values())
    } catch { /* handled by useD2FormData */ }
  }

  /** 函证汇总信息 */
  const confirmationSummary = ref<ConfirmationSummary | null>(null)

  /** 审定表各行数据 */
  const adjudicationRows: ComputedRef<AdjudicationRow[]> = computed(() => {
    const sv = sumifValues.value
    return ADJUDICATION_ROWS_CONFIG.map(({ rowKey, label }) => {
      let priorUnadjusted: number
      let currentUnadjusted: number
      let sumifPrior = 0
      let sumifChange = 0
      let sumifEnd = 0

      if (rowKey === 'individual') {
        sumifPrior = sv.individual_prior
        sumifChange = sv.individual_change
        sumifEnd = sv.individual_end
        priorUnadjusted = sumifPrior || parseNum(getVal('D2-adj-individual-prior').remark)
        currentUnadjusted = sumifEnd || parseNum(getVal('D2-adj-individual-current').remark)
      } else if (rowKey === 'aging-combo') {
        sumifPrior = sv.agingCombo_prior
        sumifChange = sv.agingCombo_change
        sumifEnd = sv.agingCombo_end
        priorUnadjusted = sumifPrior || parseNum(getVal('D2-adj-aging-combo-prior').remark)
        currentUnadjusted = sumifEnd || parseNum(getVal('D2-adj-aging-combo-current').remark)
      } else if (rowKey === 'customer-combo') {
        sumifPrior = sv.customerCombo_prior
        sumifChange = sv.customerCombo_change
        sumifEnd = sv.customerCombo_end
        priorUnadjusted = sumifPrior || parseNum(getVal('D2-adj-customer-combo-prior').remark)
        currentUnadjusted = sumifEnd || parseNum(getVal('D2-adj-customer-combo-current').remark)
      } else if (rowKey === 'total') {
        // Total is sum of individual + aging-combo + customer-combo
        const rows = ADJUDICATION_ROWS_CONFIG.filter(r => ['individual', 'aging-combo', 'customer-combo'].includes(r.rowKey))
        priorUnadjusted = rows.reduce((s, r) => {
          if (r.rowKey === 'individual') return s + (sv.individual_prior || parseNum(getVal('D2-adj-individual-prior').remark))
          if (r.rowKey === 'aging-combo') return s + (sv.agingCombo_prior || parseNum(getVal('D2-adj-aging-combo-prior').remark))
          if (r.rowKey === 'customer-combo') return s + (sv.customerCombo_prior || parseNum(getVal('D2-adj-customer-combo-prior').remark))
          return s
        }, 0)
        currentUnadjusted = rows.reduce((s, r) => {
          if (r.rowKey === 'individual') return s + (sv.individual_end || parseNum(getVal('D2-adj-individual-current').remark))
          if (r.rowKey === 'aging-combo') return s + (sv.agingCombo_end || parseNum(getVal('D2-adj-aging-combo-current').remark))
          if (r.rowKey === 'customer-combo') return s + (sv.customerCombo_end || parseNum(getVal('D2-adj-customer-combo-current').remark))
          return s
        }, 0)
      } else {
        priorUnadjusted = parseNum(getVal(`D2-adj-${rowKey}-prior`).remark)
        currentUnadjusted = parseNum(getVal(`D2-adj-${rowKey}-current`).remark)
      }

      const ajeAdjustment = parseNum(getVal(`D2-adj-${rowKey}-aje`).remark)
      const rjeAdjustment = parseNum(getVal(`D2-adj-${rowKey}-rje`).remark)
      const audited = getAuditedAmount(currentUnadjusted, ajeAdjustment, rjeAdjustment)
      const rate = getChangeRate(priorUnadjusted, audited)
      const isFromSumif = ['individual', 'aging-combo', 'customer-combo'].includes(rowKey)

      return {
        rowKey,
        label,
        priorUnadjusted,
        currentUnadjusted,
        sumifPrior,
        sumifChange,
        sumifEnd,
        ajeAdjustment,
        rjeAdjustment,
        auditedAmount: audited,
        changeRate: rate,
        isFromSumif,
      }
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.3: 程序表 D2A 逻辑（7步）
  // ═══════════════════════════════════════════════════════════════════════════

  const riskIndicators = ref<Map<number, RiskIndicator>>(new Map())
  const overallConclusion = ref<string>(getVal('D2-proc-overall').remark || '')

  const procedureSteps: ComputedRef<ProcedureStep[]> = computed(() => {
    return PROCEDURE_STEPS_CONFIG.map((cfg, idx) => {
      const n = idx + 1
      return {
        stepOrder: n,
        stepName: cfg.stepName,
        description: cfg.description,
        status: (getVal(`D2-proc-${n}-status`).conclusion as ProcedureStatus) || '未开始',
        executor: getVal(`D2-proc-${n}-executor`).remark || '',
        executeDate: getVal(`D2-proc-${n}-date`).remark || '',
        wpIndexRef: getVal(`D2-proc-${n}-wpindex`).remark || '',
        findings: getVal(`D2-proc-${n}-findings`).remark || '',
        conclusion: getVal(`D2-proc-${n}-conclusion`).remark || '',
        isRequired: cfg.isRequired,
        relatedTab: cfg.relatedTab,
      }
    })
  })

  function setProcedureStatus(stepIndex: number, status: ProcedureStatus): void {
    const n = stepIndex + 1
    const item = setLocal(`D2-proc-${n}-status`, status)
    saveImmediate([item])
  }

  function setProcedureConclusion(stepIndex: number, conclusion: string): void {
    const n = stepIndex + 1
    const item = setLocal(`D2-proc-${n}-conclusion`, null, conclusion)
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

  const badDebtMethod: ComputedRef<BadDebtMethod> = computed(() => {
    return (getVal('D2-baddebt-method').conclusion as BadDebtMethod) || '账龄组合'
  })

  function setBadDebtMethod(method: BadDebtMethod): void {
    const item = setLocal('D2-baddebt-method', method)
    saveImmediate([item])
  }

  const agingBands: ComputedRef<AgingBand[]> = computed(() => {
    return AGING_BANDS_CONFIG.map(({ bandKey, label }) => {
      const endBalance = parseNum(getVal(`D2-ecl-${bandKey}-balance`).remark)
      const rateVal = parseNum(getVal(`D2-ecl-${bandKey}-rate`).remark) / 100
      const expectedLossRate = Math.max(0, Math.min(1, rateVal))
      const shouldProvision = calculateProvision(endBalance, expectedLossRate)
      const actualProvision = parseNum(getVal(`D2-ecl-${bandKey}-actual`).remark)
      const difference = calculateDifference(actualProvision, shouldProvision)

      return {
        bandKey,
        label,
        priorBalance: parseNum(getVal(`D2-ecl-${bandKey}-prior`).remark),
        currentProvision: parseNum(getVal(`D2-ecl-${bandKey}-provision`).remark),
        currentReversal: parseNum(getVal(`D2-ecl-${bandKey}-reversal`).remark),
        currentWriteOff: parseNum(getVal(`D2-ecl-${bandKey}-writeoff`).remark),
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
      const y1 = parseNum(getVal(`D2-ecl-migration-${from}-${to}-y1`).remark) / 100
      const y2 = parseNum(getVal(`D2-ecl-migration-${from}-${to}-y2`).remark) / 100
      const y3 = parseNum(getVal(`D2-ecl-migration-${from}-${to}-y3`).remark) / 100
      const avg = (y1 + y2 + y3) / 3
      rows.push({ fromBand: from, toBand: to, year1Rate: y1, year2Rate: y2, year3Rate: y3, averageRate: avg })
    }
    return rows
  })

  const eclSummary: ComputedRef<EclSummary> = computed(() => {
    const bands = agingBands.value
    const totalEndBalance = bands.reduce((s, b) => s + b.endBalance, 0)
    const totalShouldProvision = bands.reduce((s, b) => s + b.shouldProvision, 0)
    const totalActualProvision = bands.reduce((s, b) => s + b.actualProvision, 0)
    const totalDifference = totalActualProvision - totalShouldProvision
    const materiality = parseNum(getVal('D2-ecl-materiality').remark)
    const exceedsMateriality = materiality > 0 && Math.abs(totalDifference) > materiality
    return { totalEndBalance, totalShouldProvision, totalActualProvision, totalDifference, exceedsMateriality }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.5: 截止测试逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  function getCutoffCount(): number {
    return parseNum(getVal('D2-cutoff-count').remark) || 0
  }

  const cutoffTestSamples: ComputedRef<CutoffTestSample[]> = computed(() => {
    const count = getCutoffCount()
    const bsDate = `${year.value}-12-31`
    const items: CutoffTestSample[] = []
    for (let i = 1; i <= count; i++) {
      const revenueDate = getVal(`D2-cutoff-${i}-revDate`).remark || ''
      const isCutoff = revenueDate ? determineCutoff(revenueDate, bsDate) : false
      items.push({
        index: i,
        invoiceNo: getVal(`D2-cutoff-${i}-invoiceNo`).remark || '',
        revenueDate,
        arBookingDate: getVal(`D2-cutoff-${i}-arDate`).remark || '',
        amount: parseNum(getVal(`D2-cutoff-${i}-amount`).remark),
        isCutoffError: isCutoff,
        conclusion: isCutoff ? '跨期' : '未跨期',
        remark: getVal(`D2-cutoff-${i}-remark`).remark || '',
      })
    }
    return items
  })

  function addCutoffSample(sample: Partial<CutoffTestSample>): void {
    const count = getCutoffCount()
    const n = count + 1
    const items: ChecklistItem[] = [setLocal('D2-cutoff-count', null, String(n))]
    if (sample.invoiceNo) items.push(setLocal(`D2-cutoff-${n}-invoiceNo`, null, sample.invoiceNo))
    if (sample.revenueDate) items.push(setLocal(`D2-cutoff-${n}-revDate`, null, sample.revenueDate))
    if (sample.arBookingDate) items.push(setLocal(`D2-cutoff-${n}-arDate`, null, sample.arBookingDate))
    if (sample.amount !== undefined) items.push(setLocal(`D2-cutoff-${n}-amount`, null, String(sample.amount)))
    if (sample.remark) items.push(setLocal(`D2-cutoff-${n}-remark`, null, sample.remark))
    saveImmediate(items)
  }

  function removeCutoffSample(index: number): void {
    const count = getCutoffCount()
    if (index < 1 || index > count) return
    const items: ChecklistItem[] = []
    const fields = ['invoiceNo', 'revDate', 'arDate', 'amount', 'remark']
    for (let i = index; i < count; i++) {
      for (const f of fields) {
        const src = getVal(`D2-cutoff-${i + 1}-${f}`)
        items.push(setLocal(`D2-cutoff-${i}-${f}`, src.conclusion, src.remark))
      }
    }
    for (const f of fields) {
      items.push(setLocal(`D2-cutoff-${count}-${f}`, null, null))
    }
    items.push(setLocal('D2-cutoff-count', null, String(count - 1)))
    saveImmediate(items)
  }

  function updateCutoffSample(index: number, data: Partial<CutoffTestSample>): void {
    const count = getCutoffCount()
    if (index < 1 || index > count) return
    const items: ChecklistItem[] = []
    if (data.invoiceNo !== undefined) items.push(setLocal(`D2-cutoff-${index}-invoiceNo`, null, data.invoiceNo))
    if (data.revenueDate !== undefined) items.push(setLocal(`D2-cutoff-${index}-revDate`, null, data.revenueDate))
    if (data.arBookingDate !== undefined) items.push(setLocal(`D2-cutoff-${index}-arDate`, null, data.arBookingDate))
    if (data.amount !== undefined) items.push(setLocal(`D2-cutoff-${index}-amount`, null, String(data.amount)))
    if (data.remark !== undefined) items.push(setLocal(`D2-cutoff-${index}-remark`, null, data.remark))
    if (items.length > 0) saveImmediate(items)
  }

  const hasCutoffErrors: ComputedRef<boolean> = computed(() => {
    return cutoffTestSamples.value.some(s => s.isCutoffError)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.6: 保理分析逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  function getFactoringCount(): number {
    return parseNum(getVal('D2-factoring-count').remark) || 0
  }

  const factoringItems: ComputedRef<FactoringItem[]> = computed(() => {
    const count = getFactoringCount()
    const items: FactoringItem[] = []
    for (let i = 1; i <= count; i++) {
      items.push({
        index: i,
        category: (getVal(`D2-factoring-${i}-category`).conclusion as '质押' | '保理') || '保理',
        customerName: getVal(`D2-factoring-${i}-customer`).remark || '',
        amount: parseNum(getVal(`D2-factoring-${i}-amount`).remark),
        counterparty: getVal(`D2-factoring-${i}-counterparty`).remark || '',
        contractNo: getVal(`D2-factoring-${i}-contract`).remark || '',
        startDate: getVal(`D2-factoring-${i}-startDate`).remark || '',
        endDate: getVal(`D2-factoring-${i}-endDate`).remark || '',
        derecognition: (getVal(`D2-factoring-${i}-derecognition`).conclusion as DerecognitionResult | null) || null,
        transferRisk: getVal(`D2-factoring-${i}-transferRisk`).conclusion === '是' ? true : getVal(`D2-factoring-${i}-transferRisk`).conclusion === '否' ? false : null,
        retainControl: getVal(`D2-factoring-${i}-retainControl`).conclusion === '是' ? true : getVal(`D2-factoring-${i}-retainControl`).conclusion === '否' ? false : null,
        remark: getVal(`D2-factoring-${i}-remark`).remark || '',
      })
    }
    return items
  })

  function addFactoring(item: Partial<FactoringItem>): void {
    const count = getFactoringCount()
    if (count >= 100) return
    const n = count + 1
    const items: ChecklistItem[] = [setLocal('D2-factoring-count', null, String(n))]
    if (item.category) items.push(setLocal(`D2-factoring-${n}-category`, item.category))
    if (item.customerName) items.push(setLocal(`D2-factoring-${n}-customer`, null, item.customerName))
    if (item.amount !== undefined) items.push(setLocal(`D2-factoring-${n}-amount`, null, String(item.amount)))
    if (item.counterparty) items.push(setLocal(`D2-factoring-${n}-counterparty`, null, item.counterparty))
    if (item.contractNo) items.push(setLocal(`D2-factoring-${n}-contract`, null, item.contractNo))
    if (item.startDate) items.push(setLocal(`D2-factoring-${n}-startDate`, null, item.startDate))
    if (item.endDate) items.push(setLocal(`D2-factoring-${n}-endDate`, null, item.endDate))
    if (item.derecognition) items.push(setLocal(`D2-factoring-${n}-derecognition`, item.derecognition))
    if (item.remark) items.push(setLocal(`D2-factoring-${n}-remark`, null, item.remark))
    saveImmediate(items)
  }

  function removeFactoring(index: number): void {
    const count = getFactoringCount()
    if (index < 1 || index > count) return
    const items: ChecklistItem[] = []
    const fields = ['category', 'customer', 'amount', 'counterparty', 'contract', 'startDate', 'endDate', 'derecognition', 'transferRisk', 'retainControl', 'remark']
    for (let i = index; i < count; i++) {
      for (const f of fields) {
        const src = getVal(`D2-factoring-${i + 1}-${f}`)
        items.push(setLocal(`D2-factoring-${i}-${f}`, src.conclusion, src.remark))
      }
    }
    for (const f of fields) {
      items.push(setLocal(`D2-factoring-${count}-${f}`, null, null))
    }
    items.push(setLocal('D2-factoring-count', null, String(count - 1)))
    saveImmediate(items)
  }

  function updateFactoring(index: number, data: Partial<FactoringItem>): void {
    const count = getFactoringCount()
    if (index < 1 || index > count) return
    const items: ChecklistItem[] = []
    if (data.category !== undefined) items.push(setLocal(`D2-factoring-${index}-category`, data.category))
    if (data.customerName !== undefined) items.push(setLocal(`D2-factoring-${index}-customer`, null, data.customerName))
    if (data.amount !== undefined) items.push(setLocal(`D2-factoring-${index}-amount`, null, String(data.amount)))
    if (data.counterparty !== undefined) items.push(setLocal(`D2-factoring-${index}-counterparty`, null, data.counterparty))
    if (data.contractNo !== undefined) items.push(setLocal(`D2-factoring-${index}-contract`, null, data.contractNo))
    if (data.startDate !== undefined) items.push(setLocal(`D2-factoring-${index}-startDate`, null, data.startDate))
    if (data.endDate !== undefined) items.push(setLocal(`D2-factoring-${index}-endDate`, null, data.endDate))
    if (data.derecognition !== undefined) items.push(setLocal(`D2-factoring-${index}-derecognition`, data.derecognition))
    if (data.transferRisk !== undefined) items.push(setLocal(`D2-factoring-${index}-transferRisk`, data.transferRisk === true ? '是' : data.transferRisk === false ? '否' : null))
    if (data.retainControl !== undefined) items.push(setLocal(`D2-factoring-${index}-retainControl`, data.retainControl === true ? '是' : data.retainControl === false ? '否' : null))
    if (data.remark !== undefined) items.push(setLocal(`D2-factoring-${index}-remark`, null, data.remark))
    if (items.length > 0) saveImmediate(items)
  }

  /** 终止确认判断辅助（CAS 23） */
  function factoringDerecognitionJudge(transferRisk: boolean, retainControl: boolean): DerecognitionResult {
    if (transferRisk) return '终止确认'
    if (!transferRisk && !retainControl) return '终止确认'
    return '不终止确认'
  }

  const factoringSummary: ComputedRef<FactoringSummary> = computed(() => {
    const items = factoringItems.value
    const pledgedTotal = items.filter(i => i.category === '质押').reduce((s, i) => s + i.amount, 0)
    const factoredTotal = items.filter(i => i.category === '保理').reduce((s, i) => s + i.amount, 0)
    const derecognizedAmount = items.filter(i => i.derecognition === '终止确认').reduce((s, i) => s + i.amount, 0)
    const notDerecognizedAmount = items.filter(i => i.derecognition === '不终止确认').reduce((s, i) => s + i.amount, 0)
    const totalRow = adjudicationRows.value.find(r => r.rowKey === 'total')
    const totalAR = totalRow?.auditedAmount || 0
    const ratio = calculatePledgeRatio(pledgedTotal, totalAR)
    return { pledgedTotal, factoredTotal, derecognizedAmount, notDerecognizedAmount, pledgeRatio: ratio }
  })

  const pledgeRatio: ComputedRef<number> = computed(() => factoringSummary.value.pledgeRatio)
  const isPledgeRatioWarning: ComputedRef<boolean> = computed(() => pledgeRatio.value > 0.5)

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.7: 函证联动逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  function onConfirmationCompleted(payload: { sentCount: number; receivedCount: number; responseRate: number; confirmedAmount: number; differenceAmount: number }): void {
    confirmationSummary.value = {
      sentCount: payload.sentCount,
      receivedCount: payload.receivedCount,
      responseRate: payload.responseRate,
      confirmedAmount: payload.confirmedAmount,
      differenceAmount: payload.differenceAmount,
    }
    // Persist summary as JSON
    const item = setLocal('D2-confirm-summary', null, JSON.stringify(confirmationSummary.value))
    saveImmediate([item])
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.8: 分析程序逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  const analysisRatios: ComputedRef<AnalysisRatios> = computed(() => {
    const turnoverRate = parseNum(getVal('D2-analysis-turnoverRate').remark)
    const turnoverDays = parseNum(getVal('D2-analysis-turnoverDays').remark)
    const priorTurnoverDays = parseNum(getVal('D2-analysis-priorTurnoverDays').remark)
    const badDebtRate = parseNum(getVal('D2-analysis-badDebtRate').remark)
    const priorBadDebtRate = parseNum(getVal('D2-analysis-priorBadDebtRate').remark)
    const turnoverDaysChangeRate = priorTurnoverDays > 0
      ? Math.abs(turnoverDays - priorTurnoverDays) / priorTurnoverDays
      : 0
    return { turnoverRate, turnoverDays, priorTurnoverDays, turnoverDaysChangeRate, badDebtRate, priorBadDebtRate }
  })

  const isTurnoverDaysWarning: ComputedRef<boolean> = computed(() => {
    return analysisRatios.value.turnoverDaysChangeRate > 0.3
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.9: 关联方检查逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  const matchedRelatedParties: ComputedRef<string[]> = computed(() => {
    // From project related party list (stored as D2-rp-{n}-name)
    const count = parseNum(getVal('D2-rp-count').remark) || 0
    const rpNames: string[] = []
    for (let i = 1; i <= count; i++) {
      const name = getVal(`D2-rp-${i}-name`).remark
      if (name) rpNames.push(name)
    }
    return rpNames
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.10: 附注披露逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  const disclosureTemplate: ComputedRef<'listed' | 'soe' | 'general'> = computed(() => {
    const val = getVal('D2-disc-template').conclusion
    if (val === 'listed' || val === 'soe' || val === 'general') return val
    return 'general'
  })

  function setDisclosureTemplate(template: 'listed' | 'soe' | 'general'): void {
    const item = setLocal('D2-disc-template', template)
    saveImmediate([item])
  }

  const LISTED_DISCLOSURE_ITEMS = [
    '应收账款分类及账面价值',
    '坏账准备变动（三方式）',
    '已质押应收账款',
    '已保理应收账款',
    '前五名客户应收账款',
    '关联方应收账款',
    '账龄分析',
    '期后回款情况',
    '会计政策说明',
  ]

  const SOE_DISCLOSURE_ITEMS = [
    '应收账款基本情况',
    '坏账准备计提情况',
    '重大单项计提明细',
    '已保理/已质押情况',
    '受限资产情况',
    '关联方应收交易',
  ]

  const disclosureItems: ComputedRef<DisclosureCheckItem[]> = computed(() => {
    const template = disclosureTemplate.value
    const checkItems = template === 'soe' ? SOE_DISCLOSURE_ITEMS : LISTED_DISCLOSURE_ITEMS
    const prefix = template === 'soe' ? 'D2-disc-soe' : 'D2-disc-listed'
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
  // Task 3.11: 调整分录逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  function getAdjustmentCount(): number {
    return parseNum(getVal('D2-entry-count').remark) || 0
  }

  const adjustmentEntries: ComputedRef<AdjustmentEntry[]> = computed(() => {
    const count = getAdjustmentCount()
    const entries: AdjustmentEntry[] = []
    for (let i = 1; i <= count; i++) {
      entries.push({
        index: i,
        type: (getVal(`D2-entry-${i}-type`).conclusion as AdjustmentType) || 'AJE',
        debitAccount: getVal(`D2-entry-${i}-debit`).remark || '',
        creditAccount: getVal(`D2-entry-${i}-credit`).remark || '',
        amount: parseNum(getVal(`D2-entry-${i}-amount`).remark),
        description: getVal(`D2-entry-${i}-desc`).remark || '',
        isPushedToAdjTable: getVal(`D2-entry-${i}-pushed`).conclusion === 'Y',
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
    const items: ChecklistItem[] = [setLocal('D2-entry-count', null, String(n))]
    const entryType = entry.type || 'AJE'
    items.push(setLocal(`D2-entry-${n}-type`, entryType))
    if (entry.debitAccount) items.push(setLocal(`D2-entry-${n}-debit`, null, entry.debitAccount))
    if (entry.creditAccount) items.push(setLocal(`D2-entry-${n}-credit`, null, entry.creditAccount))
    if (entry.amount !== undefined) items.push(setLocal(`D2-entry-${n}-amount`, null, String(entry.amount)))
    if (entry.description) items.push(setLocal(`D2-entry-${n}-desc`, null, entry.description))
    saveImmediate(items)

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
        const src = getVal(`D2-entry-${i + 1}-${f}`)
        items.push(setLocal(`D2-entry-${i}-${f}`, src.conclusion, src.remark))
      }
    }
    for (const f of fields) {
      items.push(setLocal(`D2-entry-${count}-${f}`, null, null))
    }
    items.push(setLocal('D2-entry-count', null, String(count - 1)))
    saveImmediate(items)
  }

  function updateAdjustment(index: number, data: Partial<AdjustmentEntry>): void {
    const count = getAdjustmentCount()
    if (index < 1 || index > count) return
    const items: ChecklistItem[] = []
    if (data.type !== undefined) items.push(setLocal(`D2-entry-${index}-type`, data.type))
    if (data.debitAccount !== undefined) items.push(setLocal(`D2-entry-${index}-debit`, null, data.debitAccount))
    if (data.creditAccount !== undefined) items.push(setLocal(`D2-entry-${index}-credit`, null, data.creditAccount))
    if (data.amount !== undefined) items.push(setLocal(`D2-entry-${index}-amount`, null, String(data.amount)))
    if (data.description !== undefined) items.push(setLocal(`D2-entry-${index}-desc`, null, data.description))
    if (data.isPushedToAdjTable !== undefined) items.push(setLocal(`D2-entry-${index}-pushed`, data.isPushedToAdjTable ? 'Y' : null))
    if (items.length > 0) saveImmediate(items)
  }

  // Bidirectional sync: adjustment totals → adjudication AJE/RJE columns
  watch([ajeTotal, rjeTotal], ([newAje, newRje]) => {
    setLocal('D2-adj-total-aje', null, String(newAje))
    setLocal('D2-adj-total-rje', null, String(newRje))
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.12: EventBus 联动
  // ═══════════════════════════════════════════════════════════════════════════

  let previousAuditedAmount: number | null = null
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  /** 发布 substantive:adjudicated */
  function publishAdjudicated(accountCode: string, auditedAmount: number, priorAmount: number, changeRate: number | null): void {
    const payload: SubstantiveAdjudicatedPayload = {
      wpCode: 'D2',
      accountCode,
      auditedAmount,
      priorAmount,
      changeRate,
    }
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', { detail: payload }))
    } catch {
      console.warn('[D2AccountsReceivable] EventBus publish substantive:adjudicated failed')
    }
  }

  /** 发布 adjustment:created */
  function publishAdjustmentCreated(entry: AdjustmentEntry): void {
    const payload: AdjustmentCreatedPayload = {
      wpCode: 'D2',
      entryType: entry.type,
      debitAccount: entry.debitAccount,
      creditAccount: entry.creditAccount,
      amount: entry.amount,
      description: entry.description,
    }
    try {
      window.dispatchEvent(new CustomEvent('adjustment:created', { detail: payload }))
    } catch {
      console.warn('[D2AccountsReceivable] EventBus publish adjustment:created failed')
    }
  }

  // Watch audited amount changes to publish event
  watch(adjudicationRows, (rows) => {
    const totalRow = rows.find(r => r.rowKey === 'book-value')
    if (!totalRow) return
    const current = totalRow.auditedAmount
    if (previousAuditedAmount !== null && previousAuditedAmount !== current) {
      const rate = totalRow.changeRate
      publishAdjudicated(
        '1122',
        current,
        totalRow.priorUnadjusted,
        typeof rate === 'number' ? rate : null
      )
    }
    previousAuditedAmount = current
  }, { deep: true })

  /** 监听 risk:assessed（B50 → riskIndicators） */
  function onRiskAssessed(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (!detail) return
    if (detail.stepIndex !== undefined && detail.level) {
      riskIndicators.value.set(detail.stepIndex, {
        level: detail.level,
        description: detail.description || '',
      })
    }
  }

  /** 监听 control:test-concluded（C3 → 程序表提示） */
  function onControlTestConcluded(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (!detail || detail.wpCode !== 'C3') return
    const hintKey = 'D2-proc-control-hint'
    setLocal(hintKey, null, detail.conclusion || '')
  }

  /** 监听 confirmation:completed（D0 → 函证汇总） */
  function onConfirmationEvent(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (!detail) return
    onConfirmationCompleted(detail)
  }

  function registerEventListeners(): void {
    const riskHandler = (e: Event) => onRiskAssessed(e)
    const controlHandler = (e: Event) => onControlTestConcluded(e)
    const confirmHandler = (e: Event) => onConfirmationEvent(e)

    window.addEventListener('risk:assessed', riskHandler)
    window.addEventListener('control:test-concluded', controlHandler)
    window.addEventListener('confirmation:completed', confirmHandler)

    eventListeners.push(
      { event: 'risk:assessed', handler: riskHandler },
      { event: 'control:test-concluded', handler: controlHandler },
      { event: 'confirmation:completed', handler: confirmHandler },
    )
  }

  function unregisterEventListeners(): void {
    for (const { event, handler } of eventListeners) {
      window.removeEventListener(event, handler)
    }
    eventListeners.length = 0
  }

  registerEventListeners()

  onBeforeUnmount(() => {
    unregisterEventListeners()
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.13: 检查表通用逻辑（D2-7/D2-8/D2-11/D2-13）
  // ═══════════════════════════════════════════════════════════════════════════

  // Handled via getVal/setFieldImmediate in the Vue component directly
  // (same pattern as D1 check rows — simple conclusion select + remark input)

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.14: 截止测试日期校验与边界处理
  // ═══════════════════════════════════════════════════════════════════════════

  // determineCutoff already exported as pure function above
  // bsDate derived from year prop: `${year.value}-12-31`

  // ═══════════════════════════════════════════════════════════════════════════
  // Return
  // ═══════════════════════════════════════════════════════════════════════════

  // Suppress unused param warnings
  void wpId
  void projectId
  void externalReadonly

  return {
    // Task 3.1: Tab 管理
    activeTab,
    setActiveTab,
    tabCompletionStatus,
    linkageRefs,

    // Task 3.2: 审定表 D2-1 SUMIF
    adjudicationRows,
    sumifValues,
    refreshSumifData,
    confirmationSummary,

    // Task 3.3: 程序表 D2A
    procedureSteps,
    setProcedureStatus,
    setProcedureConclusion,
    procedureProgress,
    canInputOverallConclusion,
    overallConclusion,
    riskIndicators,

    // Task 3.4: ECL 坏账准备
    badDebtMethod,
    setBadDebtMethod,
    agingBands,
    migrationRateMatrix,
    eclSummary,

    // Task 3.5: 截止测试
    cutoffTestSamples,
    addCutoffSample,
    removeCutoffSample,
    updateCutoffSample,
    hasCutoffErrors,

    // Task 3.6: 保理分析
    factoringItems,
    addFactoring,
    removeFactoring,
    updateFactoring,
    factoringDerecognitionJudge,
    factoringSummary,
    pledgeRatio,
    isPledgeRatioWarning,

    // Task 3.7: 函证联动
    onConfirmationCompleted,

    // Task 3.8: 分析程序
    analysisRatios,
    isTurnoverDaysWarning,

    // Task 3.9: 关联方
    matchedRelatedParties,

    // Task 3.10: 附注披露
    disclosureTemplate,
    setDisclosureTemplate,
    disclosureItems,
    hasUndisclosedItems,

    // Task 3.11: 调整分录
    adjustmentEntries,
    addAdjustment,
    removeAdjustment,
    updateAdjustment,
    ajeTotal,
    rjeTotal,

    // Task 3.12: EventBus
    publishAdjudicated,
    publishAdjustmentCreated,
    unregisterEventListeners,
  }
}

export default useD2AccountsReceivable
