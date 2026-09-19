/**
 * useL7OtherCheck — L7-4 其他非流动负债检查表 composable
 *
 * Spec: .kiro/specs/l7-other-noncurrent-liabilities/
 * Task: 3.4
 * Requirements: 4.1-4.2
 *
 * 职责：
 * - 管理核对清单items（存在性/完整性/分类/准确性等检查项）
 * - 借方列(F)、贷方列(G)合计 + 凭证内容(H-M)
 * - 核对结论区（el-card包裹）
 * - 各section AI按钮
 * - 完成度统计
 *
 * xlsx 结构（L7-4）：
 *   A-G(核对项目) | H(审计说明) | I-M(凭证内容) | N(审计说明) | O(结论) | P(索引)
 *   实际：A(序号) B-E(核对项目描述+明细) F(借方) G(贷方) H-M(凭证金额/内容) N(审计说明) O(结论) P(索引)
 *   row22=SUM(F12:F21), row23=明细表L7-2'!N17, row24=F22/F23
 *
 * 科目：2801 其他非流动负债（贷方/负债类）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { ChecklistResponse } from './useL7FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 检查项 */
export interface L7CheckItem {
  /** 检查项唯一标识 */
  key: string
  /** 检查项标题/核对内容 */
  title: string
  /** 所属section */
  section: L7CheckSection
  /** 借方金额（F列） */
  debitAmount: number
  /** 贷方金额（G列） */
  creditAmount: number
  /** 凭证号/内容（H-M列，字符串） */
  voucherContent: string
  /** 审计说明（N列） */
  auditRemark: string
  /** 结论（O列：通过/不通过/不适用） */
  conclusion: string
  /** 是否支持AI辅助 */
  hasAiAssist: boolean
}

/** 检查表section */
export type L7CheckSection =
  | 'existence'       // 存在性
  | 'completeness'    // 完整性
  | 'classification'  // 分类与列报
  | 'accuracy'        // 准确性
  | 'conclusion'      // 审计结论

/** 结论选项 */
export type L7ConclusionOption = '通过' | '不通过' | '不适用' | ''

// ─── Constants ───────────────────────────────────────────────────────────────

const PREFIX = 'L7-L7-4'

/** 结论选项列表 */
export const L7_CONCLUSION_OPTIONS: L7ConclusionOption[] = ['通过', '不通过', '不适用', '']

