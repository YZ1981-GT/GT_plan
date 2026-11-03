/** E1 披露 Tab 的纯状态恢复口径，供真实 Tab 与 headless provider 共用。 */
import {
  E1_DEFAULT_CURRENCIES,
  E1_FX_GROUPS,
  E1_FX_SIMPLE_GROUP_LABEL,
  e1BaseCurrencyLabel,
  e1ForeignCurrencies,
} from './e1CurrencyScope'
import { e1LegacyNoteKey, e1NoteTextKey, e1NoteTexts } from './e1DisclosureScope'
import {
  customBucketKey,
  e1RestrictedMapKey,
  e1RestrictedRowId,
  e1RestrictedSeqKey,
  normalizeRestrictedPrefill,
  parseManualMap,
  parseRestrictedSeq,
  pendingUnclassified,
  resolveRestrictedRows,
  type E1RestrictedManualMap,
  type E1RestrictedRow,
} from './e1RestrictedScope'

export type E1Variant = 'listed' | 'soe'
export type E1ForeignCurrencyMode = 'simple' | 'detailed'
export type E1ForeignAmountField =
  | 'endForeign' | 'endRate' | 'endRmb' | 'openForeign' | 'openRate' | 'openRmb'

export interface E1ForeignCurrencyRow {
  id: string
  groupId: string
  item: string
  currency: string
  isGroup: boolean
  indent: boolean
  endForeign: number
  endRate: number
  endRmb: number
  openForeign: number
  openRate: number
  openRmb: number
}

export type E1ResponseMap = ReadonlyMap<string, { remark?: unknown } | undefined>

const num = (value: unknown): number => Number(value) || 0

export function e1StoragePrefix(variant: E1Variant): string {
  return `E1-disclosure-${variant}`
}

export function createE1CurrencyRow(
  groupId: string,
  currency: string,
  suffix: string,
): E1ForeignCurrencyRow {
  const isRmb = currency === e1BaseCurrencyLabel()
  return {
    id: `fc-currency-${suffix}`,
    groupId,
    item: currency,
    currency,
    isGroup: false,
    indent: true,
    endForeign: 0,
    endRate: isRmb ? 1 : 0,
    endRmb: 0,
    openForeign: 0,
    openRate: isRmb ? 1 : 0,
    openRmb: 0,
  }
}

export function createE1DefaultForeignRows(mode: E1ForeignCurrencyMode): E1ForeignCurrencyRow[] {
  const projects = mode === 'detailed'
    ? E1_FX_GROUPS.map(group => group.label)
    : [E1_FX_SIMPLE_GROUP_LABEL]
  const currencies = mode === 'detailed'
    ? E1_DEFAULT_CURRENCIES.map(currency => currency.label)
    : e1ForeignCurrencies().map(currency => currency.label)
  return projects.flatMap((item, projectIndex) => {
    const groupId = `fc-group-${mode}-${projectIndex}`
    return [{
      id: groupId,
      groupId,
      item: `${item}：`,
      currency: '',
      isGroup: true,
      indent: false,
      endForeign: 0,
      endRate: 0,
      endRmb: 0,
      openForeign: 0,
      openRate: 0,
      openRmb: 0,
    }, ...currencies.map((currency, currencyIndex) =>
      createE1CurrencyRow(groupId, currency, `${mode}-${projectIndex}-${currencyIndex}`))]
  })
}
export function normalizeE1ForeignRows(rows: readonly any[]): E1ForeignCurrencyRow[] {
  let currentGroupId = ''
  return rows.map((raw: any, index: number) => {
    const isGroup = !!raw.isGroup
    const id = String(raw.id || `fc-migrated-${index}`)
    if (isGroup) currentGroupId = id
    const currency = isGroup ? '' : String(raw.currency || raw.item || '').replace(/^其中[：:]?/, '').trim()
    const groupId = isGroup ? id : String(raw.groupId || currentGroupId)
    const endForeign = num(raw.endForeign)
    const endRate = num(raw.endRate)
    const openForeign = num(raw.openForeign)
    const openRate = num(raw.openRate)
    return {
      id,
      groupId,
      item: isGroup ? String(raw.item || `${E1_FX_SIMPLE_GROUP_LABEL}：`) : currency,
      currency,
      isGroup,
      indent: !isGroup,
      endForeign,
      endRate,
      endRmb: endForeign * endRate,
      openForeign,
      openRate,
      openRmb: openForeign * openRate,
    }
  })
}

