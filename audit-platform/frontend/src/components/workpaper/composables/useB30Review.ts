/**
 * useB30Review — B30 现场经理复核签字/只读状态/Amendment机制
 *
 * Spec: .kiro/specs/b30-group-audit/
 * Task: 2.3
 *
 * 职责：
 * - 复核状态计算（isReviewed / isReadonly / canReview）
 * - 待完成事项清单（pendingItems）
 * - 复核信息（reviewInfo）
 * - 现场经理签字操作（doReview）
 * - Amendment 修改机制（startAmendment）
 *
 * canReview 条件：
 * - 所有组成部分 Classification 非空
 * - 所有组成部分 Scope_Type 非空
 * - 所有"重要组成部分"的 Independence_Confirmation 为"已确认"或"不适用"
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse, SaveFn } from './useB30FormData'
import type { ScopeDashboardStats, ComponentEntity } from './useB30GroupAudit'
import { generateB30ItemId } from './useB30GroupAudit'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useB30Review(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistResponse>>,
  components: ComputedRef<ComponentEntity[]>,
  externalReadonly: Ref<boolean>,
  saveImmediate: SaveFn
) {
  // ─── isReviewed ────────────────────────────────────────────────────────

  const isReviewed: ComputedRef<boolean> = computed(() => {
    const item = allResponses.value.get(generateB30ItemId('review-sign'))
    return item?.conclusion === 'Y'
  })

  // ─── isReadonly ────────────────────────────────────────────────────────

  const isReadonly: ComputedRef<boolean> = computed(() => {
    return externalReadonly.value || isReviewed.value
  })

  // ─── canReview ─────────────────────────────────────────────────────────

  const canReview: ComputedRef<boolean> = computed(() => {
    const comps = components.value
    if (comps.length === 0) return false

    for (const comp of comps) {
      // All components must have a classification
      if (!comp.classification) return false

      // All components must have a scope type
      if (!comp.scopeType) return false

      // Significant components must have independence confirmed
      if (comp.classification === '重要组成部分') {
        if (comp.independence !== '已确认' && comp.independence !== '不适用') {
          return false
        }
      }
    }
    return true
  })

  // ─── pendingItems ──────────────────────────────────────────────────────

  const pendingItems: ComputedRef<string[]> = computed(() => {
    const items: string[] = []
    const comps = components.value

    for (const comp of comps) {
      if (!comp.classification) {
        items.push(`${comp.name || `组成部分${comp.id}`}：未确定分类`)
      }
      if (!comp.scopeType) {
        items.push(`${comp.name || `组成部分${comp.id}`}：未确定审计范围`)
      }
      if (comp.classification === '重要组成部分' && comp.independence !== '已确认' && comp.independence !== '不适用') {
        items.push(`${comp.name || `组成部分${comp.id}`}：独立性未确认`)
      }
    }

    return items
  })

  // ─── reviewInfo ────────────────────────────────────────────────────────

  const reviewInfo: ComputedRef<{ reviewer: string; date: string } | null> = computed(() => {
    if (!isReviewed.value) return null

    const item = allResponses.value.get(generateB30ItemId('review-sign'))
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
      item_id: generateB30ItemId('review-sign'),
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

    // Determine amendment index by counting existing B30-amend-{k}-reason items
    let k = 0
    for (const key of allResponses.value.keys()) {
      const match = key.match(/^B30-amend-(\d+)-reason$/)
      if (match) {
        const idx = parseInt(match[1], 10)
        if (idx >= k) k = idx + 1
      }
    }

    // Save amendment reason
    const reasonItem: ChecklistItem = {
      item_id: generateB30ItemId('amend', undefined, 'reason', k),
      conclusion: null,
      remark: trimmed,
      wp_ref: null,
    }

    // Reset review sign
    const resetReview: ChecklistItem = {
      item_id: generateB30ItemId('review-sign'),
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

export default useB30Review
