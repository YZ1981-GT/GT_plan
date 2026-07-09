/**
 * useM10InstrumentCheck — M10-5 其他权益工具检查表 composable
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/
 * Task: 3.4
 * Requirements: 5.1-5.2
 *
 * 职责：
 * - 核对清单管理（逐项检查+结论）
 * - 交叉引用M10-2明细表数据（公式: =明细表M10-2!R26等）
 * - AI辅助section支持（每个文本section标题行右侧放AI按钮）
 * - 审计结论区（el-card包裹）
 *
 * M10-5检查要点：
 * - 其他权益工具的条款是否与合同一致
 * - 发行/赎回是否经过授权
 * - 利息/股息计提是否准确
 * - CAS37分类结论是否与M10-4一致
 * - 财务报表列报是否正确
 */
import { computed, ref, type ComputedRef } from 'vue'
import type { useM10FormData } from './useM10FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 检查项状态 */
export type M10CheckStatus = 'passed' | 'failed' | 'na' | 'pending'

/** 检查项结论 */
export type M10CheckConclusion = '无异常' | '存在异常' | '不适用' | ''

/** 检查项数据 */
export interface M10CheckItem {
  /** 序号 */
  index: number
  /** section标识（用于AI辅助定位） */
  sectionId: string
  /** 检查项描述 */
  description: string
  /** 检查标准/方法 */
  method: string
  /** 检查状态 */
  status: M10CheckStatus
  /** 检查结论 */
  conclusion: M10CheckConclusion
  /** 审计师说明 */
  auditorNote: string
  /** 引用来源（交叉引用M10-2等） */
  crossRef: string
  /** 交叉引用值（从M10-2自动取数） */
  crossRefValue: number | string | null
  /** 索引号 */
  refIndex: string
  /** 备注 */
  remark: string
}

/** 审计结论 */
export interface M10InstrumentConclusion {
  /** 总体结论 */
  overallConclusion: string
  /** 是否存在重大异常 */
  hasMaterialIssue: boolean
  /** 异常事项描述 */
  issueDescription: string
  /** 后续程序建议 */
  furtherProcedures: string
}

