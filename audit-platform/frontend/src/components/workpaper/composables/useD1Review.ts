/**
 * useD1Review — D1 应收票据复核签字/只读/amendment composable
 *
 * Spec: .kiro/specs/d1-notes-receivable/
 * Task: 4.1
 *
 * 职责：
 * - isReviewed / isReadonly / canReview / pendingItems 计算属性
 * - doReview()：签字保存 + 全组件只读
 * - startAmendment(reason)：填写原因→解锁编辑→需重新复核
 * - reviewInfo：复核人/日期信息
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'
import { PROCEDURE_STEPS_CONFIG } from './useD1NotesReceivable'

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

export function useD1Review(
  allResponses: Ref<Map<string, ChecklistResponse>>,
  procedureProgress: ComputedRef<{ completed: number; total: number }>,
  canInputOverallConclusion: ComputedRef<boolean>,
  saveImmediate: SaveFn,
  externalReadonly: Ref<boolean>
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

  // ─── Computed ────────────────────────────────────────────────────────────

  /** 是否已复核：D1-review-sign conclusion === 'Y' */
  const isReviewed: ComputedRef<boolean> = computed(() => {
    return getVal('D1-review-sign').conclusion === 'Y'
  })

  /** 只读模式：外部 prop 或已复核 */
  const isReadonly: ComputedRef<boolean> = computed(() => {
    return externalReadonly.value || isReviewed.value
  })

  /** 是否可复核：所有必要程序步骤已完成或不适用 */
  const canReview: ComputedRef<boolean> = computed(() => {
    return canInputOverallConclusion.value
  })

  /** 待完成必要步骤清单（canReview 为 false 时用于 UI 提示） */
  const pendingItems: ComputedRef<string[]> = computed(() => {
    const pending: string[] = []
    PROCEDURE_STEPS_CONFIG.forEach((cfg, idx) => {
      if (!cfg.isRequired) return
      const n = idx + 1
      const status = getVal(`D1-proc-${n}-status`).conclusion
      if (status !== '已完成' && status !== '不适用') {
        pending.push(cfg.stepName)
      }
    })
    return pending
  })

  /** 复核人/日期信息（已复核时返回，否则 null） */
  const reviewInfo: ComputedRef<{ reviewer: string; date: string } | null> = computed(() => {
    if (!isReviewed.value) return null
    const reviewer = getVal('D1-review-sign').remark || ''
    const date = getVal('D1-review-date').remark || ''
    return { reviewer, date }
  })

  // ─── Actions ─────────────────────────────────────────────────────────────

  /** 执行复核签字 */
  async function doReview(): Promise<void> {
    if (!canReview.value) return

    const now = new Date()
    const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
    const reviewerName = '现场经理' // placeholder, real app would use current user

    const items: ChecklistItem[] = [
      setLocal('D1-review-sign', 'Y', reviewerName),
      setLocal('D1-review-date', null, dateStr),
    ]
    await saveImmediate(items)
  }

  /** 启动修改（Amendment）：填写原因→解锁→需重新复核 */
  async function startAmendment(reason: string): Promise<void> {
    if (!reason || !reason.trim()) return

    // 确定下一个修改轮次编号
    let k = 1
    while (getVal(`D1-amend-${k}-reason`).remark) {
      k++
    }

    const items: ChecklistItem[] = [
      // 保存修改原因
      setLocal(`D1-amend-${k}-reason`, null, reason.trim()),
      // 清除复核签字
      setLocal('D1-review-sign', null, null),
      // 清除复核日期
      setLocal('D1-review-date', null, null),
    ]
    await saveImmediate(items)
  }

  return {
    isReviewed,
    isReadonly,
    canReview,
    pendingItems,
    reviewInfo,
    doReview,
    startAmendment,
  }
}

export default useD1Review
