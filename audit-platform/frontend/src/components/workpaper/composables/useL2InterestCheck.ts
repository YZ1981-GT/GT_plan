/**
 * useL2InterestCheck — L2-4 应付利息检查表核心逻辑 composable
 *
 * Spec: .kiro/specs/l2-interest-payable/
 * Task: 3.4
 * Requirements: 5.1-5.2, 4.1-4.6
 *
 * 职责：
 * - 管理核对清单items（计提核对/逾期/完整性/准确性等检查项）
 * - 核对结论区（el-card包裹）
 * - 与 useL2CrossSheet 联动：accrualVsL1L3 一致性显示
 * - 各section AI按钮 placeholder
 * - 链接 L1/L3 利息测算结果（通过 cross_wp_references）
 *
 * 科目：2231 应付利息（贷方/负债类）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { ChecklistResponse } from './useL2FormData'
import type { AccrualVsL1L3Result } from './useL2CrossSheet'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 检查项 */
export interface CheckItem {
  /** 检查项唯一标识 */
  key: string
  /** 检查项标题 */
  title: string
  /** 所属section */
  section: CheckSection
  /** 检查结论（通过/不通过/不适用） */
  conclusion: string
  /** 审计说明/备注 */
  remark: string
  /** 是否支持AI辅助 */
  hasAiAssist: boolean
}

/** 检查表section */
export type CheckSection =
  | 'accrual-verification'   // 计提核对
  | 'overdue-analysis'       // 逾期分析
  | 'completeness'           // 完整性检查
  | 'accuracy'               // 准确性检查
  | 'conclusion'             // 审计结论

/** 结论选项 */
export type ConclusionOption = '通过' | '不通过' | '不适用' | ''

export interface UseL2InterestCheckOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveField: (itemId: string, value: { conclusion?: string; remark?: string }) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  /** 来自 useL2CrossSheet 的计提核对结果 */
  accrualVsL1L3: ComputedRef<AccrualVsL1L3Result>
  /** L1/L3 利息测算是否就绪 */
  isInterestDataReady: ComputedRef<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const PREFIX = 'L2-L2-4'

/** 结论选项列表 */
export const CONCLUSION_OPTIONS: ConclusionOption[] = ['通过', '不通过', '不适用', '']

