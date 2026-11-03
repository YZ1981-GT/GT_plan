import type { ChecklistResponse } from './useM10FormData'
import {
  buildM10ListedSyncPayload,
  buildM10SoeSyncPayload,
  type M10MovementRow,
} from './m10NoteSectionMap'

export type M10Variant = 'listed' | 'soe'
export type M10MovementField =
  | 'beginQty' | 'beginBalance'
  | 'increaseQty' | 'issuance'
  | 'decreaseQty' | 'redemption'
export type M10LocalField = M10MovementField | 'interestDividend'

export interface M10UiRow {
  key: string
  item: string
  beginQty: number | null
  beginBalance: number | null
  increaseQty: number | null
  issuance: number | null
  decreaseQty: number | null
  redemption: number | null
  /** 上市底稿本地字段，附注变动表没有此列。 */
  interestDividend: number | null
}

export interface M10DisplayRow {
  key: string
  item: string
  beginQty: number
  beginBalance: number
  increaseQty: number
  issuance: number
  decreaseQty: number
  redemption: number
  endQty: number
  endBalance: number
  interestDividend: number
  _isTotal?: boolean
}

const LISTED_ROWS = [
  ['perpetual-1', '永续债 — 第一期'], ['perpetual-2', '永续债 — 第二期'],
  ['perpetual-3', '永续债 — 第三期'], ['preferred-a', '优先股 — A系列'],
  ['preferred-b', '优先股 — B系列'], ['other', '其他权益工具'],
] as const

const SOE_ROWS = [
  ['perpetual', '永续债'], ['preferred', '优先股'], ['other', '其他权益工具'],
] as const
const n = (value: number | null): number => value ?? 0

export function createM10Rows(variant: M10Variant): M10UiRow[] {
  const definitions = variant === 'listed' ? LISTED_ROWS : SOE_ROWS
  return definitions.map(([key, item]) => ({
    key, item,
    beginQty: null, beginBalance: null,
    increaseQty: null, issuance: null,
    decreaseQty: null, redemption: null,
    interestDividend: null,
  }))
}

function savedNumber(responses: ReadonlyMap<string, ChecklistResponse>, key: string): number | null {
  const raw = responses.get(key)?.remark
  if (raw == null || raw === '') return null
  const value = Number(raw)
  return Number.isFinite(value) ? value : null
}

export function m10MovementItemId(
  variant: M10Variant,
  rowKey: string,
  field: M10LocalField,
): string {
  return `M10-disclosure-${variant}-movement-${rowKey}-${field}`
}

export function restoreM10Rows(
  responses: ReadonlyMap<string, ChecklistResponse>,
  variant: M10Variant,
): M10UiRow[] {
  const rows = createM10Rows(variant)
  const legacyFields: readonly M10LocalField[] = ['beginBalance', 'issuance', 'redemption', 'interestDividend']
  rows.forEach((row, index) => {
    for (const field of [
      'beginQty', 'beginBalance', 'increaseQty', 'issuance',
      'decreaseQty', 'redemption', 'interestDividend',
    ] as const) {
      let value = savedNumber(responses, m10MovementItemId(variant, row.key, field))
      if (value === null && legacyFields.includes(field)) {
        value = savedNumber(responses, `M10-disclosure-${variant}-${index}-${field}`)
      }
      row[field] = value
    }
  })
  return rows
}
/** 三个数量字段都有真实输入后才拥有整行写权；缺数量时不能用默认零覆盖附注。 */
export function hasM10MovementSource(row: M10UiRow): boolean {
  return [row.beginQty, row.increaseQty, row.decreaseQty].every((value) => value !== null)
}

export function m10WireRows(rows: readonly M10UiRow[]): M10MovementRow[] {
  return rows.filter(hasM10MovementSource).map((row) => ({
    label: row.item,
    beginQty: n(row.beginQty),
    beginValue: n(row.beginBalance),
    increaseQty: n(row.increaseQty),
    increaseValue: n(row.issuance),
    decreaseQty: n(row.decreaseQty),
    decreaseValue: n(row.redemption),
  }))
}

export function m10DisplayRows(source: readonly M10UiRow[]): M10DisplayRow[] {
  const rows: M10DisplayRow[] = source.map((row) => {
    const beginQty = n(row.beginQty)
    const beginBalance = n(row.beginBalance)
    const increaseQty = n(row.increaseQty)
    const issuance = n(row.issuance)
    const decreaseQty = n(row.decreaseQty)
    const redemption = n(row.redemption)
    return {
      key: row.key, item: row.item,
      beginQty, beginBalance, increaseQty, issuance, decreaseQty, redemption,
      endQty: beginQty + increaseQty - decreaseQty,
      endBalance: beginBalance + issuance - redemption,
      interestDividend: n(row.interestDividend),
    }
  })
  const sum = (field: keyof Pick<M10DisplayRow,
    'beginQty' | 'beginBalance' | 'increaseQty' | 'issuance' | 'decreaseQty' |
    'redemption' | 'endQty' | 'endBalance' | 'interestDividend'>) =>
    rows.reduce((total, row) => total + row[field], 0)
  rows.push({
    key: 'total', item: '合计',
    beginQty: sum('beginQty'), beginBalance: sum('beginBalance'),
    increaseQty: sum('increaseQty'), issuance: sum('issuance'),
    decreaseQty: sum('decreaseQty'), redemption: sum('redemption'),
    endQty: sum('endQty'), endBalance: sum('endBalance'),
    interestDividend: sum('interestDividend'), _isTotal: true,
  })
  return rows
}
export function m10NoteText(
  responses: ReadonlyMap<string, ChecklistResponse>,
  variant: M10Variant,
): string {
  const keys = variant === 'listed'
    ? [
        'M10-disclosure-listed-terms-summary',
        'M10-disclosure-listed-distribution-note',
        'M10-disclosure-listed-other-disclosure',
      ]
    : [
        'M10-disclosure-soe-classification-basis',
        'M10-disclosure-soe-special-note',
      ]
  return keys
    .map((key) => String(responses.get(key)?.remark ?? '').trim())
    .filter(Boolean)
    .join('\n\n')
}

export function buildM10DisclosurePayload(input: {
  wpId: string
  variant: M10Variant
  rows: readonly M10UiRow[]
  noteText?: string
}) {
  const movement = m10WireRows(input.rows)
  return input.variant === 'listed'
    ? buildM10ListedSyncPayload(input.wpId, [], movement, [], input.noteText)
    : buildM10SoeSyncPayload(input.wpId, movement, input.noteText)
}
