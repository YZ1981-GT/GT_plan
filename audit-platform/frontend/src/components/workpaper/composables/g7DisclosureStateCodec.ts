/** G7 披露状态的唯一序列化/恢复口径，供真实 Tab 与离屏 provider 共用。 */
import {
  createG7ListedDisclosureState,
  type G7DisclosureRow as ListedRow,
  type G7ListedDisclosureState,
} from '../g7-long-term-equity-main/disclosure/g7ListedDisclosureModel'
import {
  createG7SoeDisclosureState,
  type G7DisclosureRow as SoeRow,
  type G7SoeDisclosureState,
} from '../g7-long-term-equity-main/disclosure/g7SoeDisclosureModel'

export const G7_LISTED_RESPONSE_KEY = 'G7-main-disclosure-listed-v2'
export const G7_SOE_RESPONSE_KEY = 'G7-main-disclosure-soe-v2'

type SavedResponse = { remark?: unknown } | undefined
type ResponseMap = ReadonlyMap<string, SavedResponse>

function cloneRows<T extends ListedRow | SoeRow>(rows: readonly T[]): T[] {
  return rows.map(row => ({
    ...row,
    values: { ...(row.values ?? {}) },
    sumRows: row.sumRows ? [...row.sumRows] : undefined,
    diffRows: row.diffRows ? [...row.diffRows] as [string, string] : undefined,
  }))
}

function cloneSlots(slots: Record<string, string[]> | undefined): Record<string, string[]> {
  return Object.fromEntries(
    Object.entries(slots ?? {}).map(([key, names]) => [key, [...names]]),
  )
}

/** 旧版 previouslySyncedTables 只接受读取、不再写回；删除基线已迁到附注行内 owner ledger。 */
export function serialiseG7ListedState(
  state: G7ListedDisclosureState,
  updatedAt = new Date().toISOString(),
): G7ListedDisclosureState {
  return {
    version: 2,
    tables: Object.fromEntries(
      Object.entries(state.tables).map(([key, rows]) => [key, cloneRows(rows)]),
    ),
    texts: { ...state.texts },
    updatedAt,
    entitySlots: cloneSlots(state.entitySlots),
  }
}
export function serialiseG7SoeState(
  state: G7SoeDisclosureState,
  updatedAt = new Date().toISOString(),
): G7SoeDisclosureState {
  return {
    version: 2,
    tables: Object.fromEntries(
      Object.entries(state.tables).map(([key, rows]) => [key, cloneRows(rows)]),
    ),
    texts: { ...state.texts },
    updatedAt,
    entitySlots: cloneSlots(state.entitySlots),
  }
}

export function applyG7ListedSavedState(
  target: G7ListedDisclosureState,
  saved: Partial<G7ListedDisclosureState>,
): boolean {
  if (saved.version !== 2) return false
  if (saved.tables && typeof saved.tables === 'object') {
    for (const [tableId, rows] of Object.entries(saved.tables)) {
      if (Array.isArray(rows) && tableId in target.tables) target.tables[tableId] = cloneRows(rows)
    }
  }
  if (saved.texts && typeof saved.texts === 'object') Object.assign(target.texts, saved.texts)
  if (saved.entitySlots && typeof saved.entitySlots === 'object') {
    target.entitySlots = cloneSlots(saved.entitySlots)
  }
  return true
}

export function applyG7SoeSavedState(
  target: G7SoeDisclosureState,
  saved: Partial<G7SoeDisclosureState>,
): boolean {
  if (saved.version !== 2) return false
  if (saved.tables && typeof saved.tables === 'object') {
    for (const [tableId, rows] of Object.entries(saved.tables)) {
      if (Array.isArray(rows) && tableId in target.tables) target.tables[tableId] = cloneRows(rows)
    }
  }
  if (saved.texts && typeof saved.texts === 'object') Object.assign(target.texts, saved.texts)
  if (saved.entitySlots && typeof saved.entitySlots === 'object') {
    if (!target.entitySlots) target.entitySlots = {}
    Object.assign(target.entitySlots, cloneSlots(saved.entitySlots))
  }
  return true
}
function parseRemark<T>(
  target: T,
  remark: unknown,
  apply: (target: T, saved: any) => boolean,
): boolean {
  if (typeof remark !== 'string' || !remark.trim()) return false
  try {
    return apply(target, JSON.parse(remark))
  } catch {
    return false
  }
}

export function parseG7ListedSavedRemark(
  target: G7ListedDisclosureState,
  remark: unknown,
): boolean {
  return parseRemark(target, remark, applyG7ListedSavedState)
}

export function parseG7SoeSavedRemark(
  target: G7SoeDisclosureState,
  remark: unknown,
): boolean {
  return parseRemark(target, remark, applyG7SoeSavedState)
}

export function restoreG7ListedState(responses: ResponseMap): {
  state: G7ListedDisclosureState
  hasSource: boolean
} {
  const state = createG7ListedDisclosureState()
  return {
    state,
    hasSource: parseG7ListedSavedRemark(state, responses.get(G7_LISTED_RESPONSE_KEY)?.remark),
  }
}

export function restoreG7SoeState(responses: ResponseMap): {
  state: G7SoeDisclosureState
  hasSource: boolean
} {
  const state = createG7SoeDisclosureState()
  return {
    state,
    hasSource: parseG7SoeSavedRemark(state, responses.get(G7_SOE_RESPONSE_KEY)?.remark),
  }
}
