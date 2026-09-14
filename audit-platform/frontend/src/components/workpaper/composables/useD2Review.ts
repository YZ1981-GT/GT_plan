/**
 * useD2Review — D2 应收账款复核签字/只读/amendment composable
 *
 * Spec: .kiro/specs/d2-accounts-receivable/
 * Task: 4.1
 *
 * 职责：
 * - isReviewed / isReadonly / canReview / pendingItems 计算属性
 * - doReview()：签字保存 + 全组件只读
 * - startAmendment(reason)：填写原因→解锁编辑→需重新复核
 * - reviewInfo：复核人/日期信息
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD2FormData'
import { PROCEDURE_STEPS_CONFIG } from './d2Constants'

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

export function useD2Review(
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

  // Suppress unused param warnings
  void procedureProgress

  // ─── Computed ────────────────────────────────────────────────────────────

  /** 是否已复核：D2-review-sign conclusion === 'Y' */
  const isReviewed: ComputedRef<boolean> = computed(() => {
    return getVal('D2-review-sign').conclusion === 'Y'
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
      const status = getVal(`D2-proc-${n}-status`).conclusion
      if (status !== '已完成' && status !== '不适用') {
        pending.push(cfg.stepName)
      }
    })
    return pending
  })

  /** 复核人/日期信息（已复核时返回，否则 null） */
  const reviewInfo: ComputedRef<{ reviewer: string; date: string } | null> = computed(() => {
    if (!isReviewed.value) return null
    const reviewer = getVal('D2-review-sign').remark || ''
    const date = getVal('D2-review-date').remark || ''
    return { reviewer, date }
  })

  // ─── Actions ─────────────────────────────────────────────────────────────

  /** 执行复核签字 */
  async function doReview(): Promise<void> {
    if (!canReview.value) return

    const now = new Date()
    const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
    const reviewerName = '现场经理'

    const items: ChecklistItem[] = [
      setLocal('D2-review-sign', 'Y', reviewerName),
      setLocal('D2-review-date', null, dateStr),
    ]
    await saveImmediate(items)
  }

  /** 启动修改（Amendment）：填写原因→解锁→需重新复核 */
  async function startAmendment(reason: string): Promise<void> {
    if (!reason || !reason.trim()) return

    let k = 1
    while (getVal(`D2-amend-${k}-reason`).remark) {
      k++
    }

    const items: ChecklistItem[] = [
      setLocal(`D2-amend-${k}-reason`, null, reason.trim()),
      setLocal('D2-review-sign', null, null),
      setLocal('D2-review-date', null, null),
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

export default useD2Review
