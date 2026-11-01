import type { InternalAxiosRequestConfig } from 'axios'

export interface BookedAdjustmentImpact {
  entry_group_id: string
  adjustment_no?: string | null
  description?: string | null
  account_codes?: string[]
}

function objectOf(value: unknown): Record<string, any> | null {
  return value && typeof value === 'object' ? value as Record<string, any> : null
}

/** 兼容 FastAPI detail 与平台统一信封，识别发布门的客户已入账确认清单。 */
export function parseBookedAdjustmentAckError(data: unknown): BookedAdjustmentImpact[] | null {
  const root = objectOf(data)
  const candidates = [root, objectOf(root?.detail), objectOf(root?.message), objectOf(root?.data)]
  const payload = candidates.find((item) => item?.error_code === 'BOOKED_ADJUSTMENTS_UNACKED')
  if (!payload || !Array.isArray(payload.groups)) return null
  const groups = payload.groups.filter((item: unknown) => {
    const row = objectOf(item)
    return typeof row?.entry_group_id === 'string' && row.entry_group_id.length > 0
  }) as BookedAdjustmentImpact[]
  return groups.length ? groups : null
}

/** Axios 已 transform 的 data 可能是 JSON 字符串；重发时保留原 body/publish_token。 */
export function addBookedAdjustmentAck(
  config: InternalAxiosRequestConfig,
  groups: BookedAdjustmentImpact[],
): InternalAxiosRequestConfig {
  const body = typeof config.data === 'string' ? JSON.parse(config.data) : { ...(config.data || {}) }
  body.booked_adjustments_ack = [...new Set(groups.map((item) => item.entry_group_id))]
  return { ...config, data: body }
}

export function bookedAdjustmentConfirmText(groups: BookedAdjustmentImpact[]): string {
  const listed = groups.slice(0, 5).map((item) => item.adjustment_no || item.entry_group_id.slice(0, 8)).join('、')
  const tail = groups.length > 5 ? ` 等 ${groups.length} 笔` : ''
  return `涉及客户已入账调整：${listed}${tail}。请确认本底稿的审定表、明细调整列和调整页签已移除这些金额，再继续发布。`
}
