/**
 * useB23Review — B23 现场经理复核签字/只读状态/Amendment机制
 *
 * Spec: .kiro/specs/b23-process-control/
 * Task: 2.3
 *
 * 职责：
 * - 复核状态计算（isReviewed / isReadonly / canReview）
 * - 待完成事项清单（pendingItems）— 未完成 Process_Conclusion 的适用流程 + 缺穿行结论的控制点
 * - 复核信息（reviewInfo）
 * - 现场经理签字操作（doReview）
 * - Amendment 修改机制（startAmendment）
 *
 * canReview 条件：
 * - 所有适用流程的 Process_Conclusion 均已选择（非 null）
 * - 所有适用流程中 Understanding_Method 包含"穿行测试"的控制点均有穿行测试结论
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useB23FormData'
import type { B23CycleCard } from './useB23ProcessControl'

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

// ─── Composable ──────────────────────────────────────────────────────────────

export function useB23Review(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistResponse>>,
  cycles: ComputedRef<B23CycleCard[]>,
  externalReadonly: Ref<boolean>,
  saveImmediate: SaveFn
) {
  // ─── isReviewed ────────────────────────────────────────────────────────

  const isReviewed: ComputedRef<boolean> = computed(() => {
    const item = allResponses.value.get('B23-review-sign')
    return item?.conclusion === 'Y'
  })

  // ─── isReadonly ────────────────────────────────────────────────────────

  const isReadonly: ComputedRef<boolean> = computed(() => {
    return externalReadonly.value || isReviewed.value
  })

  // ─── canReview ─────────────────────────────────────────────────────────

  const canReview: ComputedRef<boolean> = computed(() => {
    const cards = cycles.value
    for (const card of cards) {
      if (!card.applicable) continue

      // 所有适用循环必须有循环结论
      if (!card.conclusion) return false

      // 关键控制点必须有穿行测试（验设计）结论
      for (const cp of card.controlPoints) {
        if (cp.isKeyControl === '是' && card.walkthroughs[cp.index - 1]?.asDesigned == null) {
          return false
        }
        // 拟测试的控制点必须有控制测试（验运行）结论
        if (cp.doControlTest === '是' && card.controlTests[cp.index - 1]?.operatingEffective == null) {
          return false
        }
      }
    }
    return true
  })

  // ─── pendingItems ──────────────────────────────────────────────────────

  const pendingItems: ComputedRef<string[]> = computed(() => {
    const items: string[] = []
    const cards = cycles.value

    for (const card of cards) {
      if (!card.applicable) continue

      if (!card.conclusion) {
        items.push(`${card.name}：未选择循环结论`)
      }

      for (const cp of card.controlPoints) {
        const label = cp.ctrlName || cp.ctrlNo || `控制点 ${cp.index}`
        if (cp.isKeyControl === '是' && card.walkthroughs[cp.index - 1]?.asDesigned == null) {
          items.push(`${card.name} - ${label}：缺穿行测试结论`)
        }
        if (cp.doControlTest === '是' && card.controlTests[cp.index - 1]?.operatingEffective == null) {
          items.push(`${card.name} - ${label}：缺控制测试结论`)
        }
      }
    }

    return items
  })

  // ─── reviewInfo ────────────────────────────────────────────────────────

  const reviewInfo: ComputedRef<{ reviewer: string; date: string } | null> = computed(() => {
    if (!isReviewed.value) return null

    const item = allResponses.value.get('B23-review-sign')
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
      item_id: 'B23-review-sign',
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

    // Determine amendment index by counting existing B23-amend-{k}-reason items
    let k = 0
    for (const key of allResponses.value.keys()) {
      const match = key.match(/^B23-amend-(\d+)-reason$/)
      if (match) {
        const idx = parseInt(match[1], 10)
        if (idx >= k) k = idx + 1
      }
    }

    // Save amendment reason
    const reasonItem: ChecklistItem = {
      item_id: `B23-amend-${k}-reason`,
      conclusion: null,
      remark: trimmed,
      wp_ref: null,
    }

    // Reset review sign
    const resetReview: ChecklistItem = {
      item_id: 'B23-review-sign',
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

export default useB23Review
