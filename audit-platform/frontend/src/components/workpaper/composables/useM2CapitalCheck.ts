/**
 * useM2CapitalCheck — M2-5 检查表（验资核对）composable
 *
 * Spec: .kiro/specs/m2-paid-in-capital/
 * Task: 3.4
 * Requirements: 5.1-5.5
 *
 * 职责：
 * - 验资核对行：出资人 | 认缴出资 | 实缴出资 | 验资金额 | 差异 | 验资机构
 * - 计算 verifyDiff（calcVerifyDiff）
 * - 计算 paidInRate（calcPaidInRate）
 * - 差异阈值高亮（红色|验资差异>阈值 / 黄色|出资到位率<100%）
 * - 核对清单项 + 审计结论区（el-card包裹）
 * - AI辅助 section
 *
 * 科目：4001 实收资本/股本
 * 验资是实收资本核心审计程序——确认出资真实性（存在+准确性认定）
 */
import { computed, ref, watch, type ComputedRef } from 'vue'
import { calcVerifyDiff, calcPaidInRate } from './useM2VerifyEngine'
import { calcSubtotal } from './useM2FormulaEngine'
import type { useM2FormData } from './useM2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 验资核对行 */
export interface M2VerifyRow {
  /** 行唯一标识 */
  key: string
  /** 序号 */
  seq: number
  /** 出资人名称 */
  investorName: string
  /** 认缴出资额 */
  subscribedAmount: number
  /** 实缴出资额（账面记录） */
  paidAmount: number
  /** 验资金额（验资报告确认数） */
  verifiedAmount: number
  /** 验资差异（公式=实缴-验资） */
  verifyDiff: number
  /** 出资到位率（公式=实缴/认缴） */
  paidInRate: number
  /** 验资机构（会计师事务所名称） */
  verifyOrg: string
  /** 验资报告编号 */
  verifyReportNo: string
  /** 验资日期 */
  verifyDate: string
  /** 备注 */
  remark: string
}

/** 检查状态 */
export type CheckStatus = 'pending' | 'pass' | 'fail' | 'na'

/** 核对清单项 */
export interface M2CheckItem {
  /** 唯一标识 */
  id: string
  /** 检查项标题 */
  title: string
  /** 检查状态 */
  status: CheckStatus
  /** 检查说明/备注 */
  remark: string
  /** 是否支持AI辅助 */
  aiEnabled: boolean
}

/** AI辅助section */
export interface M2AiSection {
  /** section标识 */
  sectionId: string
  /** section标题 */
  title: string
  /** section内容 */
  content: string
  /** AI是否正在生成 */
  isGenerating: boolean
}

