/**
 * useM6RetainedCheck — M6-4 检查表 composable
 *
 * Spec: .kiro/specs/m6-retained-earnings/
 * Task: 3.4
 * Requirements: 4.1-4.7, 5.1-5.2
 *
 * 职责：
 * - M6-4 检查表管理（核对清单+M5/M1联动核对+审计结论区）
 * - 核对清单项：
 *   1. 期初未分配利润=上年末审定
 *   2. 本年净利润=利润表结转
 *   3. 提取盈余公积=M5计提（surplusVsM5）
 *   4. 分配股利=M1宣告（dividendVsM1）
 *   5. 期末=期初+净利润-盈余公积-股利
 *   6. 审定数=TB科目4104余额
 *   7. 审定表=明细表（adjudicationVsDetail）
 * - 使用 useM6CrossSheet 的联动核对结果
 * - 审计结论区（el-card包裹）+ 每个section AI辅助按钮
 *
 * 科目：4104 利润分配-未分配利润（**贷方/权益类！**）
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { calcLinkageDiff } from './useM6DistributionEngine'
import type { useM6FormData } from './useM6FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 核对清单项状态 */
export type CheckStatus = 'pass' | 'fail' | 'pending' | 'not-applicable'

/** 核对清单项 */
export interface M6CheckItem {
  /** 检查项唯一标识 */
  id: string
  /** 序号 */
  order: number
  /** 检查项描述 */
  description: string
  /** 检查类别 */
  category: 'distribution-chain' | 'cross-check' | 'tb-reconciliation'
  /** 核对状态 */
  status: CheckStatus
  /** M6-2值 / 审定值 */
  m6Value: number | null
  /** 来源值（M5/M1/TB） */
  sourceValue: number | null
  /** 差异 */
  diff: number | null
  /** 备注 */
  remark: string
  /** 来源索引（GtIndexChip跳转） */
  sourceRef: string
}

/** 审计结论数据 */
export interface M6AuditConclusion {
  /** 结论类型 */
  conclusionType: 'no-exception' | 'exception-found' | 'pending'
  /** 结论文本 */
  conclusionText: string
  /** 审计建议 */
  suggestion: string
  /** 编制人 */
  preparedBy: string
  /** 编制日期 */
  preparedDate: string
  /** 复核人 */
  reviewedBy: string
  /** 复核日期 */
  reviewedDate: string
}

