/** E1 非公式附注章节的唯一请求计划，供真实 Tab 与 headless provider 共用。 */
import {
  buildE1SyncPayload,
  E1_DISCLOSURE_SHEET_NAME,
  type E1DisclosureSnapshot,
  type E1MainRowLike,
  type E1NoteSectionLike,
  type E1SyncPayload,
} from './e1NoteSectionMap'
import { buildE1FxSyncPayload, type E1FxSyncPayload } from './e1FxNoteSectionMap'
import {
  buildRestrictedAssetsPayloads,
  RESTRICTED_ASSETS_OWNERS,
  summarizeRestrictedRows,
  type RestrictedAssetsPayload,
} from './restrictedAssetsNoteSectionMap'
import type { E1ForeignCurrencyRow, E1Variant } from './e1DisclosureTabState'
import type { E1RestrictedRow } from './e1RestrictedScope'

export type E1PlannedPayload = E1SyncPayload | E1FxSyncPayload | RestrictedAssetsPayload
export type E1PlanKind = 'main' | 'fx' | 'restricted'

export interface E1SyncPlanItem {
  kind: E1PlanKind
  payload: E1PlannedPayload & { year?: number }
  rowScopeLabel?: '外币货币性项目' | '受限资产'
}

export interface E1DisclosurePlanInput {
  variant: E1Variant
  wpId: string
  year?: number
  applicableStandards: readonly string[] | null | undefined
  mainRows?: readonly E1MainRowLike[]
  /** undefined=无可信来源，不管理②表；[]=可信来源明确为空。 */
  restrictedRows?: readonly E1RestrictedRow[]
  noteSections?: readonly E1NoteSectionLike[]
  foreignCurrencyRows?: readonly E1ForeignCurrencyRow[]
}

function withYear<T extends E1PlannedPayload>(payload: T, year?: number): T & { year?: number } {
  return year == null ? payload : { ...payload, year }
}

function hasMainPayloadWork(payload: E1SyncPayload): boolean {
  const data = payload.sub_table_data
  const tableKeys = Object.keys(data).filter(key => !key.startsWith('_'))
  const texts = Array.isArray(data._note_texts) ? data._note_texts : []
  const removed = Array.isArray(data._removed_table_keys) ? data._removed_table_keys : []
  return tableKeys.length > 0 || texts.length > 0 || removed.length > 0
}

export function buildE1DisclosureSyncPlan(input: E1DisclosurePlanInput): E1SyncPlanItem[] {
  const restrictedRows = input.restrictedRows?.map(row => ({
    item: row.label,
    openingAmount: row.openingAmount,
    endingAmount: row.endingAmount,
    reason: row.reason,
  }))
  const snapshot: E1DisclosureSnapshot = {
    mainRows: [...(input.mainRows ?? [])],
    restrictedRows,
    noteSections: [...(input.noteSections ?? [])],
  }
  const main = buildE1SyncPayload(
    input.variant,
    input.wpId,
    input.applicableStandards,
    snapshot,
    { mainTable: false },
  )
  const out: E1SyncPlanItem[] = []
  if (hasMainPayloadWork(main)) {
    out.push({ kind: 'main', payload: withYear(main, input.year) })
  }

  const fx = buildE1FxSyncPayload(
    input.variant,
    input.wpId,
    input.applicableStandards,
    {
      fxRows: (input.foreignCurrencyRows ?? []).map(row => ({
        groupId: row.groupId,
        currency: row.currency,
        isGroup: row.isGroup,
        endForeign: row.endForeign,
        endRate: row.endRate,
        endRmb: row.endRmb,
      })),
    },
  )
  if (fx) {
    out.push({ kind: 'fx', payload: withYear(fx, input.year), rowScopeLabel: '外币货币性项目' })
  }

  if (input.restrictedRows && input.restrictedRows.length > 0) {
    const restricted = buildRestrictedAssetsPayloads(
      input.variant,
      input.wpId,
      input.applicableStandards,
      {
        ownerRowCode: 'BS-002',
        rows: summarizeRestrictedRows(
          RESTRICTED_ASSETS_OWNERS['BS-002'],
          input.restrictedRows.map(row => ({
            endAmount: row.endingAmount,
            priorAmount: row.openingAmount,
            reason: row.reason,
          })),
        ),
      },
      E1_DISCLOSURE_SHEET_NAME,
    )
    out.push(...restricted.map(payload => ({
      kind: 'restricted' as const,
      payload: withYear(payload, input.year),
      rowScopeLabel: '受限资产' as const,
    })))
  }
  return out
}