/** 审计结论 */
export interface M2AuditConclusion {
  /** 审计发现摘要 */
  findings: string
  /** 最终结论 */
  conclusion: string
  /** 结论日期 */
  conclusionDate: string
  /** 编制人 */
  preparedBy: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 验资差异阈值（绝对值超过此值红色高亮） */
export const VERIFY_DIFF_THRESHOLD = 100

/** 出资到位率预警阈值（低于此值黄色提示） */
export const PAID_IN_RATE_THRESHOLD = 1.0

/** 检查状态选项 */
export const CHECK_STATUS_OPTIONS: { value: CheckStatus; label: string; color: string }[] = [
  { value: 'pending', label: '待检查', color: '#909399' },
  { value: 'pass', label: '通过', color: '#67C23A' },
  { value: 'fail', label: '未通过', color: '#F56C6C' },
  { value: 'na', label: '不适用', color: '#E6A23C' },
]

/** 默认检查项清单 */
export const DEFAULT_CHECK_ITEMS: Omit<M2CheckItem, 'status' | 'remark'>[] = [
  { id: 'verify_existence', title: '验资报告真实性核查（原件查验）', aiEnabled: true },
  { id: 'verify_completeness', title: '出资人清单完整性核对（工商登记 vs 账面）', aiEnabled: true },
  { id: 'verify_accuracy', title: '验资金额准确性核对（验资报告 vs 账面实缴）', aiEnabled: true },
  { id: 'verify_timeliness', title: '出资到位时间检查（是否逾期）', aiEnabled: false },
  { id: 'verify_method', title: '非货币出资评估核查（实物/知识产权等）', aiEnabled: true },
  { id: 'verify_capital_reduction', title: '减资合规性检查（债权人公告等）', aiEnabled: true },
  { id: 'verify_registration', title: '工商变更登记核对', aiEnabled: false },
  { id: 'verify_disclosure', title: '实收资本披露充分性检查', aiEnabled: true },
]

/** AI辅助sections定义 */
export const AI_SECTIONS: Omit<M2AiSection, 'content' | 'isGenerating'>[] = [
  { sectionId: 'existence_analysis', title: '存在性分析' },
  { sectionId: 'accuracy_analysis', title: '准确性分析' },
  { sectionId: 'completeness_analysis', title: '完整性分析' },
  { sectionId: 'valuation_analysis', title: '非货币出资评估分析' },
  { sectionId: 'disclosure_analysis', title: '披露充分性分析' },
]

// ─── Storage Keys ────────────────────────────────────────────────────────────

const VERIFY_ROWS_KEY = 'M2-M2-5-verify-rows'
const CHECK_ITEMS_KEY = 'M2-M2-5-check-items'
const AI_SECTIONS_KEY = 'M2-M2-5-ai-sections'
const CONCLUSION_KEY = 'M2-M2-5-conclusion'

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M2-5 检查表（验资核对）业务逻辑
 *
 * @param formData 由调用方传入的 useM2FormData 实例
 */
export function useM2CapitalCheck(formData: ReturnType<typeof useM2FormData>) {
  const { debouncedSave, allResponses } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const verifyRows = ref<M2VerifyRow[]>(_loadVerifyRows())
  const checkItems = ref<M2CheckItem[]>(_loadCheckItems())
  const aiSections = ref<M2AiSection[]>(_loadAiSections())
  const conclusion = ref<M2AuditConclusion>(_loadConclusion())

  // ─── 2. 初始化加载 ────────────────────────────────────────────────────

  function _loadVerifyRows(): M2VerifyRow[] {
    const stored = allResponses.value.get(VERIFY_ROWS_KEY)?.conclusion
    if (stored) {
      try { return JSON.parse(stored) } catch { /* fallback */ }
    }
    return []
  }

  function _loadCheckItems(): M2CheckItem[] {
    const stored = allResponses.value.get(CHECK_ITEMS_KEY)?.conclusion
    if (stored) {
      try { return JSON.parse(stored) } catch { /* fallback */ }
    }
    return DEFAULT_CHECK_ITEMS.map(item => ({
      ...item,
      status: 'pending' as CheckStatus,
      remark: '',
    }))
  }

  function _loadAiSections(): M2AiSection[] {
    const stored = allResponses.value.get(AI_SECTIONS_KEY)?.conclusion
    if (stored) {
      try { return JSON.parse(stored) } catch { /* fallback */ }
    }
    return AI_SECTIONS.map(s => ({
      ...s,
      content: '',
      isGenerating: false,
    }))
  }

  function _loadConclusion(): M2AuditConclusion {
    const stored = allResponses.value.get(CONCLUSION_KEY)?.conclusion
    if (stored) {
      try { return JSON.parse(stored) } catch { /* fallback */ }
    }
    return { findings: '', conclusion: '', conclusionDate: '', preparedBy: '' }
  }

  // 异步加载完成后回填
  watch(
    () => allResponses.value.get(VERIFY_ROWS_KEY)?.conclusion,
    (raw) => { if (raw) { try { verifyRows.value = JSON.parse(raw) } catch { /* ignore */ } } },
  )
  watch(
    () => allResponses.value.get(CHECK_ITEMS_KEY)?.conclusion,
    (raw) => { if (raw) { try { checkItems.value = JSON.parse(raw) } catch { /* ignore */ } } },
  )
  watch(
    () => allResponses.value.get(AI_SECTIONS_KEY)?.conclusion,
    (raw) => { if (raw) { try { aiSections.value = JSON.parse(raw) } catch { /* ignore */ } } },
  )
  watch(
    () => allResponses.value.get(CONCLUSION_KEY)?.conclusion,
    (raw) => { if (raw) { try { conclusion.value = JSON.parse(raw) } catch { /* ignore */ } } },
  )

  // ─── 3. 验资核对行计算属性 ────────────────────────────────────────────

  /** 各行自动计算公式列 */
  const computedVerifyRows: ComputedRef<M2VerifyRow[]> = computed(() => {
    return verifyRows.value.map(row => {
      const verifyDiff = calcVerifyDiff(row.paidAmount, row.verifiedAmount)
      const paidInRate = calcPaidInRate(row.paidAmount, row.subscribedAmount)
      return { ...row, verifyDiff, paidInRate }
    })
  })

  /** 合计行 */
  const totalSubscribed: ComputedRef<number> = computed(() => {
    return calcSubtotal(verifyRows.value.map(r => r.subscribedAmount))
  })

  const totalPaid: ComputedRef<number> = computed(() => {
    return calcSubtotal(verifyRows.value.map(r => r.paidAmount))
  })

  const totalVerified: ComputedRef<number> = computed(() => {
    return calcSubtotal(verifyRows.value.map(r => r.verifiedAmount))
  })

  const totalVerifyDiff: ComputedRef<number> = computed(() => {
    return calcVerifyDiff(totalPaid.value, totalVerified.value)
  })

  const overallPaidInRate: ComputedRef<number> = computed(() => {
    return calcPaidInRate(totalPaid.value, totalSubscribed.value)
  })

  // ─── 4. 阈值高亮判断 ─────────────────────────────────────────────────

  /** 判断验资差异是否超阈值（需红色高亮） */
  function isDiffOverThreshold(diff: number): boolean {
    return Math.abs(diff) > VERIFY_DIFF_THRESHOLD
  }

  /** 判断出资到位率是否低于100%（需黄色提示） */
  function isPaidInRateBelowFull(rate: number): boolean {
    return rate < PAID_IN_RATE_THRESHOLD && rate >= 0
  }

  /** 存在异常的行（差异超阈值或到位率不足） */
  const alertRows: ComputedRef<M2VerifyRow[]> = computed(() => {
    return computedVerifyRows.value.filter(
      row => isDiffOverThreshold(row.verifyDiff) || isPaidInRateBelowFull(row.paidInRate),
    )
  })

  // ─── 5. 验资行操作 ────────────────────────────────────────────────────

  /** 新增验资核对行 */
  function addVerifyRow(investorName?: string): void {
    const key = `m2-verify-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const seq = verifyRows.value.length + 1
    const newRow: M2VerifyRow = {
      key,
      seq,
      investorName: investorName || '',
      subscribedAmount: 0,
      paidAmount: 0,
      verifiedAmount: 0,
      verifyDiff: 0,
      paidInRate: 0,
      verifyOrg: '',
      verifyReportNo: '',
      verifyDate: '',
      remark: '',
    }
    verifyRows.value.push(newRow)
    _persistVerifyRows()
  }

  /** 删除验资行 */
  function removeVerifyRow(index: number): void {
    if (index < 0 || index >= verifyRows.value.length) return
    verifyRows.value.splice(index, 1)
    verifyRows.value.forEach((r, i) => { r.seq = i + 1 })
    _persistVerifyRows()
  }

  /** 更新验资行字段 */
  function updateVerifyRow(index: number, field: keyof M2VerifyRow, value: any): void {
    if (index < 0 || index >= verifyRows.value.length) return
    const row = verifyRows.value[index] as any
    row[field] = value
    _persistVerifyRows()
  }

  // ─── 6. 检查项操作 ────────────────────────────────────────────────────

  /** 检查完成率 */
  const completionRate: ComputedRef<number> = computed(() => {
    const total = checkItems.value.length
    if (total === 0) return 0
    const completed = checkItems.value.filter(
      item => item.status === 'pass' || item.status === 'fail' || item.status === 'na',
    ).length
    return Math.round((completed / total) * 100)
  })

  /** 是否全部检查完成 */
  const isAllChecked: ComputedRef<boolean> = computed(() => {
    return completionRate.value === 100
  })

  /** 未通过项数 */
  const failedCount: ComputedRef<number> = computed(() => {
    return checkItems.value.filter(item => item.status === 'fail').length
  })

  /** 更新检查项状态 */
  function updateCheckStatus(itemId: string, status: CheckStatus): void {
    const item = checkItems.value.find(i => i.id === itemId)
    if (item) {
      item.status = status
      _persistCheckItems()
    }
  }

  /** 更新检查项备注 */
  function updateCheckRemark(itemId: string, remark: string): void {
    const item = checkItems.value.find(i => i.id === itemId)
    if (item) {
      item.remark = remark
      _persistCheckItems()
    }
  }

  // ─── 7. AI辅助section操作 ─────────────────────────────────────────────

  /** 更新AI section内容 */
  function updateAiSectionContent(sectionId: string, content: string): void {
    const section = aiSections.value.find(s => s.sectionId === sectionId)
    if (section) {
      section.content = content
      _persistAiSections()
    }
  }

  /** 标记AI section正在生成 */
  function setAiSectionGenerating(sectionId: string, generating: boolean): void {
    const section = aiSections.value.find(s => s.sectionId === sectionId)
    if (section) {
      section.isGenerating = generating
    }
  }

  // ─── 8. 审计结论操作 ──────────────────────────────────────────────────

  /** 更新审计结论 */
  function updateConclusion(field: keyof M2AuditConclusion, value: string): void {
    conclusion.value[field] = value
    _persistConclusion()
  }

  // ─── 9. 持久化 ────────────────────────────────────────────────────────

  function _persistVerifyRows(): void {
    debouncedSave(VERIFY_ROWS_KEY, { conclusion: JSON.stringify(verifyRows.value) })
  }

  function _persistCheckItems(): void {
    debouncedSave(CHECK_ITEMS_KEY, { conclusion: JSON.stringify(checkItems.value) })
  }

  function _persistAiSections(): void {
    debouncedSave(AI_SECTIONS_KEY, { conclusion: JSON.stringify(aiSections.value) })
  }

  function _persistConclusion(): void {
    debouncedSave(CONCLUSION_KEY, { conclusion: JSON.stringify(conclusion.value) })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 验资核对行
    verifyRows,
    computedVerifyRows,
    totalSubscribed,
    totalPaid,
    totalVerified,
    totalVerifyDiff,
    overallPaidInRate,

    // 阈值判断
    isDiffOverThreshold,
    isPaidInRateBelowFull,
    alertRows,

    // 验资行操作
    addVerifyRow,
    removeVerifyRow,
    updateVerifyRow,

    // 检查项
    checkItems,
    completionRate,
    isAllChecked,
    failedCount,
    updateCheckStatus,
    updateCheckRemark,

    // AI section
    aiSections,
    updateAiSectionContent,
    setAiSectionGenerating,

    // 结论
    conclusion,
    updateConclusion,
  }
}

export default useM2CapitalCheck
