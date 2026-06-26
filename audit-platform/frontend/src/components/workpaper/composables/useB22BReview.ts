/**
 * useB22BReview — B22B 现场经理复核签字/只读状态/Amendment机制
 *
 * Spec: .kiro/specs/b22b-deficiency-evaluation/
 * Task: 2.3
 *
 * 职责：
 * - 复核状态计算（isReviewed / isReadonly / canReview）
 * - 待完成事项清单（pendingItems）— 未完成严重程度评定的缺陷
 * - 复核信息（reviewInfo）
 * - 现场经理签字操作（doReview）— 前置条件：allEvaluated=true
 * - Amendment 修改机制（startAmendment）
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useB22BFormData'
import type { EvaluationItem } from './useB22BDeficiency'

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

// ─── Composable ──────────────────────────────────────────────────────────────

export function useB22BReview(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistResponse>>,
  allEvaluated: ComputedRef<boolean>,
  deficiencyItems: Ref<EvaluationItem[]>,
  externalReadonly: Ref<boolean>,
  saveImmediate: SaveFn
) {
  // ─── isReviewed ────────────────────────────────────────────────────────

  const isReviewed: ComputedRef<boolean> = computed(() => {
    const item = allResponses.value.get('B22B-review-sign')
    return item?.conclusion === 'Y'
  })

  // ─── isReadonly ────────────────────────────────────────────────────────

  const isReadonly: ComputedRef<boolean> = computed(() => {
    return externalReadonly.value || isReviewed.value
  })

  // ─── canReview ─────────────────────────────────────────────────────────

  const canReview: ComputedRef<boolean> = computed(() => {
    // All non-eliminated deficiency items must have severity set
    return allEvaluated.value
  })

  // ─── pendingItems ──────────────────────────────────────────────────────

  const pendingItems: ComputedRef<string[]> = computed(() => {
    const items: string[] = []

    const activeItems = deficiencyItems.value.filter(i => !i.eliminated)
    for (let i = 0; i < activeItems.length; i++) {
      const item = activeItems[i]
      if (item.severity === null) {
        const label = item.source.controlPoint || `缺陷 ${i + 1}`
        items.push(`${label}：未评定严重程度`)
      }
    }

    return items
  })

  // ─── reviewInfo ────────────────────────────────────────────────────────

  const reviewInfo: ComputedRef<{ reviewer: string; date: string } | null> = computed(() => {
    if (!isReviewed.value) return null

    const item = allResponses.value.get('B22B-review-sign')
    if (!item) return null

    return {
      reviewer: item.remark || '',
      date: item.wp_ref || '',
    }
  })

  // ─── doReview ──────────────────────────────────────────────────────────

  async function doReview(): Promise<void> {
    if (!canReview.value) return

    const userName = '当前用户' // placeholder — actual user from auth context

    const today = new Date()
    const dateStr = [
      today.getFullYear(),
      String(today.getMonth() + 1).padStart(2, '0'),
      String(today.getDate()).padStart(2, '0'),
    ].join('-')

    const item: ChecklistItem = {
      item_id: 'B22B-review-sign',
      conclusion: 'Y',
      remark: userName,
      wp_ref: dateStr,
    }

    allResponses.value.set(item.item_id, item)
    await saveImmediate([item])
  }

  // ─── startAmendment ────────────────────────────────────────────────────

  async function startAmendment(reason: string): Promise<void> {
    const trimmed = reason.trim()
    if (!trimmed) {
      throw new Error('修改原因不能为空')
    }

    // Determine amendment index N by counting existing B22B-amend-{N}-reason items
    let n = 0
    for (const key of allResponses.value.keys()) {
      const match = key.match(/^B22B-amend-(\d+)-reason$/)
      if (match) {
        const idx = parseInt(match[1], 10)
        if (idx >= n) n = idx + 1
      }
    }

    // Save amendment reason
    const reasonItem: ChecklistItem = {
      item_id: `B22B-amend-${n}-reason`,
      conclusion: null,
      remark: trimmed,
      wp_ref: null,
    }

    // Reset review sign
    const resetReview: ChecklistItem = {
      item_id: 'B22B-review-sign',
      conclusion: null,
      remark: null,
      wp_ref: null,
    }

    // Update local state
    allResponses.value.set(reasonItem.item_id, reasonItem)
    allResponses.value.set(resetReview.item_id, resetReview)

    await saveImmediate([reasonItem, resetReview])
  }

  // ─── Return ────────────────────────────────────────────────────────────

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

export default useB22BReview