/** AI辅助section定义 */
export interface M10AiSection {
  sectionId: string
  label: string
  prompt: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 默认检查项 */
export const M10_DEFAULT_CHECK_ITEMS: Omit<M10CheckItem, 'index'>[] = [
  {
    sectionId: 'terms-verify',
    description: '核对其他权益工具的条款是否与合同/发行文件一致',
    method: '取得发行合同/章程，逐项核对关键条款（票面利率、期限、赎回条款、转股条件等）',
    status: 'pending',
    conclusion: '',
    auditorNote: '',
    crossRef: '',
    crossRefValue: null,
    refIndex: '',
    remark: '',
  },
  {
    sectionId: 'authorization-check',
    description: '检查发行/赎回是否经过适当授权',
    method: '查阅董事会/股东会决议，确认发行/赎回已获批准',
    status: 'pending',
    conclusion: '',
    auditorNote: '',
    crossRef: '',
    crossRefValue: null,
    refIndex: '',
    remark: '',
  },
  {
    sectionId: 'interest-verify',
    description: '核实利息/股息计提是否准确',
    method: '按合同约定的利率/股息率重新计算应付利息/股息，与账面记录核对',
    status: 'pending',
    conclusion: '',
    auditorNote: '',
    crossRef: '=明细表M10-2!利息区段',
    crossRefValue: null,
    refIndex: '',
    remark: '',
  },
  {
    sectionId: 'classification-consistency',
    description: 'CAS37负债权益分类是否与M10-4检查结论一致',
    method: '核对M10-4判定结论与实际账务处理，确认分类正确',
    status: 'pending',
    conclusion: '',
    auditorNote: '',
    crossRef: '=M10-4!分类结论',
    crossRefValue: null,
    refIndex: '',
    remark: '',
  },
  {
    sectionId: 'presentation-check',
    description: '财务报表列报是否正确（权益工具在权益列报，负债部分在负债列报）',
    method: '检查资产负债表列报位置，确认权益/负债分类与CAS37判定一致',
    status: 'pending',
    conclusion: '',
    auditorNote: '',
    crossRef: '',
    crossRefValue: null,
    refIndex: '',
    remark: '',
  },
  {
    sectionId: 'disclosure-check',
    description: '附注披露是否充分（工具条款、分类依据、利息/股息等）',
    method: '检查附注是否按CAS37要求披露金融工具分类依据、重要条款、利息/股息信息',
    status: 'pending',
    conclusion: '',
    auditorNote: '',
    crossRef: '',
    crossRefValue: null,
    refIndex: '',
    remark: '',
  },
  {
    sectionId: 'amount-reconciliation',
    description: '明细表合计与审定表核对',
    method: '核对M10-2明细表合计金额与M10-1审定表合计是否一致',
    status: 'pending',
    conclusion: '',
    auditorNote: '',
    crossRef: '=明细表M10-2!合计',
    crossRefValue: null,
    refIndex: '',
    remark: '',
  },
]

/** AI辅助section定义 */
export const M10_AI_SECTIONS: M10AiSection[] = [
  { sectionId: 'terms-verify', label: '条款核对', prompt: '请根据提供的合同条款信息，分析其他权益工具的关键条款是否存在异常' },
  { sectionId: 'authorization-check', label: '授权检查', prompt: '请分析发行/赎回授权是否充分' },
  { sectionId: 'interest-verify', label: '利息核实', prompt: '请根据约定利率和期限重新计算应付利息/股息' },
  { sectionId: 'classification-consistency', label: '分类一致性', prompt: '请分析CAS37分类判定结论与实际账务处理是否一致' },
  { sectionId: 'presentation-check', label: '列报检查', prompt: '请评估财务报表中其他权益工具的列报位置是否正确' },
  { sectionId: 'disclosure-check', label: '披露充分性', prompt: '请评估附注对其他权益工具的披露是否满足CAS37要求' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M10-5 其他权益工具检查表逻辑
 *
 * @param formData 由调用方传入的 useM10FormData 实例
 */
export function useM10InstrumentCheck(formData: ReturnType<typeof useM10FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  /** 检查项列表 */
  const checkItems = ref<M10CheckItem[]>(
    M10_DEFAULT_CHECK_ITEMS.map((item, i) => ({ ...item, index: i + 1 })),
  )

  /** 审计结论 */
  const conclusionData = ref<M10InstrumentConclusion>({
    overallConclusion: '',
    hasMaterialIssue: false,
    issueDescription: '',
    furtherProcedures: '',
  })

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 检查完成率 */
  const completionRate: ComputedRef<number> = computed(() => {
    const total = checkItems.value.length
    if (total === 0) return 0
    const completed = checkItems.value.filter(i => i.status !== 'pending').length
    return Math.round((completed / total) * 100)
  })

  /** 是否全部完成 */
  const isAllCompleted: ComputedRef<boolean> = computed(() => {
    return checkItems.value.every(i => i.status !== 'pending')
  })

  /** 异常项 */
  const failedItems: ComputedRef<M10CheckItem[]> = computed(() => {
    return checkItems.value.filter(i => i.status === 'failed')
  })

  /** 按section分组的检查项（用于UI渲染） */
  const itemsBySection: ComputedRef<Map<string, M10CheckItem[]>> = computed(() => {
    const map = new Map<string, M10CheckItem[]>()
    for (const item of checkItems.value) {
      const existing = map.get(item.sectionId) || []
      existing.push(item)
      map.set(item.sectionId, existing)
    }
    return map
  })

  // ─── 3. 检查项操作 ────────────────────────────────────────────────────

  /** 更新检查项状态 */
  function updateCheckStatus(index: number, status: M10CheckStatus): void {
    const item = checkItems.value.find(i => i.index === index)
    if (!item) return
    item.status = status
    // 自动推导结论
    if (status === 'passed') item.conclusion = '无异常'
    else if (status === 'failed') item.conclusion = '存在异常'
    else if (status === 'na') item.conclusion = '不适用'
    _triggerSaveItem(index)
  }

  /** 更新检查项审计师说明 */
  function updateAuditorNote(index: number, note: string): void {
    const item = checkItems.value.find(i => i.index === index)
    if (!item) return
    item.auditorNote = note
    _triggerSaveItem(index)
  }

  /** 更新检查项备注 */
  function updateRemark(index: number, remark: string): void {
    const item = checkItems.value.find(i => i.index === index)
    if (!item) return
    item.remark = remark
    _triggerSaveItem(index)
  }

  /** 设置交叉引用值（从M10-2取数回填） */
  function setCrossRefValue(index: number, value: number | string | null): void {
    const item = checkItems.value.find(i => i.index === index)
    if (!item) return
    item.crossRefValue = value
  }

  // ─── 4. 审计结论操作 ──────────────────────────────────────────────────

  /** 更新总体结论 */
  function updateConclusion(field: keyof M10InstrumentConclusion, value: string | boolean): void {
    ;(conclusionData.value as any)[field] = value
    debouncedSave('M10-5-conclusion', {
      remark: JSON.stringify(conclusionData.value),
    })
  }

  // ─── 5. 批量保存 ──────────────────────────────────────────────────────

  async function saveAll(): Promise<void> {
    const items = checkItems.value.map((item, i) => {
      const n = i + 1
      return [
        { itemId: `M10-5-check-${n}-status`, data: { remark: item.status } },
        { itemId: `M10-5-check-${n}-conclusion`, data: { remark: item.conclusion } },
        { itemId: `M10-5-check-${n}-note`, data: { remark: item.auditorNote || null } },
        { itemId: `M10-5-check-${n}-ref`, data: { remark: item.refIndex || null } },
        { itemId: `M10-5-check-${n}-remark`, data: { remark: item.remark || null } },
      ]
    }).flat()

    // 结论区
    items.push(
      { itemId: 'M10-5-conclusion', data: { remark: JSON.stringify(conclusionData.value) } },
    )

    await saveBatch(items)
  }

  // ─── 6. 内部保存触发 ──────────────────────────────────────────────────

  function _triggerSaveItem(index: number): void {
    const item = checkItems.value.find(i => i.index === index)
    if (!item) return
    debouncedSave(`M10-5-check-${index}-data`, {
      remark: JSON.stringify({
        index: item.index,
        sectionId: item.sectionId,
        status: item.status,
        conclusion: item.conclusion,
        auditorNote: item.auditorNote,
        crossRef: item.crossRef,
        refIndex: item.refIndex,
        remark: item.remark,
      }),
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // State
    checkItems,
    conclusionData,

    // 计算属性
    completionRate,
    isAllCompleted,
    failedItems,
    itemsBySection,

    // 检查项操作
    updateCheckStatus,
    updateAuditorNote,
    updateRemark,
    setCrossRefValue,

    // 结论操作
    updateConclusion,

    // 保存
    saveAll,
  }
}

export default useM10InstrumentCheck
