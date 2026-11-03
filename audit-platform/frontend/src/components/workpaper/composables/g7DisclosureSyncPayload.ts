/** G7 多章节附注请求体的唯一构建口径，供真实 Tab 与离屏 provider 逐字节复用。 */
import {
  G7_LISTED_DISCLOSURE_SECTIONS,
  buildG7ListedColumns,
  buildG7ListedSyncPayloads,
  type G7ListedDisclosureState,
} from '../g7-long-term-equity-main/disclosure/g7ListedDisclosureModel'
import {
  G7_SOE_DISCLOSURE_SECTIONS,
  buildG7SoeColumns,
  buildG7SoeSyncPayloads,
  type G7SoeDisclosureState,
} from '../g7-long-term-equity-main/disclosure/g7SoeDisclosureModel'
import { pickColumnsForPayload } from '../g7-long-term-equity-main/disclosure/g7PayloadColumns'

export const G7_OWNER_KEYS = {
  listed: 'G7:listed',
  soe: 'G7:soe',
} as const

export interface G7BatchSyncItem {
  sheet_name: string
  section_id: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, unknown[]>
  owner_key?: string
  replace_owned_tables: boolean
}

export interface G7BatchSyncRequest {
  wp_id: string
  current_standard: 'listed' | 'soe'
  year?: number
  require_all_applied: true
  items: G7BatchSyncItem[]
}

function withoutLegacyClientDiff(data: Record<string, unknown>): Record<string, unknown> {
  const next = { ...data }
  // 删除差集只能由附注行内 owner ledger 计算；旧底稿 JSON 里的客户端基线不再可信。
  delete next._removed_table_keys
  return next
}

function tableSections(
  sections: ReadonlyArray<{ noteSectionId: string; tables?: readonly unknown[] }>,
): Set<string> {
  return new Set(
    sections
      .filter(section => (section.tables ?? []).length > 0)
      .map(section => section.noteSectionId),
  )
}

export function buildG7ListedBatchRequest(input: {
  wpId: string
  year?: number
  state: G7ListedDisclosureState
}): G7BatchSyncRequest {
  const payloads = buildG7ListedSyncPayloads(input.state)
  const columns = buildG7ListedColumns(input.state.entitySlots)
  const owned = tableSections(G7_LISTED_DISCLOSURE_SECTIONS)
  return {
    wp_id: input.wpId,
    current_standard: 'listed',
    ...(input.year == null ? {} : { year: input.year }),
    require_all_applied: true,
    items: payloads.map(payload => {
      const subTableData = withoutLegacyClientDiff(payload.subTableData)
      const replace = owned.has(payload.noteSectionId)
      return {
        sheet_name: payload.sheetName,
        section_id: payload.noteSectionId,
        sub_table_data: subTableData,
        columns: pickColumnsForPayload(subTableData, columns),
        ...(replace ? { owner_key: G7_OWNER_KEYS.listed } : {}),
        replace_owned_tables: replace,
      }
    }),
  }
}

export function buildG7SoeBatchRequest(input: {
  wpId: string
  year?: number
  state: G7SoeDisclosureState
}): G7BatchSyncRequest {
  const payloads = buildG7SoeSyncPayloads(input.state)
  const columns = buildG7SoeColumns(input.state.entitySlots)
  const owned = tableSections(G7_SOE_DISCLOSURE_SECTIONS)
  return {
    wp_id: input.wpId,
    current_standard: 'soe',
    ...(input.year == null ? {} : { year: input.year }),
    require_all_applied: true,
    items: payloads.map(payload => {
      const subTableData = withoutLegacyClientDiff(payload.subTableData)
      const replace = owned.has(payload.noteSectionId)
      return {
        sheet_name: payload.sheetName,
        section_id: payload.noteSectionId,
        sub_table_data: subTableData,
        columns: pickColumnsForPayload(subTableData, columns),
        ...(replace ? { owner_key: G7_OWNER_KEYS.soe } : {}), // gitleaks:allow — 业务 owner 命名空间，不是凭据
        replace_owned_tables: replace,
      }
    }),
  }
}