/** 跨底稿联动核对结果（从 CrossSheet 注入） */
export interface M6CrossCheckResults {
  /** 盈余公积联动：M6 vs M5 */
  surplusVsM5: { diff: number; isConsistent: boolean }
  /** 股利联动：M6 vs M1 */
  dividendVsM1: { diff: number; isConsistent: boolean }
  /** 审定表vs明细表 */
  adjudicationVsDetail: { diff: number; isMatch: boolean }
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 默认核对清单模板 */
const DEFAULT_CHECK_ITEMS: Omit<M6CheckItem, 'status' | 'm6Value' | 'sourceValue' | 'diff' | 'remark'>[] = [
  { id: 'chk-01', order: 1, description: '期初未分配利润与上年末审定数一致', category: 'distribution-chain', sourceRef: '上年度M6' },
  { id: 'chk-02', order: 2, description: '本年净利润与利润表结转数一致', category: 'distribution-chain', sourceRef: '利润表' },
  { id: 'chk-03', order: 3, description: '提取盈余公积=M5盈余公积实际计提数', category: 'cross-check', sourceRef: 'M5' },
  { id: 'chk-04', order: 4, description: '分配股利=M1应付股利实际宣告数', category: 'cross-check', sourceRef: 'M1' },
  { id: 'chk-05', order: 5, description: '期末=期初+净利润-盈余公积-股利（结转公式链一致）', category: 'distribution-chain', sourceRef: 'M6-2' },
  { id: 'chk-06', order: 6, description: '审定数与试算表科目4104余额核对一致', category: 'tb-reconciliation', sourceRef: 'TB' },
  { id: 'chk-07', order: 7, description: '审定表(M6-1)期末=明细表(M6-2)期末', category: 'cross-check', sourceRef: 'M6-1/M6-2' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M6-4 检查表业务逻辑（核对清单+M5/M1联动核对+结论区）
 *
 * @param formData 由调用方传入的 useM6FormData 实例
 * @param crossCheckResults reactive ref of cross-check results (from useM6CrossSheet)
 */
export function useM6RetainedCheck(
  formData: ReturnType<typeof useM6FormData>,
  crossCheckResults: Ref<M6CrossCheckResults>,
) {
  const { debouncedSave, saveField } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const checkItems = ref<M6CheckItem[]>(
    DEFAULT_CHECK_ITEMS.map(item => ({
      ...item,
      status: 'pending' as CheckStatus,
      m6Value: null,
      sourceValue: null,
      diff: null,
      remark: '',
    })),
  )

  const conclusion = ref<M6AuditConclusion>({
    conclusionType: 'pending',
    conclusionText: '',
    suggestion: '',
    preparedBy: '',
    preparedDate: '',
    reviewedBy: '',
    reviewedDate: '',
  })

  // ─── 2. 自动核对状态计算 ──────────────────────────────────────────────

  /** 结合 CrossSheet 结果自动更新检查项状态 */
  const computedCheckItems: ComputedRef<M6CheckItem[]> = computed(() => {
    const results = crossCheckResults.value
    return checkItems.value.map(item => {
      const updated = { ...item }

      switch (item.id) {
        case 'chk-03': // 盈余公积 vs M5
          updated.diff = results.surplusVsM5.diff
          updated.status = results.surplusVsM5.isConsistent ? 'pass' : 'fail'
          break
        case 'chk-04': // 股利 vs M1
          updated.diff = results.dividendVsM1.diff
          updated.status = results.dividendVsM1.isConsistent ? 'pass' : 'fail'
          break
        case 'chk-07': // 审定表 vs 明细表
          updated.diff = results.adjudicationVsDetail.diff
          updated.status = results.adjudicationVsDetail.isMatch ? 'pass' : 'fail'
          break
        default:
          // 其他检查项维持手动状态
          break
      }

      return updated
    })
  })

  // ─── 3. 汇总统计 ─────────────────────────────────────────────────────

  /** 检查项通过率 */
  const checkSummary: ComputedRef<{ total: number; passed: number; failed: number; pending: number; passRate: number }> = computed(() => {
    const items = computedCheckItems.value
    const total = items.length
    const passed = items.filter(i => i.status === 'pass').length
    const failed = items.filter(i => i.status === 'fail').length
    const pending = items.filter(i => i.status === 'pending').length
    const passRate = total > 0 ? passed / total : 0
    return { total, passed, failed, pending, passRate }
  })

  /** 是否全部通过 */
  const isAllPassed: ComputedRef<boolean> = computed(() => {
    return checkSummary.value.failed === 0 && checkSummary.value.pending === 0
  })

  // ─── 4. 检查项操作 ────────────────────────────────────────────────────

  /** 手动更新检查项状态 */
  function updateCheckStatus(checkId: string, status: CheckStatus): void {
    const item = checkItems.value.find(i => i.id === checkId)
    if (item) {
      item.status = status
      _saveCheckItem(checkId)
    }
  }

  /** 更新检查项备注 */
  function updateCheckRemark(checkId: string, remark: string): void {
    const item = checkItems.value.find(i => i.id === checkId)
    if (item) {
      item.remark = remark
      _saveCheckItem(checkId)
    }
  }

  /** 设置检查项的M6值和来源值（手动录入或自动填入） */
  function setCheckValues(checkId: string, m6Value: number | null, sourceValue: number | null): void {
    const item = checkItems.value.find(i => i.id === checkId)
    if (item) {
      item.m6Value = m6Value
      item.sourceValue = sourceValue
      if (m6Value !== null && sourceValue !== null) {
        item.diff = calcLinkageDiff(m6Value, sourceValue)
        item.status = Math.abs(item.diff) < 0.01 ? 'pass' : 'fail'
      }
      _saveCheckItem(checkId)
    }
  }

  // ─── 5. 结论区操作 ────────────────────────────────────────────────────

  /** 更新审计结论 */
  function updateConclusion(field: keyof M6AuditConclusion, value: string): void {
    (conclusion.value as any)[field] = value
    _saveConclusion()
  }

  /** 自动推荐结论（基于检查结果） */
  const recommendedConclusion: ComputedRef<string> = computed(() => {
    const summary = checkSummary.value
    if (summary.failed > 0) {
      return `经核对，发现${summary.failed}项不一致，需进一步追查差异原因。`
    }
    if (summary.pending > 0) {
      return '部分检查项尚未完成，请继续核对。'
    }
    return '经核对，未分配利润各项数据勾稽一致，分配结转过程无异常。'
  })

  // ─── 6. 保存 ──────────────────────────────────────────────────────────

  function _saveCheckItem(checkId: string): void {
    const item = checkItems.value.find(i => i.id === checkId)
    if (!item) return
    debouncedSave(`M6-4-check-${checkId}`, {
      remark: JSON.stringify({
        status: item.status,
        m6Value: item.m6Value,
        sourceValue: item.sourceValue,
        diff: item.diff,
        remark: item.remark,
      }),
    })
  }

  function _saveConclusion(): void {
    debouncedSave('M6-4-conclusion', {
      remark: JSON.stringify(conclusion.value),
    })
  }

  /** 即时保存结论（选择结论类型时） */
  async function saveConclusionImmediate(): Promise<void> {
    await saveField('M6-4-conclusion', {
      remark: JSON.stringify(conclusion.value),
    })
  }

  // ─── 7. 加载已保存数据 ────────────────────────────────────────────────

  /** 从 allResponses 恢复检查表数据 */
  function loadFromResponses(allResponses: Map<string, any>): void {
    // 恢复各检查项
    for (const item of checkItems.value) {
      const resp = allResponses.get(`M6-4-check-${item.id}`)
      if (resp?.remark) {
        try {
          const data = JSON.parse(resp.remark)
          item.status = data.status || 'pending'
          item.m6Value = data.m6Value ?? null
          item.sourceValue = data.sourceValue ?? null
          item.diff = data.diff ?? null
          item.remark = data.remark || ''
        } catch { /* ignore parse error */ }
      }
    }

    // 恢复结论
    const conclusionResp = allResponses.get('M6-4-conclusion')
    if (conclusionResp?.remark) {
      try {
        const data = JSON.parse(conclusionResp.remark)
        Object.assign(conclusion.value, data)
      } catch { /* ignore parse error */ }
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // State
    checkItems,
    conclusion,

    // 计算属性
    computedCheckItems,
    checkSummary,
    isAllPassed,
    recommendedConclusion,

    // 检查项操作
    updateCheckStatus,
    updateCheckRemark,
    setCheckValues,

    // 结论操作
    updateConclusion,
    saveConclusionImmediate,

    // 加载
    loadFromResponses,
  }
}

export default useM6RetainedCheck
