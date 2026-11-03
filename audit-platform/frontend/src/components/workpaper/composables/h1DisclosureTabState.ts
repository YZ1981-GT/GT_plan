/** H1 两版披露 Tab 与离屏 provider 共用的纯状态恢复。 */
import {
  H1_LISTED_DEFAULT_CATEGORIES,
  H1_LISTED_ITEM,
  H1_LISTED_MOVEMENT_ROWS,
  createDefaultGovSubsidy,
  createDefaultIdleRows,
  createDefaultLeaseRows,
  createDefaultSummary,
  emptyMovement,
  isMovementEmpty,
  num,
  seedMovementFromAdjudication,
  totalCellValue,
  type ClearingRow,
  type FullyDepRow,
  type H1ListedCategory,
  type MortgageRow,
  type TitleCertRow,
} from './h1ListedDisclosureModel'
import {
  H1_SOE_KEYS,
  createH1SoeDisclosureState,
  hydrateClearingRows,
  hydrateFullyDepRows,
  hydrateIdleRows,
  hydrateLayers,
  hydrateSummary,
  hydrateTitleRows,
  layersHaveAnyAmount,
  readSoeRemark,
  seedMovementFromDetailRows,
  type H1SoeDisclosureState,
  type H1SoeFullyDepRow,
} from './h1SoeDisclosureModel'
import type { H1ListedSyncSnapshot } from './h1DisclosureSyncPayload'

export type H1DisclosureResponses = ReadonlyMap<
  string,
  { remark?: unknown; conclusion?: unknown; value?: unknown } | undefined
>

function raw(responses: H1DisclosureResponses, itemId: string): unknown {
  const item = responses.get(itemId)
  return item?.remark ?? item?.conclusion ?? item?.value ?? null
}

function hasValue(responses: H1DisclosureResponses, itemIds: readonly string[]): boolean {
  return itemIds.some((itemId) => {
    const value = raw(responses, itemId)
    return value !== null && value !== undefined && value !== ''
  })
}
function parsed<T>(responses: H1DisclosureResponses, itemId: string, fallback: T): T {
  const value = raw(responses, itemId)
  if (value == null || value === '') return fallback
  if (typeof value !== 'string') return value as T
  try {
    return (JSON.parse(value) ?? fallback) as T
  } catch {
    return fallback
  }
}

function text(responses: H1DisclosureResponses, itemId: string): string {
  const value = raw(responses, itemId)
  return typeof value === 'string' ? value : ''
}

export interface H1ListedRestoredState {
  snapshot: H1ListedSyncSnapshot
  mortgageRows: MortgageRow[]
  fullyDepRows: FullyDepRow[]
  hasSource: boolean
}

