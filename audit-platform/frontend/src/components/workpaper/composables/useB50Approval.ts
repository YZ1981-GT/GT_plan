/**
 * useB50Approval — B50 合伙人审批/只读状态/Amendment机制
 *
 * Spec: .kiro/specs/b50-risk-assessment/
 * Task: 2.3
 *
 * 职责：
 * - 审批状态计算（isApproved / isReadonly / canApprove）
 * - 待完成事项清单（pendingItems）
 * - 签字信息（approvalInfo）
 * - 合伙人签字操作（doApproval）
 * - Amendment 修改机制（startAmendment）
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useB50FormData'
import type { SpecialRiskCell } from './useB50RiskMatrix'

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

// ─── Composable ──────────────────────────────────────────────────────────────

export function useB50Approval(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistResponse>>,
  incompleteAccounts: ComputedRef<string[]>,
  specialRiskCells: ComputedRef<SpecialRiskCell[]>,
  externalReadonly: Ref<boolean>,
  saveImmediate: SaveFn
) {
  // ─── isApproved ────────────────────────────────────────────────────────

  const isApproved: ComputedRef<boolean> = computed(() => {
    const item = allResponses.value.get('B50-approval-sign')
    return item?.conclusion === 'Y'
  })

  // ─── isReadonly ────────────────────────────────────────────────────────

  const isReadonly: ComputedRef<boolean> = computed(() => {
    return externalReadonly.value || isApproved.value
  })

  // ─── canApprove ────────────────────────────────────────────────────────

  const canApprove: ComputedRef<boolean> = computed(() => {
    // Condition (a): all accounts fully assessed
    if (incompleteAccounts.value.length > 0) return false

    // Condition (b): all special risk entries have response text
    for (const sr of specialRiskCells.value) {
      const responseItemId = `B50-T4-sr-${sr.account}-${sr.assertion}-response`
      const responseItem = allResponses.value.get(responseItemId)
      if (!responseItem?.remark?.trim()) return false
    }

    return true
  })

  // ─── pendingItems ──────────────────────────────────────────────────────

  const pendingItems: ComputedRef<string[]> = computed(() => {
    const items: string[] = []

    // Incomplete accounts
    for (const name of incompleteAccounts.value) {
      items.push(`科目「${name}」未完成认定评估`)
    }

    // Special risk without response
    for (const sr of specialRiskCells.value) {
      const responseItemId = `B50-T4-sr-${sr.account}-${sr.assertion}-response`
      const responseItem = allResponses.value.get(responseItemId)
      if (!responseItem?.remark?.trim()) {
        items.push(`特别风险「${sr.account}-${sr.assertion}」缺少应对程序`)
      }
    }

    return items
  })

  // ─── approvalInfo ──────────────────────────────────────────────────────

  const approvalInfo: ComputedRef<{ signer: string; date: string } | null> = computed(() => {
    if (!isApproved.value) return null

    const item = allResponses.value.get('B50-approval-sign')
    if (!item) return null

    return {
      signer: item.remark || '',
      date: item.wp_ref || '',
    }
  })

  // ─── doApproval ────────────────────────────────────────────────────────

  async function doApproval(): Promise<void> {
    const userName = '当前用户' // placeholder — actual user from auth context

    const today = new Date()
    const dateStr = [
      today.getFullYear(),
      String(today.getMonth() + 1).padStart(2, '0'),
      String(today.getDate()).padStart(2, '0'),
    ].join('-')

    const item: ChecklistItem = {
      item_id: 'B50-approval-sign',
      conclusion: 'Y',
      remark: userName,
      wp_ref: dateStr,
    }

    // Update local state
    allResponses.value.set(item.item_id, item)

    await saveImmediate([item])
  }

  // ─── startAmendment ────────────────────────────────────────────────────

  async function startAmendment(reason: string): Promise<void> {
    const trimmed = reason.trim()
    if (!trimmed) {
      throw new Error('Amendment 原因不能为空')
    }

    // Determine amendment index N by counting existing B50-amend-{N}-reason items
    let n = 0
    for (const key of allResponses.value.keys()) {
      const match = key.match(/^B50-amend-(\d+)-reason$/)
      if (match) {
        const idx = parseInt(match[1], 10)
        if (idx >= n) n = idx + 1
      }
    }

    // Save amendment reason
    const reasonItem: ChecklistItem = {
      item_id: `B50-amend-${n}-reason`,
      conclusion: null,
      remark: trimmed,
      wp_ref: null,
    }

    // Reset approval
    const resetApproval: ChecklistItem = {
      item_id: 'B50-approval-sign',
      conclusion: null,
      remark: null,
      wp_ref: null,
    }

    // Update local state
    allResponses.value.set(reasonItem.item_id, reasonItem)
    allResponses.value.set(resetApproval.item_id, resetApproval)

    await saveImmediate([reasonItem, resetApproval])
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    isApproved,
    isReadonly,
    canApprove,
    pendingItems,
    approvalInfo,
    doApproval,
    startAmendment,
  }
}

export default useB50Approval
