/**
 * 客户入账凭证选择（spec voucher-workflow-linkage-lineage-closure R5.1 / R5.2，design §7.1）
 *
 * 原先没有自动匹配候选时要用户粘贴凭证键 JSON（`["2025","001","2025-12-31","记","0008"]`），实际没人会填。
 * 改为按凭证号（可加日期）查当前账套的凭证分录，确认是哪一张后加入；提交时取各张的凭证键。
 */
import Decimal from 'decimal.js'
import { amountString, normText, voucherKeyString, voucherLabel } from '@/utils/voucherIdentity'
import { migrationPendingMessage } from '@/utils/migrationPending'

/** 已选的一张客户入账凭证（提交只用 voucher_key，其余供列表显示） */
export interface PickedBookingVoucher {
  voucher_key: string
  /** 称呼：FY-0003 / 0003 */
  label: string
  voucher_date: string
  line_count: number
  /** 借方合计（两位小数串） */
  debit_total: string
  summary: string
}

/** 后端一次最多收 100 张（MarkClientBookingRequest.voucher_keys max_length=100） */
export const BOOKING_VOUCHER_MAX = 100

export const VOUCHER_NOT_IN_DATASET = '当前账套没有这张凭证'

/** 一张凭证的分录 → 已选条目；分录为空返回 null（当前账套没有这张凭证） */
export function pickedFromLines(lines: Array<Record<string, unknown>>, year: number): PickedBookingVoucher | null {
  const first = lines[0]
  if (!first) return null
  const key = normText(first.voucher_key) || voucherKeyString(first, year)
  const debit = lines.reduce((sum, line) => sum.plus(new Decimal(amountString(line.debit_amount))), new Decimal(0))
  return {
    voucher_key: key,
    label: voucherLabel(first.voucher_type, first.voucher_no),
    voucher_date: normText(first.voucher_date).slice(0, 10),
    line_count: lines.length,
    debit_total: amountString(debit),
    summary: normText(lines.find(line => normText(line.summary))?.summary),
  }
}

/**
 * 客户入账建议对应的分录组（R5.3）：当前页有就用；不在当前页时用 `fetchFocused` 取它所在的那一页
 * （列表接口按 focus_entry_group_id 定位，每页 1 条即本组）。找不到返回 null（已删除或不在本年度）；
 * 取数失败返回 undefined（全局提示已说明，调用方不再提示）。
 */
export async function resolveSuggestionEntry<T extends { entry_group_id: string }>(
  groupId: string,
  currentPage: readonly T[],
  fetchFocused: (groupId: string) => Promise<{ items: T[] }>,
): Promise<T | null | undefined> {
  const onPage = currentPage.find(entry => entry.entry_group_id === groupId)
  if (onPage) return onPage
  try {
    const page = await fetchFocused(groupId)
    return (page?.items ?? []).find(entry => entry.entry_group_id === groupId) ?? null
  } catch {
    return undefined
  }
}

/** 查凭证失败的原因（409 多张凭证由调用方列候选，不走这里） */
export function voucherLookupFailureText(err: unknown): string {
  const pending = migrationPendingMessage(err)
  if (pending) return pending
  const res = (err as { response?: { status?: number; data?: Record<string, unknown> } } | null)?.response
  if (res?.status === 404) return VOUCHER_NOT_IN_DATASET
  if (res?.status === 403) return '没有本项目的查看权限'
  const detail = (res?.data?.detail ?? res?.data?.message) as unknown
  if (typeof detail === 'string' && detail) return detail
  if (detail && typeof detail === 'object' && typeof (detail as { message?: unknown }).message === 'string') {
    return String((detail as { message: string }).message)
  }
  return res ? '查找凭证失败，请稍后重试' : '网络连接失败，请检查网络'
}
