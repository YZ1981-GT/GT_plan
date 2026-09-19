/**
 * useM1DividendCheck — M1-6 应付股利检查表 composable
 *
 * Spec: .kiro/specs/m1-dividends-payable/
 * Task: 3.4
 * Requirements: 6.1-6.2
 *
 * 职责：
 * - 管理核对清单项 + 审计结论区
 * - AI辅助 section管理（per text section AI button）
 * - 每个文本section标题行右侧放AI辅助按钮
 * - 存储到 checklist_responses（前缀 M1-M1-6-）
 *
 * 检查项包括：
 * - 应付股利完整性检查（股东清册核对）
 * - 应付股利准确性检查（宣告分配 vs 账面）
 * - 应付股利分类检查（按股东类型）
 * - 应付股利截止性检查（宣告日/支付日）
 * - 外币应付股利汇率检查（M1-4联动）
 * - 审计结论（审计发现+最终结论）
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import type { useM1FormData } from './useM1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 检查状态 */
export type CheckStatus = 'pending' | 'pass' | 'fail' | 'na'

/** 单个检查项 */
export interface M1CheckItem {
  /** 唯一标识 */
  id: string
  /** 检查项标题 */
  title: string
  /** 检查状态 */
  status: CheckStatus
  /** 检查说明/备注 */
  remark: string
  /** 是否支持AI辅助（文本section） */
  aiEnabled: boolean
}

/** AI辅助section */
export interface M1AiSection {
  /** section标识 */
  sectionId: string
  /** section标题 */
  title: string
  /** section内容（textarea） */
  content: string
  /** AI是否正在生成 */
  isGenerating: boolean
}

