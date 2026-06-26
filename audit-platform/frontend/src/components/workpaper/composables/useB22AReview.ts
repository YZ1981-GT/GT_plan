/**
 * useB22AReview — B22A 现场经理复核签字/只读状态/Amendment机制
 *
 * Spec: .kiro/specs/b22a-control-matrix/
 * Task: 2.3
 *
 * 职责：
 * - 复核状态计算（isReviewed / isReadonly / canReview）
 * - 待完成事项清单（pendingItems）
 * - 复核信息（reviewInfo）
 * - 现场经理签字操作（doReview）
 * - Amendment 修改机制（startAmendment）
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useB22AFormData'
import type { ElementScore, TabNumber } from './useB22AControlMatrix'
import { COSO_TABS } from './useB22AControlMatrix'

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

// ─── Composable ──────────────────────────────────────────────────────────────

export function useB22AReview(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistResponse>>,
  completedElementCount: ComputedRef<number>,
  overallConclusion: Ref<ElementScore | null>,
  externalReadonly: Ref<boolean>,
  saveImmediate: SaveFn
) {
  // ─── isReviewed ────────────────────────────────────────────────────────

  const isReviewed: ComputedRef<boolean> = computed(() => {
    const item = allResponses.value.get('B22A-review-sign')
    return item?.conclusion === 'Y'
  })

  // ─── isReadonly ────────────────────────────────────────────────────────

  const isReadonly: ComputedRef<boolean> = computed(() => {
    return externalReadonly.value || isReviewed.value
  })

  // ─── canReview ─────────────────────────────────────────────────────────

  const canReview: ComputedRef<boolean> = computed(() => {
    // Condition (a): all 5 elements have all check items with non-null conclusion
    // (excluding '不适用' items from the completion check is NOT needed —
    //  we need all items to have ANY conclusion set, including '不适用')
    for (const cosoTab of COSO_TABS) {
      const tab = cosoTab.tab as TabNumber
      const countId = `B22A-T${tab}-count`
      const countItem = allResponses.value.get(countId)
      const count = parseInt(countItem?.remark || '0', 10)

      for (let i = 1; i <= count; i++) {
        const conclusionId = `B22A-T${tab}-item-${i}-conclusion`
        const conclusionItem = allResponses.value.get(conclusionId)
        if (!conclusionItem?.conclusion) return false
      }
    }

    // Condition (b): overallConclusion is set
    if (!overallConclusion.value) return false

    return true
  })

  // ─── pendingItems ──────────────────────────────────────────────────────

  const pendingItems: ComputedRef<string[]> = computed(() => {
    const items: string[] = []

    for (const cosoTab of COSO_TABS) {
      const tab = cosoTab.tab as TabNumber
      const countId = `B22A-T${tab}-count`
      const countItem = allResponses.value.get(countId)
      const count = parseInt(countItem?.remark || '0', 10)

      let incompleteCount = 0
      for (let i = 1; i <= count; i++) {
        const conclusionId = `B22A-T${tab}-item-${i}-conclusion`
        const conclusionItem = allResponses.value.get(conclusionId)
        if (!conclusionItem?.conclusion) {
          incompleteCount++
        }
      }

      if (incompleteCount > 0) {
        items.push(`${cosoTab.label}：${incompleteCount} 项检查项未设置结论`)
      }
    }

    if (!overallConclusion.value) {
      items.push('整体结论未设置')
    }

    return items
  })

  // ─── reviewInfo ────────────────────────────────────────────────────────

  const reviewInfo: ComputedRef<{ reviewer: string; date: string } | null> = computed(() => {
    if (!isReviewed.value) return null

    const item = allResponses.value.get('B22A-review-sign')
    if (!item) return null

    return {
      reviewer: item.remark || '',
      date: item.wp_ref || '',
    }
  })

  // ─── doReview ──────────────────────────────────────────────────────────

  async function doReview(): Promise<void> {
    const userName = '当前用户' // placeholder — actual user from auth context

    const today = new Date()
    const dateStr = [
      today.getFullYear(),
      String(today.getMonth() + 1).padStart(2, '0'),
      String(today.getDate()).padStart(2, '0'),
    ].join('-')

    const item: ChecklistItem = {
      item_id: 'B22A-review-sign',
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

    // Determine amendment index N by counting existing B22A-amend-{N}-reason items
    let n = 0
    for (const key of allResponses.value.keys()) {
      const match = key.match(/^B22A-amend-(\d+)-reason$/)
      if (match) {
        const idx = parseInt(match[1], 10)
        if (idx >= n) n = idx + 1
      }
    }

    // Save amendment reason
    const reasonItem: ChecklistItem = {
      item_id: `B22A-amend-${n}-reason`,
      conclusion: null,
      remark: trimmed,
      wp_ref: null,
    }

    // Reset review sign
    const resetReview: ChecklistItem = {
      item_id: 'B22A-review-sign',
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

export default useB22AReview
