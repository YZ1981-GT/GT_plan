/**
 * L2 应付利息披露表 → 附注同步的快照与请求体（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * `L2TabDisclosureListed` / `L2TabDisclosureSoe` 原在同步函数里内联「分类表 / 逾期表 → 载荷行」的映射与请求体拼装，
 * 原样抽到这里：Tab 与离屏 provider 调同一个快照函数 + 同一个 `buildL2SyncPayload` + 同一个请求体函数 ⇒ 两条路径发出
 * 逐字节相同的请求体。只做计算；发送、提示、事件留在调用方。
 *
 * 写入章节与 K3 / M1 共用（五、42 / 八、42）：载荷只带 L2 的两张子表、不带 `_removed_table_keys`（见 `buildL2SyncPayload`）。
 */
import {
  L2_DISCLOSURE_SHEET_NAME,
  L2_NOTE_SECTION,
  type L2DisclosureVariant,
  type L2InterestRow,
  type L2OverdueRow,
  type L2SyncPayload,
} from './l2NoteSectionMap'
import type { DisclosureRow, OverdueDisclosureRow } from './useL2Disclosure'

/** 分类表（含合计）/ 逾期表 → `buildL2SyncPayload` 的两组入参（与 Tab 原内联映射逐字段一致） */
export function buildL2DisclosureSnapshot(
  disclosureTableData: readonly DisclosureRow[],
  overdueRows: readonly OverdueDisclosureRow[],
): { interestRows: L2InterestRow[]; overdueRows: L2OverdueRow[] } {
  return {
    interestRows: disclosureTableData.map((r: DisclosureRow) => ({
      label: r.label,
      endAmount: r.endAmount ?? 0,
      priorAmount: r.priorAmount ?? 0,
    })),
    overdueRows: overdueRows.map((r: any) => ({
      label: r.borrower ?? '',
      overdueAmount: r.overdueAmount ?? 0,
      overdueReason: r.overdueReason ?? '',
    })),
  }
}

/** `POST …/disclosure-notes/sync-from-workpaper` 请求体（键序与 Tab 原写法一致） */
export function buildL2SyncRequestBody(variant: L2DisclosureVariant, wpId: string, payload: L2SyncPayload) {
  return {
    wp_id: wpId,
    sheet_name: L2_DISCLOSURE_SHEET_NAME[variant],
    section_id: L2_NOTE_SECTION[variant],
    current_standard: variant === 'listed' ? 'listed_standalone' : 'soe_standalone',
    sub_table_data: payload.sub_table_data,
    columns: payload._sub_table_columns,
  }
}