/** 检查项定义（基于xlsx L7-4结构） */
export const L7_CHECK_ITEMS_DEFINITION: Array<{
  key: string
  title: string
  section: L7CheckSection
  hasAiAssist: boolean
}> = [
  // 存在性section
  {
    key: 'existence-confirm',
    title: '确认账面其他非流动负债的真实存在性（查验合同/协议）',
    section: 'existence',
    hasAiAssist: true,
  },
  {
    key: 'existence-nature',
    title: '核实负债性质（是否满足非流动负债确认条件：到期日>1年）',
    section: 'existence',
    hasAiAssist: true,
  },
  // 完整性section
  {
    key: 'completeness-all-items',
    title: '确认所有其他非流动负债项目均已完整记录',
    section: 'completeness',
    hasAiAssist: true,
  },
  {
    key: 'completeness-cutoff',
    title: '检查截止日是否存在未入账的其他非流动负债',
    section: 'completeness',
    hasAiAssist: false,
  },
  {
    key: 'completeness-reclassify',
    title: '检查一年内到期部分是否已重分类至流动负债',
    section: 'completeness',
    hasAiAssist: true,
  },
  // 分类section
  {
    key: 'classification-proper',
    title: '核对负债分类是否恰当（递延收益/保证金/押金/其他）',
    section: 'classification',
    hasAiAssist: true,
  },
  {
    key: 'classification-disclosure',
    title: '检查附注披露是否充分、分类是否与账面一致',
    section: 'classification',
    hasAiAssist: false,
  },
  // 准确性section
  {
    key: 'accuracy-balance',
    title: '核对期末余额=期初+贷方增加-借方减少',
    section: 'accuracy',
    hasAiAssist: true,
  },
  {
    key: 'accuracy-detail-match',
    title: '核对明细表L7-2合计与审定表L7-1是否一致',
    section: 'accuracy',
    hasAiAssist: false,
  },
  {
    key: 'accuracy-voucher',
    title: '抽查大额变动凭证，核实交易真实性',
    section: 'accuracy',
    hasAiAssist: true,
  },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeItemId(key: string, field: string): string {
  return `${PREFIX}-${key}-${field}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L7-4 检查表业务逻辑
 *
 * @param options composable 选项
 */
export function useL7OtherCheck(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (itemId: string, value: { conclusion?: string; remark?: string }) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}) {
  const { allResponses, saveField, debouncedSave } = options

  // ─── Check items reactive ──────────────────────────────────────────────

  const checkItems = ref<L7CheckItem[]>([])

  // Load from allResponses
  watch(
    () => allResponses.value,
    (responses) => {
      checkItems.value = L7_CHECK_ITEMS_DEFINITION.map(def => {
        const conclusionResp = responses.get(makeItemId(def.key, 'conclusion'))
        const remarkResp = responses.get(makeItemId(def.key, 'remark'))
        const debitResp = responses.get(makeItemId(def.key, 'debit'))
        const creditResp = responses.get(makeItemId(def.key, 'credit'))
        const voucherResp = responses.get(makeItemId(def.key, 'voucher'))
        return {
          key: def.key,
          title: def.title,
          section: def.section,
          debitAmount: debitResp?.remark ? Number(debitResp.remark) : 0,
          creditAmount: creditResp?.remark ? Number(creditResp.remark) : 0,
          voucherContent: voucherResp?.remark || '',
          auditRemark: remarkResp?.remark || '',
          conclusion: conclusionResp?.conclusion || '',
          hasAiAssist: def.hasAiAssist,
        }
      })
    },
    { immediate: true, deep: true },
  )

  // ─── 按section分组 ────────────────────────────────────────────────────

  const sections: ComputedRef<Record<L7CheckSection, L7CheckItem[]>> = computed(() => {
    const result: Record<L7CheckSection, L7CheckItem[]> = {
      'existence': [],
      'completeness': [],
      'classification': [],
      'accuracy': [],
      'conclusion': [],
    }
    for (const item of checkItems.value) {
      result[item.section].push(item)
    }
    return result
  })

  /** Section标题映射 */
  const sectionLabels: Record<L7CheckSection, string> = {
    'existence': '一、存在性检查',
    'completeness': '二、完整性检查',
    'classification': '三、分类与列报',
    'accuracy': '四、准确性检查',
    'conclusion': '五、审计结论',
  }

  // ─── 审计结论区 ────────────────────────────────────────────────────────

  const auditConclusion = ref('')
  const conclusionRemark = ref('')

  watch(
    () => allResponses.value.get(`${PREFIX}-overall-conclusion`)?.conclusion,
    (val) => { auditConclusion.value = val || '' },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(`${PREFIX}-overall-remark`)?.remark,
    (val) => { conclusionRemark.value = val || '' },
    { immediate: true },
  )

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

  // ─── 操作方法 ──────────────────────────────────────────────────────────

  /**
   * 更新检查项结论（即时保存）
   */
  async function updateCheckItem(
    key: string,
    field: 'conclusion' | 'auditRemark' | 'debitAmount' | 'creditAmount' | 'voucherContent',
    value: string | number,
  ): Promise<void> {
    const idx = checkItems.value.findIndex(i => i.key === key)
    if (idx === -1) return

    // 同步本地状态
    const item = checkItems.value[idx] as any
    item[field] = value

    // 持久化
    if (field === 'conclusion') {
      const itemId = makeItemId(key, 'conclusion')
      await saveField(itemId, { conclusion: String(value) })
    } else if (field === 'auditRemark') {
      const itemId = makeItemId(key, 'remark')
      debouncedSave(itemId, { remark: String(value) })
    } else if (field === 'debitAmount') {
      const itemId = makeItemId(key, 'debit')
      debouncedSave(itemId, { remark: String(value) })
    } else if (field === 'creditAmount') {
      const itemId = makeItemId(key, 'credit')
      debouncedSave(itemId, { remark: String(value) })
    } else if (field === 'voucherContent') {
      const itemId = makeItemId(key, 'voucher')
      debouncedSave(itemId, { remark: String(value) })
    }
  }

  /**
   * 保存总体审计结论
   */
  async function saveAuditConclusion(conclusion: string): Promise<void> {
    auditConclusion.value = conclusion
    await saveField(`${PREFIX}-overall-conclusion`, { conclusion })
  }

  /**
   * 更新结论备注（debounce）
   */
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
    auditConclusion,
    conclusionRemark,
    // 统计
    completionStats,
    // 操作
    updateCheckItem,
    saveAuditConclusion,
    updateConclusionRemark,
    // 常量
    L7_CONCLUSION_OPTIONS,
  }
}

export default useL7OtherCheck