/** 检查项定义 */
export const CHECK_ITEMS_DEFINITION: Array<{
  key: string
  title: string
  section: CheckSection
  hasAiAssist: boolean
}> = [
  // 计提核对section
  {
    key: 'accrual-l1-match',
    title: '核对L1短期借款利息测算与账面计提是否一致',
    section: 'accrual-verification',
    hasAiAssist: true,
  },
  {
    key: 'accrual-l3-match',
    title: '核对L3长期借款利息测算与账面计提是否一致',
    section: 'accrual-verification',
    hasAiAssist: true,
  },
  {
    key: 'accrual-rate-verify',
    title: '验证利息计算所用利率与合同约定是否一致',
    section: 'accrual-verification',
    hasAiAssist: false,
  },
  {
    key: 'accrual-period-verify',
    title: '验证计息期间的起止日期与合同条款是否匹配',
    section: 'accrual-verification',
    hasAiAssist: false,
  },
  // 逾期分析section
  {
    key: 'overdue-identification',
    title: '识别逾期未付利息并分析原因',
    section: 'overdue-analysis',
    hasAiAssist: true,
  },
  {
    key: 'overdue-impairment',
    title: '评估逾期利息的可收回性及减值需要',
    section: 'overdue-analysis',
    hasAiAssist: true,
  },
  // 完整性检查section
  {
    key: 'completeness-all-loans',
    title: '确认所有借款合同的应付利息均已完整记录',
    section: 'completeness',
    hasAiAssist: true,
  },
  {
    key: 'completeness-cutoff',
    title: '检查截止日期前后的利息计提是否归属正确期间',
    section: 'completeness',
    hasAiAssist: false,
  },
  // 准确性检查section
  {
    key: 'accuracy-formula',
    title: '验证利息计算公式（本金×利率×天数/365）的准确性',
    section: 'accuracy',
    hasAiAssist: true,
  },
  {
    key: 'accuracy-balance-movement',
    title: '核对期末余额变动的合理性（期初+计提-支付=期末）',
    section: 'accuracy',
    hasAiAssist: false,
  },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeItemId(key: string, field: string): string {
  return `${PREFIX}-${key}-${field}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useL2InterestCheck(options: UseL2InterestCheckOptions) {
  const {
    allResponses,
    saveField,
    debouncedSave,
    accrualVsL1L3,
    isInterestDataReady,
  } = options

  // ─── Check items reactive ──────────────────────────────────────────────

  const checkItems = ref<CheckItem[]>([])

  // Load from allResponses
  watch(
    () => allResponses.value,
    (responses) => {
      checkItems.value = CHECK_ITEMS_DEFINITION.map(def => {
        const conclusionResp = responses.get(makeItemId(def.key, 'conclusion'))
        const remarkResp = responses.get(makeItemId(def.key, 'remark'))
        return {
          key: def.key,
          title: def.title,
          section: def.section,
          conclusion: conclusionResp?.conclusion || '',
          remark: remarkResp?.remark || '',
          hasAiAssist: def.hasAiAssist,
        }
      })
    },
    { immediate: true, deep: true },
  )

  // ─── 按section分组 ────────────────────────────────────────────────────

  const sections: ComputedRef<Record<CheckSection, CheckItem[]>> = computed(() => {
    const result: Record<CheckSection, CheckItem[]> = {
      'accrual-verification': [],
      'overdue-analysis': [],
      'completeness': [],
      'accuracy': [],
      'conclusion': [],
    }
    for (const item of checkItems.value) {
      result[item.section].push(item)
    }
    return result
  })

  /** Section标题映射 */
  const sectionLabels: Record<CheckSection, string> = {
    'accrual-verification': '一、计提核对',
    'overdue-analysis': '二、逾期分析',
    'completeness': '三、完整性检查',
    'accuracy': '四、准确性检查',
    'conclusion': '五、审计结论',
  }

  // ─── 审计结论区 ────────────────────────────────────────────────────────

  const overallConclusion = ref('')
  const conclusionRemark = ref('')

  watch(
    () => allResponses.value.get(`${PREFIX}-overall-conclusion`)?.conclusion,
    (val) => { overallConclusion.value = val || '' },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(`${PREFIX}-overall-remark`)?.remark,
    (val) => { conclusionRemark.value = val || '' },
    { immediate: true },
  )

  // ─── 计提核对摘要（来自 useL2CrossSheet） ─────────────────────────────

  /** 计提差异摘要 */
  const accrualSummary: ComputedRef<{
    diff: number
    isConsistent: boolean
    statusText: string
    statusType: 'success' | 'warning' | 'danger' | 'info'
  }> = computed(() => {
    if (!isInterestDataReady.value) {
      return {
        diff: 0,
        isConsistent: false,
        statusText: '待L1/L3利息测算完成',
        statusType: 'info',
      }
    }

    const result = accrualVsL1L3.value
    if (result.isConsistent) {
      return {
        diff: result.diff,
        isConsistent: true,
        statusText: `一致（差异${result.diff}元）`,
        statusType: 'success',
      }
    }

    return {
      diff: result.diff,
      isConsistent: false,
      statusText: `不一致，差异${result.diff}元（${result.diff > 0 ? '少计提' : '多计提'}）`,
      statusType: 'danger',
    }
  })

  // ─── 完成度统计 ────────────────────────────────────────────────────────

  const completionStats: ComputedRef<{ total: number; completed: number; rate: number }> = computed(() => {
    const total = checkItems.value.length
    const completed = checkItems.value.filter(item => item.conclusion !== '').length
    return {
      total,
      completed,
      rate: total > 0 ? Math.round((completed / total) * 100) : 0,
    }
  })

  // ─── updateConclusion ──────────────────────────────────────────────────

  /**
   * 更新检查项结论（即时保存）
   */
  async function updateConclusion(key: string, conclusion: ConclusionOption): Promise<void> {
    const itemId = makeItemId(key, 'conclusion')
    await saveField(itemId, { conclusion })

    // 同步本地状态
    const idx = checkItems.value.findIndex(i => i.key === key)
    if (idx !== -1) {
      checkItems.value[idx] = { ...checkItems.value[idx], conclusion }
    }
  }

  // ─── updateRemark ──────────────────────────────────────────────────────

  /**
   * 更新检查项备注（debounce保存）
   */
  function updateRemark(key: string, remark: string): void {
    const itemId = makeItemId(key, 'remark')
    debouncedSave(itemId, { remark })

    // 同步本地状态
    const idx = checkItems.value.findIndex(i => i.key === key)
    if (idx !== -1) {
      checkItems.value[idx] = { ...checkItems.value[idx], remark }
    }
  }

  // ─── saveOverallConclusion ─────────────────────────────────────────────

  async function saveOverallConclusion(conclusion: string): Promise<void> {
    overallConclusion.value = conclusion
    await saveField(`${PREFIX}-overall-conclusion`, { conclusion })
  }

  function updateConclusionRemark(remark: string): void {
    conclusionRemark.value = remark
    debouncedSave(`${PREFIX}-overall-remark`, { remark })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 检查项
    checkItems,
    sections,
    sectionLabels,
    // 结论
    overallConclusion,
    conclusionRemark,
    // 计提核对摘要
    accrualSummary,
    isInterestDataReady,
    // 统计
    completionStats,
    // 操作
    updateConclusion,
    updateRemark,
    saveOverallConclusion,
    updateConclusionRemark,
    // 常量
    CONCLUSION_OPTIONS,
  }
}

export default useL2InterestCheck
