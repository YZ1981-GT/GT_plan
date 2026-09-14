/**
 * G10 附注披露 — 用户确认后从 G10-1/G10-2 同步至上市/国企附注
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { applyG10DisclosurePullToResponses } from './g10DisclosureFromAdj'
import type { ChecklistResponse } from './useF1FormData'

export const G10_OFFER_DISCLOSURE_PULL_EVENT = 'g10:offer-disclosure-pull'

export function dispatchG10OfferDisclosurePull(source?: string): void {
  try {
    window.dispatchEvent(new CustomEvent(G10_OFFER_DISCLOSURE_PULL_EVENT, {
      detail: { source, timestamp: Date.now() },
    }))
  } catch { /* silent */ }
}

/** 弹窗确认后同步两套附注；用户取消返回 false */
export async function offerG10DisclosurePull(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  auditYear: number | null,
  prompt?: string,
): Promise<boolean> {
  try {
    await ElMessageBox.confirm(
      prompt ?? 'G10-1 审定/调整已更新。是否同步更新附注披露（上市/国企）分项金额？',
      '同步附注披露',
      {
        confirmButtonText: '同步附注',
        cancelButtonText: '稍后手工带入',
        type: 'info',
      },
    )
  } catch {
    return false
  }
  const batch = applyG10DisclosurePullToResponses(responses, debouncedSave, auditYear)
  if (batch.usedResidual) {
    ElMessage.warning(batch.summary)
  } else {
    ElMessage.success(`附注已同步：${batch.summary}`)
  }
  return true
}
