/**
 * L3 长期借款披露表 → 附注同步的载荷入参与请求体（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * `L3TabDisclosureListed` / `L3TabDisclosureSoe` 原在同步函数里内联「`useL3Disclosure` 的计算结果 → `buildL3SyncPayload`
 * 入参」与请求体拼装（上市单节 `sync-from-workpaper`，国企两节 `sync-batch-from-workpaper`），原样抽到这里：Tab 与离屏
 * provider 调同一个入参函数 + 同一个 `buildL3SyncPayload` + 同一个请求体函数。只做计算；发送、提示、事件留在调用方。
 */
import type { L3SyncItem, L3SyncPayloadOptions } from './l3NoteSectionMap'
import type { L3CurrentPortionRow, L3DisclosureRow } from './useL3Disclosure'

/** `useL3Disclosure` 返回值里同步要用的几项（国企 Tab 不取抵押质押说明） */
export interface L3DisclosureSyncSource {
  classificationRows: { readonly value: L3DisclosureRow[] }
  currentPortionRows: { readonly value: L3CurrentPortionRow[] }
  rateRange: (rowKey: string, period: 'end' | 'prior') => string
  propertyNote?: { readonly value: string }
  conclusion: { readonly value: string }
}

/** 底稿条目里的 sheet 名（两版各一，与 Tab 原写法一致） */
export const L3_SYNC_SHEET_NAME = { listed: 'L3-note-listed', soe: 'L3-note-soe' } as const

/** `buildL3SyncPayload` 入参：国企 八、49 不推抵押质押说明（Tab 原写法即传空串） */
export function buildL3SyncOptions(variant: 'listed' | 'soe', src: L3DisclosureSyncSource): L3SyncPayloadOptions {
  return {
    variant,
    classificationRows: src.classificationRows.value,
    currentPortionRows: src.currentPortionRows.value,
    rateRange: src.rateRange,
    propertyNote: variant === 'listed' ? (src.propertyNote?.value ?? '') : '',
    conclusion: src.conclusion.value,
  }
}

/** 上市：`sync-from-workpaper` 请求体（只推 五、45 一节；键序与 Tab 原写法一致） */
export function buildL3ListedSyncBody(wpId: string, item: L3SyncItem) {
  return { wp_id: wpId, sheet_name: L3_SYNC_SHEET_NAME.listed, current_standard: 'listed_standalone', ...item }
}

/** 国企：`sync-batch-from-workpaper` 请求体（Tab 一次发全部章节；离屏逐章节各发一次，item 形态相同） */
export function buildL3SoeBatchBody(wpId: string, items: readonly L3SyncItem[]) {
  return {
    wp_id: wpId,
    current_standard: 'soe_standalone',
    items: items.map((item) => ({ sheet_name: L3_SYNC_SHEET_NAME.soe, ...item })),
  }
}
