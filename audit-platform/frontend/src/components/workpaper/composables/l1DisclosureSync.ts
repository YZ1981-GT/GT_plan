/**
 * L1 短期借款披露表 → 附注同步的载荷入参与请求体（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * `L1TabDisclosureListed` / `L1TabDisclosureSoe` 原在同步函数里内联「`useL1DisclosureData` 的计算结果 → `buildL1SyncPayload`
 * 入参」与请求体拼装，原样抽到这里：Tab 与离屏 provider 调同一个入参函数 + 同一个 `buildL1SyncPayload` + 同一个请求体函数。
 * 只做计算；发送、提示、事件留在调用方。
 */
import { L1_NOTE_SECTION, type buildL1SyncPayload, type L1SyncPayloadOptions } from './l1NoteSectionMap'
import type { L1DisclosureCategoryRow, L1DisclosureOverdueRow } from '@/composables/useL1DisclosureData'

type L1Variant = L1SyncPayloadOptions['variant']

/** `useL1DisclosureData` 返回值里同步要用的四项 */
export interface L1DisclosureSyncSource {
  categoryRows: { readonly value: L1DisclosureCategoryRow[] }
  categoryTotal: { readonly value: { begin: number; end: number } }
  overdueRows: { readonly value: L1DisclosureOverdueRow[] }
  conclusionText: { readonly value: string }
}

/** 底稿条目里的 sheet 名（两版各一，与 Tab 原写法一致） */
export const L1_SYNC_SHEET_NAME = { listed: 'L1-note-listed', soe: 'L1-note-soe' } as const

/** `buildL1SyncPayload` 入参（分类表 / 合计 / 逾期表 / 审计结论） */
export function buildL1SyncOptions(variant: L1Variant, src: L1DisclosureSyncSource): L1SyncPayloadOptions {
  return {
    variant,
    categoryRows: src.categoryRows.value,
    categoryTotal: src.categoryTotal.value,
    overdueRows: src.overdueRows.value,
    conclusionText: src.conclusionText.value,
  }
}

/** `POST …/disclosure-notes/sync-from-workpaper` 请求体（键序与 Tab 原写法一致） */
export function buildL1SyncRequestBody(
  variant: L1Variant,
  wpId: string,
  payload: ReturnType<typeof buildL1SyncPayload>,
) {
  return {
    wp_id: wpId,
    sheet_name: L1_SYNC_SHEET_NAME[variant],
    section_id: L1_NOTE_SECTION[variant],
    current_standard: variant === 'listed' ? 'listed_standalone' : 'soe_standalone',
    sub_table_data: payload.sub_table_data,
    columns: payload.columns,
  }
}
