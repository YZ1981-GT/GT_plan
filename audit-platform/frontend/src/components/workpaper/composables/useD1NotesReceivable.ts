/**
 * useD1NotesReceivable — D1 应收票据核心逻辑 composable
 *
 * Spec: .kiro/specs/d1-notes-receivable/
 * Tasks: 3.1 ~ 3.13
 *
 * 职责（拆分后保留）：
 * - Tab 管理 + localStorage 持久化
 * - 程序表 D1A 状态/结论/进度
 * - 附注披露
 * - 调整分录 CRUD + 审定表同步
 * - EventBus 联动（发布 + 监听 + 卸载注销）
 *
 * 已拆出至独立 composable：
 * - 审定表 D1-1 → useD1Adjudication.ts
 * - 原值明细 D1-2 → useD1DetailCategory.ts
 * - 原值明细 D1-3 → useD1DetailCustomer.ts
 * - 坏账准备 D1-4 → useD1BadDebt.ts
 * - 业务模式 D1-6 → useD1BusinessMode.ts
 * - 备查簿 D1-7 → useD1MemoReconciliation.ts
 * - 背书贴现 D1-8 → useD1EndorsementDetail.ts
 * - 贴息 D1-9 → useD1InterestCheck.ts
 * - 监盘 D1-10 → useD1InventoryCount.ts
 * - 关联方 D1-11 → useD1RelatedPartyCheck.ts
 * - 质押 D1-12 → useD1PledgeCheck.ts
 * - 抽样凭证核对 D1-13 → useD1SamplingVouching.ts
 * - ECL测算 D1-14/D1-15 → useD1EclCalc.ts
 * - 政策检查 D1-14 → useD1PolicyCheck.ts
 * - 共享纯函数 → useD1FormulaEngine.ts
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type ProcedureStatus = '未开始' | '执行中' | '已完成' | '不适用'
export type BusinessModelType =
  | '以摊余成本计量'
  | '以公允价值计量且变动计入其他综合收益'
  | '以公允价值计量且变动计入当期损益'
export type DerecognitionResult = '终止确认' | '不终止确认'
export type DisclosureConclusion = '已披露且准确' | '已披露但需修改' | '未披露需补充' | '不适用'
export type CheckConclusion = '符合' | '不符合' | '不适用'
export type TabStatus = 'completed' | 'in-progress' | 'not-started'
export type AdjustmentType = 'AJE' | 'RJE'

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

/** @deprecated Use InventoryCountRow from d1InspectionFormulas.ts instead */
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

/** @deprecated Use PledgeRow from d1InspectionFormulas.ts instead */
export interface PledgeItem {
  index: number
  noteNo: string
  amount: number
  pledgee: string
  purpose: string
  releaseDate: string
  isRestricted: boolean
}

/** @deprecated Use RelatedPartyRow from d1InspectionFormulas.ts instead */
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

/**
 * @deprecated 已迁移至 useD1Adjudication.ts，此处保留仅为向后兼容测试导入
 */
export const ADJUDICATION_ROWS_CONFIG: Array<{ rowKey: string; label: string }> = [
  { rowKey: 'bank-acceptance', label: '应收票据-银行承兑汇票' },
  { rowKey: 'commercial-acceptance', label: '应收票据-商业承兑汇票' },
  { rowKey: 'bad-debt', label: '坏账准备' },
  { rowKey: 'book-value', label: '账面价值' },
]

/**
 * @deprecated 已迁移至 useD1BadDebt.ts，此处保留仅为向后兼容测试导入
 */
export const AGING_BANDS_CONFIG: Array<{ bandKey: string; label: string }> = [
  { bandKey: 'not-overdue', label: '未逾期' },
  { bandKey: 'overdue-1-30', label: '逾期1-30天' },
  { bandKey: 'overdue-31-90', label: '逾期31-90天' },
  { bandKey: 'overdue-91-180', label: '逾期91-180天' },
  { bandKey: 'overdue-181-365', label: '逾期181-365天' },
  { bandKey: 'overdue-1year', label: '逾期1年以上' },
]

const LOCALSTORAGE_TAB_KEY = 'd1-notes-receivable-active-tab'

// ─── Pure Functions (exported for testing backward compatibility) ─────────────
// These have equivalents in useD1FormulaEngine.ts but are kept here for
// existing test imports. New code should use useD1FormulaEngine instead.

/**
 * @deprecated Use calcAuditedAmount from useD1FormulaEngine instead (3-param net version)
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
 * @deprecated Use calcChangeRate from useD1FormulaEngine instead
 */
export function getChangeRate(priorPeriod: number, auditedAmount: number): number | '' {
  if (priorPeriod === 0 && auditedAmount === 0) return ''
  if (priorPeriod === 0) return 1
  return (auditedAmount - priorPeriod) / priorPeriod
}

/**
 * @deprecated Use calcExpectedLossRate from useD1FormulaEngine instead
 */
export function calculateExpectedLossRate(migrationRates: number[]): number {
  if (migrationRates.length === 0) return 0
  return migrationRates.reduce((acc, rate) => acc * rate, 1)
}

/**
 * @deprecated Use calcProvision from useD1FormulaEngine instead
 */
export function calculateProvision(balance: number, lossRate: number): number {
  return balance * lossRate
}

/**
 * @deprecated Use calcDifference from useD1FormulaEngine instead
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
  // 背书贴现明细（D1-8 已迁移至 useD1EndorsementDetail）
  // 保留 endorsementItems / getEndorsementCount：关联方自动匹配(D1-11)依赖出票人清单
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

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.8: 监盘倒推逻辑 → 已迁移至 useD1InventoryCount.ts
  // ═══════════════════════════════════════════════════════════════════════════

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.9: 质押检查逻辑 → 已迁移至 useD1PledgeCheck.ts
  // ═══════════════════════════════════════════════════════════════════════════

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.10: 关联方检查逻辑 → 已迁移至 useD1RelatedPartyCheck.ts
  // ═══════════════════════════════════════════════════════════════════════════

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.11: 附注披露逻辑
  // ═══════════════════════════════════════════════════════════════════════════

  const disclosureTemplate: ComputedRef<'listed' | 'soe' | 'general'> = computed(() => {
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

  // Bidirectional sync: adjustment totals → adjudication table AJE/RJE columns
  watch([ajeTotal, rjeTotal], ([newAje, newRje]) => {
    // Sync AJE/RJE totals into bank-acceptance row (primary substantive account)
    setLocal('D1-adj-bank-acceptance-aje-dr', null, String(newAje))
    setLocal('D1-adj-bank-acceptance-rje-dr', null, String(newRje))
    // Don't call saveImmediate here to avoid circular save loops;
    // useD1Adjudication's computed will re-derive from allResponses reactively.
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Task 3.13: EventBus 联动
  // ═══════════════════════════════════════════════════════════════════════════

  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

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

  /** 监听 control:test-concluded（C2 → 程序表提示） */
  function onControlTestConcluded(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (!detail || detail.wpCode !== 'C2') return
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

    // Task 3.3: 程序表 D1A
    procedureSteps,
    setProcedureStatus,
    setProcedureConclusion,
    procedureProgress,
    canInputOverallConclusion,
    overallConclusion,
    riskIndicators,

    // 背书贴现明细（D1-8 已迁移，保留 endorsementItems 供关联方匹配 D1-11 使用）
    endorsementItems,

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
    publishAdjustmentCreated,
    unregisterEventListeners,
  }
}

export default useD1NotesReceivable