/** 审计结论 */
export interface M1AuditConclusion {
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

/** 检查状态选项 */
export const CHECK_STATUS_OPTIONS: { value: CheckStatus; label: string; color: string }[] = [
  { value: 'pending', label: '待检查', color: '#909399' },
  { value: 'pass', label: '通过', color: '#67C23A' },
  { value: 'fail', label: '未通过', color: '#F56C6C' },
  { value: 'na', label: '不适用', color: '#E6A23C' },
]

/** 默认检查项清单 */
export const DEFAULT_CHECK_ITEMS: Omit<M1CheckItem, 'status' | 'remark'>[] = [
  { id: 'completeness', title: '应付股利完整性检查（股东清册核对）', aiEnabled: true },
  { id: 'accuracy', title: '应付股利准确性检查（宣告分配vs账面）', aiEnabled: true },
  { id: 'classification', title: '应付股利分类检查（按股东类型）', aiEnabled: false },
  { id: 'cutoff', title: '应付股利截止性检查（宣告日/支付日）', aiEnabled: true },
  { id: 'fx_rate', title: '外币应付股利汇率检查（M1-4联动）', aiEnabled: true },
  { id: 'disclosure', title: '应付股利披露充分性检查', aiEnabled: true },
  { id: 'resolution', title: '股东大会/董事会决议核对', aiEnabled: false },
  { id: 'payment', title: '支付合规性检查（代扣税、付款凭证）', aiEnabled: false },
]

/** AI辅助sections定义 */
export const AI_SECTIONS: Omit<M1AiSection, 'content' | 'isGenerating'>[] = [
  { sectionId: 'completeness_analysis', title: '完整性分析' },
  { sectionId: 'accuracy_analysis', title: '准确性分析' },
  { sectionId: 'cutoff_analysis', title: '截止性分析' },
  { sectionId: 'fx_analysis', title: '外币折算分析' },
  { sectionId: 'disclosure_analysis', title: '披露充分性分析' },
]

// ─── Storage Keys ────────────────────────────────────────────────────────────

const CHECK_ITEMS_KEY = 'M1-M1-6-check-items'
const AI_SECTIONS_KEY = 'M1-M1-6-ai-sections'
const CONCLUSION_KEY = 'M1-M1-6-conclusion'

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M1-6 应付股利检查表业务逻辑
 *
 * @param formData 由调用方传入的 useM1FormData 实例
 */
export function useM1DividendCheck(formData: ReturnType<typeof useM1FormData>) {
  const { getField, setField, debouncedSave, allResponses } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const checkItems = ref<M1CheckItem[]>(_loadCheckItems())
  const aiSections = ref<M1AiSection[]>(_loadAiSections())
  const conclusion = ref<M1AuditConclusion>(_loadConclusion())

  // ─── 2. 初始化加载 ────────────────────────────────────────────────────

  function _loadCheckItems(): M1CheckItem[] {
    const stored = allResponses.value.get(CHECK_ITEMS_KEY)?.conclusion
    if (stored) {
      try {
        return JSON.parse(stored)
      } catch { /* fallback */ }
    }
    // 默认初始化
    return DEFAULT_CHECK_ITEMS.map(item => ({
      ...item,
      status: 'pending' as CheckStatus,
      remark: '',
    }))
  }

  function _loadAiSections(): M1AiSection[] {
    const stored = allResponses.value.get(AI_SECTIONS_KEY)?.conclusion
    if (stored) {
      try {
        return JSON.parse(stored)
      } catch { /* fallback */ }
    }
    return AI_SECTIONS.map(s => ({
      ...s,
      content: '',
      isGenerating: false,
    }))
  }

  function _loadConclusion(): M1AuditConclusion {
    const stored = allResponses.value.get(CONCLUSION_KEY)?.conclusion
    if (stored) {
      try {
        return JSON.parse(stored)
      } catch { /* fallback */ }
    }
    return { findings: '', conclusion: '', conclusionDate: '', preparedBy: '' }
  }

  // 异步加载完成后回填
  watch(
    () => allResponses.value.get(CHECK_ITEMS_KEY)?.conclusion,
    (raw) => {
      if (raw) {
        try { checkItems.value = JSON.parse(raw) } catch { /* ignore */ }
      }
    },
  )

  watch(
    () => allResponses.value.get(AI_SECTIONS_KEY)?.conclusion,
    (raw) => {
      if (raw) {
        try { aiSections.value = JSON.parse(raw) } catch { /* ignore */ }
      }
    },
  )

  watch(
    () => allResponses.value.get(CONCLUSION_KEY)?.conclusion,
    (raw) => {
      if (raw) {
        try { conclusion.value = JSON.parse(raw) } catch { /* ignore */ }
      }
    },
  )

  // ─── 3. 计算属性 ──────────────────────────────────────────────────────

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

  /** 通过项数 */
  const passedCount: ComputedRef<number> = computed(() => {
    return checkItems.value.filter(item => item.status === 'pass').length
  })

  // ─── 4. 检查项操作 ────────────────────────────────────────────────────

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

  // ─── 5. AI辅助section操作 ─────────────────────────────────────────────

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

  /** 获取支持AI辅助的检查项（文本section标题行右侧显示AI按钮） */
  const aiEnabledItems: ComputedRef<M1CheckItem[]> = computed(() => {
    return checkItems.value.filter(item => item.aiEnabled)
  })

  // ─── 6. 审计结论操作 ──────────────────────────────────────────────────

  /** 更新审计结论 */
  function updateConclusion(field: keyof M1AuditConclusion, value: string): void {
    conclusion.value[field] = value
    _persistConclusion()
  }

  // ─── 7. 持久化 ────────────────────────────────────────────────────────

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
    // State
    checkItems,
    aiSections,
    conclusion,

    // 计算属性
    completionRate,
    isAllChecked,
    failedCount,
    passedCount,
    aiEnabledItems,

    // 检查项操作
    updateCheckStatus,
    updateCheckRemark,

    // AI section
    updateAiSectionContent,
    setAiSectionGenerating,

    // 结论
    updateConclusion,
  }
}

export default useM1DividendCheck