export function restoreH1ListedState(responses: H1DisclosureResponses): H1ListedRestoredState {
  const summary = createDefaultSummary()
  const savedSummary = parsed<H1ListedSyncSnapshot['summary'] | null>(responses, H1_LISTED_ITEM.summary, null)
  if (Array.isArray(savedSummary)) {
    for (const saved of savedSummary) {
      const row = summary.find((item) => item.key === saved.key)
      if (row) Object.assign(row, saved)
    }
  }
  let categories: H1ListedCategory[] = H1_LISTED_DEFAULT_CATEGORIES.map((item) => ({ ...item }))
  const savedCategories = parsed<H1ListedCategory[] | null>(responses, H1_LISTED_ITEM.categories, null)
  if (Array.isArray(savedCategories) && savedCategories.length > 0) categories = savedCategories
  let movement = parsed<H1ListedSyncSnapshot['movement']>(responses, H1_LISTED_ITEM.movement, emptyMovement())
  const idle = parsed(responses, H1_LISTED_ITEM.idle, createDefaultIdleRows())
  const leaseSaved = parsed<any[] | null>(responses, H1_LISTED_ITEM.leaseOut, null)
    ?? parsed<any[] | null>(responses, H1_LISTED_ITEM.leaseOutLegacy, null)
  const leaseOut = Array.isArray(leaseSaved) && leaseSaved.length > 0
    ? leaseSaved.map((row, index) => ({
        rowId: row.rowId || `lease-${index}`,
        name: row.name || '',
        bookValue: num(row.bookValue ?? row.amount),
        isPreset: row.isPreset,
      }))
    : createDefaultLeaseRows()
  const titleCert = parsed<TitleCertRow[]>(responses, H1_LISTED_ITEM.titleCert, [
    { rowId: 'title-0', name: '', bookValue: 0, reason: '' },
    { rowId: 'title-1', name: '', bookValue: 0, reason: '' },
    { rowId: 'title-2', name: '', bookValue: 0, reason: '' },
  ])
  const clearing = parsed<ClearingRow[]>(responses, H1_LISTED_ITEM.clearing, [
    { rowId: 'clr-0', name: '', endBalance: 0, priorBalance: 0, reason: '' },
  ])
  const mortgageSaved = parsed<any[] | null>(responses, H1_LISTED_ITEM.mortgageRows, null)
    ?? parsed<any[] | null>(responses, H1_LISTED_ITEM.mortgageLegacy, null)
  const mortgageRows = Array.isArray(mortgageSaved) ? mortgageSaved.map((row, index) => ({
    rowId: row.rowId || `mort-${index}`,
    name: row.name || '',
    amount: num(row.amount),
    description: row.description || '',
    remark: row.remark || '',
  })) : []
  const govSubsidy = {
    ...createDefaultGovSubsidy(),
    ...parsed<Record<string, unknown>>(responses, H1_LISTED_ITEM.govSubsidy, {}),
  } as H1ListedSyncSnapshot['govSubsidy']
  const fullySaved = parsed<any[] | null>(responses, H1_LISTED_ITEM.fullyDepreciated, null)
  const fullyDepRows = Array.isArray(fullySaved) ? fullySaved.map((row, index) => ({
    rowId: row.rowId || `fdep-${index}`,
    name: row.name || '',
    cost: num(row.cost),
    remark: row.remark || '',
  })) : []

  if (isMovementEmpty(movement)) {
    const costRows = parsed<any[] | null>(responses, 'H1-1-cost-rows', null)
    const depRows = parsed<any[]>(responses, 'H1-1-dep-rows', [])
    if (Array.isArray(costRows)) {
      const seeded = seedMovementFromAdjudication(costRows, Array.isArray(depRows) ? depRows : [], categories)
      categories = seeded.categories
      movement = seeded.movement
    }
  }
  const fixedAssets = summary.find((row) => row.key === 'fixed_assets')
  if (fixedAssets && num(fixedAssets.endBalance) === 0) {
    const bookEnd = H1_LISTED_MOVEMENT_ROWS.find((row) => row.key === 'book_end')!
    const bookBegin = H1_LISTED_MOVEMENT_ROWS.find((row) => row.key === 'book_begin')!
    fixedAssets.endBalance = totalCellValue(movement, bookEnd, categories)
    fixedAssets.priorBalance = totalCellValue(movement, bookBegin, categories)
  }
  return {
    snapshot: {
      summary,
      categories,
      movement,
      idle,
      leaseOut,
      titleCert,
      clearing,
      govSubsidy,
      noteImpairment: text(responses, H1_LISTED_ITEM.noteImpairment),
      noteMortgage: text(responses, H1_LISTED_ITEM.noteMortgage),
      noteSale: text(responses, H1_LISTED_ITEM.noteSale),
      noteClearing: text(responses, H1_LISTED_ITEM.noteClearing),
    },
    mortgageRows,
    fullyDepRows,
    hasSource: hasValue(responses, [
      H1_LISTED_ITEM.summary,
      H1_LISTED_ITEM.categories,
      H1_LISTED_ITEM.movement,
      H1_LISTED_ITEM.idle,
      H1_LISTED_ITEM.leaseOut,
      H1_LISTED_ITEM.leaseOutLegacy,
      H1_LISTED_ITEM.titleCert,
      H1_LISTED_ITEM.clearing,
      H1_LISTED_ITEM.govSubsidy,
      H1_LISTED_ITEM.noteImpairment, H1_LISTED_ITEM.noteMortgage,
      H1_LISTED_ITEM.noteSale, H1_LISTED_ITEM.noteClearing, 'H1-1-cost-rows',
    ]),
  }
}

function parseSoeKey(responses: H1DisclosureResponses, key: keyof typeof H1_SOE_KEYS): unknown {
  const value = readSoeRemark((id) => responses.get(id) as any, key)
  if (value == null || value === '') return null
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}

export function restoreH1SoeState(responses: H1DisclosureResponses): {
  state: H1SoeDisclosureState
  fullyDepRows: H1SoeFullyDepRow[]
  hasSource: boolean
} {
  const state = createH1SoeDisclosureState()
  state.summary = hydrateSummary(parseSoeKey(responses, 'summary'))
  state.layers = hydrateLayers(parseSoeKey(responses, 'movement'))
  state.idleRows = hydrateIdleRows(parseSoeKey(responses, 'idle'))
  state.titleRows = hydrateTitleRows(parseSoeKey(responses, 'title'))
  state.clearingRows = hydrateClearingRows(parseSoeKey(responses, 'clearing'))
  const clearingNote = readSoeRemark((id) => responses.get(id) as any, 'clearingNote')
  state.clearingNote = typeof clearingNote === 'string' ? clearingNote : ''
  const fullyDepRows = hydrateFullyDepRows(parseSoeKey(responses, 'fullyDep'))

  if (!layersHaveAnyAmount(state.layers)) {
    const detail = parsed<Record<string, unknown>[] | null>(responses, 'H1-2-rows', null)
    if (Array.isArray(detail) && detail.length > 0) {
      state.layers = seedMovementFromDetailRows(detail)
    }
  }
  return {
    state,
    fullyDepRows,
    hasSource: hasValue(responses, [...Object.values(H1_SOE_KEYS), 'H1-2-rows']),
  }
}