export function restoreE1ForeignCurrency(responses: E1ResponseMap, variant: E1Variant): {
  mode: E1ForeignCurrencyMode
  simpleRows: E1ForeignCurrencyRow[]
  detailedRows: E1ForeignCurrencyRow[]
  hasSource: boolean
  parseError: boolean
} {
  const fallback = {
    mode: 'detailed' as E1ForeignCurrencyMode,
    simpleRows: createE1DefaultForeignRows('simple'),
    detailedRows: createE1DefaultForeignRows('detailed'),
    hasSource: false,
    parseError: false,
  }
  const remark = responses.get(`${e1StoragePrefix(variant)}-foreign-currency`)?.remark
  if (typeof remark !== 'string' || !remark.trim()) return fallback
  try {
    const parsed = JSON.parse(remark)
    if (Array.isArray(parsed)) {
      return { ...fallback, simpleRows: normalizeE1ForeignRows(parsed), hasSource: true }
    }
    if (!parsed || typeof parsed !== 'object') return { ...fallback, parseError: true }
    return {
      mode: parsed.mode === 'detailed' ? 'detailed' : 'simple',
      simpleRows: Array.isArray(parsed.simpleRows)
        ? normalizeE1ForeignRows(parsed.simpleRows)
        : fallback.simpleRows,
      detailedRows: Array.isArray(parsed.detailedRows)
        ? normalizeE1ForeignRows(parsed.detailedRows)
        : fallback.detailedRows,
      hasSource: true,
      parseError: false,
    }
  } catch {
    return { ...fallback, parseError: true }
  }
}

export function restoreE1Openings(responses: E1ResponseMap, variant: E1Variant): Record<string, number> {
  const remark = responses.get(`${e1StoragePrefix(variant)}-openings`)?.remark
  if (typeof remark !== 'string' || !remark.trim()) return {}
  try {
    const parsed = JSON.parse(remark)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? Object.fromEntries(Object.entries(parsed).map(([key, value]) => [key, num(value)]))
      : {}
  } catch {
    return {}
  }
}
export function restoreE1NoteTexts(responses: E1ResponseMap, variant: E1Variant): {
  texts: Record<string, string>
  hasSource: boolean
} {
  const texts: Record<string, string> = {}
  let hasNew = false
  let anyNew = false
  for (const def of e1NoteTexts(variant)) {
    const response = responses.get(e1NoteTextKey(variant, def.key))
    if (response) hasNew = true
    const value = typeof response?.remark === 'string' ? response.remark : ''
    texts[def.key] = value
    if (value) anyNew = true
  }
  const legacy = responses.get(e1LegacyNoteKey(variant))
  if (!anyNew && typeof legacy?.remark === 'string' && legacy.remark) {
    const first = e1NoteTexts(variant)[0]
    if (first) texts[first.key] = legacy.remark
  }
  return { texts, hasSource: hasNew || !!legacy }
}

export function restoreE1RestrictedState(responses: E1ResponseMap, variant: E1Variant): {
  manualMap: E1RestrictedManualMap
  persistedRows: E1RestrictedRow[]
  seq: number
  hasSavedRows: boolean
  parseError: boolean
} {
  const manualMap = parseManualMap(responses.get(e1RestrictedMapKey(variant))?.remark)
  const seq = parseRestrictedSeq(responses.get(e1RestrictedSeqKey(variant))?.remark)
  const response = responses.get(`${e1StoragePrefix(variant)}-restricted`)
  if (!response || typeof response.remark !== 'string' || !response.remark.trim()) {
    return { manualMap, persistedRows: [], seq, hasSavedRows: false, parseError: false }
  }
  try {
    const parsed = JSON.parse(response.remark)
    if (!Array.isArray(parsed)) {
      return { manualMap, persistedRows: [], seq, hasSavedRows: false, parseError: true }
    }
    const persistedRows = parsed.map((row: any, index: number) => ({
      id: String(row.id || e1RestrictedRowId(String(row.bucketKey || 'legacy'), index)),
      bucketKey: String(row.bucketKey || customBucketKey(String(row.item || ''))),
      label: String(row.label || row.item || ''),
      openingAmount: num(row.openingAmount),
      endingAmount: num(row.endingAmount ?? row.amount),
      reason: String(row.reason || ''),
      codes: Array.isArray(row.codes) ? row.codes.map((code: unknown) => String(code)) : [],
      fromFourTable: !!row.fromFourTable,
    }))
    return { manualMap, persistedRows, seq, hasSavedRows: true, parseError: false }
  } catch {
    return { manualMap, persistedRows: [], seq, hasSavedRows: false, parseError: true }
  }
}

export function resolveE1ManagedRestrictedRows(input: {
  rawPrefill: unknown
  restored: ReturnType<typeof restoreE1RestrictedState>
}): {
  rows: E1RestrictedRow[]
  managedRows: E1RestrictedRow[] | undefined
  trustedPrefill: boolean
  pendingCount: number
} {
  const prefill = normalizeRestrictedPrefill(input.rawPrefill)
  const trustedPrefill = prefill.source?.report_row_code === 'BS-002'
    && prefill.source?.chart_available !== false
  const rows = resolveRestrictedRows({
    prefill,
    manualMap: input.restored.manualMap,
    existingRows: input.restored.persistedRows,
  })
  const pendingCount = pendingUnclassified(prefill, input.restored.manualMap).length
  const authoritative = trustedPrefill
    || input.restored.hasSavedRows
    || input.restored.persistedRows.length > 0
    || Object.keys(input.restored.manualMap).length > 0
  const managedRows = authoritative && !(pendingCount > 0 && rows.length === 0)
    ? rows
    : undefined
  return { rows, managedRows, trustedPrefill, pendingCount }
}
