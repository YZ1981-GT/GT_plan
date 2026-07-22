/**
 * G11 附注披露 — 用户确认后从 G11-1/G11-2 同步至上市/国企附注
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { applyG11DisclosurePullToResponses } from './g11DisclosureFromAdj'
import type { ChecklistResponse } from './useF1FormData'

export const G11_OFFER_DISCLOSURE_PULL_EVENT = 'g11:offer-disclosure-pull'

export function dispatchG11OfferDisclosurePull(source?: string): void {
  try {
    window.dispatchEvent(new CustomEvent(G11_OFFER_DISCLOSURE_PULL_EVENT, {
      detail: { source, timestamp: Date.now() },
    }))
  } catch { /* silent */ }
}

/** 弹窗确认后同步两套附注；用户取消返回 false */
export async function offerG11DisclosurePull(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  prompt?: string,
): Promise<boolean> {
  try {
    await ElMessageBox.confirm(
      prompt ?? 'G11-1/G11-2 已更新。是否同步更新附注披露（上市/国企）分项金额？',
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
  const batch = applyG11DisclosurePullToResponses(responses, debouncedSave)
  if (batch.usedResidual) {
    ElMessage.warning(batch.summary)
  } else {
    ElMessage.success(`附注已同步：${batch.summary}`)
  }
  return true
}

export function promptForG11DisclosureSource(source?: string): string {
  if (source === 'G11-3') {
    return 'G11-3 调整已回写 G11-1/G11-2。是否同步更新附注披露（上市/国企）分项金额？'
  }
  if (source === 'G11-2') {
    return 'G11-2 明细已更新。是否同步更新附注披露（上市/国企）分项金额？'
  }
  if (source === 'G11-1') {
    return 'G11-1 审定已更新。是否同步更新附注披露（上市/国企）分项金额？'
  }
  return '是否同步更新附注披露（上市/国企）分项金额？'
}
