import {
  buildL4SyncPayload,
  L4_DISCLOSURE_SHEET_NAME,
  L4_NOTE_SECTION,
  type L4Variant,
} from './l4NoteSectionMap'
import type { ChecklistResponse } from './useL4FormData'

export interface L4DisclosureItem {
  seq: number
  item: string
  noteContent: string
  auditedData: string
  isConsistent: string
  diffNote: string
}

export interface L4DetailSourceRow {
  key?: string
  bondName?: string
  issueDate?: string
  maturityDate?: string
  faceValue?: number
  couponRate?: number
  beginCostPrincipal?: number
  beginCostInterestAdj?: number
  beginCostAccrued?: number
  creditIssue?: number
  creditInterestAdj?: number
  debitRedemption?: number
  debitInterestAdj?: number
  endCostAccrued?: number
  couponInterest?: number
  redemptionAmount?: number
}

export interface L4DisclosureState {
  items: L4DisclosureItem[]
  noteText: string
  conclusion: string
  /** undefined = 底稿从未保存过 L4-2 行，不能以默认空表覆盖附注。 */
  detailRows?: L4DetailSourceRow[]
}

const LISTED_ITEMS = [
  '债券名称及面值', '发行日期及期限', '票面利率/实际利率', '期初摊余成本', '本期利息费用',
  '本期兑付金额', '期末摊余成本', '信用评级', '担保情况', '提前赎回/转换条款',
] as const

const SOE_ITEMS = [
  '债券名称及面值', '发行日期及期限', '票面利率/实际利率', '期初摊余成本', '本期利息费用',
  '本期兑付金额', '期末摊余成本', '审批机关及批准文号', '资金用途及使用进度',
  '偿债计划及资金来源', '国资委备案情况', '担保情况',
] as const

const num = (value: unknown): number => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function json<T>(value: string | null | undefined, fallback: T): T {
  if (!value) return fallback
  try {
    const parsed = JSON.parse(value)
    return (parsed ?? fallback) as T
  } catch {
    return fallback
  }
}

export function createL4DisclosureItems(variant: L4Variant): L4DisclosureItem[] {
  const labels = variant === 'listed' ? LISTED_ITEMS : SOE_ITEMS
  return labels.map((item, index) => ({
    seq: index + 1,
    item,
    noteContent: '',
    auditedData: '',
    isConsistent: '',
    diffNote: '',
  }))
}

export function restoreL4DisclosureState(
  responses: ReadonlyMap<string, ChecklistResponse>,
  variant: L4Variant,
): L4DisclosureState {
  const prefix = `L4-disc-${variant}`
  const items = createL4DisclosureItems(variant).map((item) => {
    const response = responses.get(`${prefix}-${item.seq}`)
    const saved = json<{ noteContent?: unknown; diffNote?: unknown }>(response?.remark, {})
    return {
      ...item,
      noteContent: String(saved.noteContent ?? ''),
      isConsistent: String(response?.conclusion ?? ''),
      diffNote: String(saved.diffNote ?? ''),
    }
  })
  const rowsItem = responses.get('L4-2-rows')
  const parsedRows = rowsItem
    ? json<unknown>(rowsItem.remark, [])
    : undefined
  return {
    items,
    noteText: String(responses.get(`${prefix}-noteText`)?.remark ?? ''),
    conclusion: String(responses.get(`${prefix}-conclusion`)?.remark ?? ''),
    detailRows: Array.isArray(parsedRows) ? parsedRows as L4DetailSourceRow[] : undefined,
  }
}

function calculated(row: L4DetailSourceRow) {
  const endPrincipal = num(row.beginCostPrincipal) + num(row.creditIssue) - num(row.debitRedemption)
  const endInterestAdj = num(row.beginCostInterestAdj) + num(row.creditInterestAdj) - num(row.debitInterestAdj)
  const endAccrued = num(row.endCostAccrued)
  return { endPrincipal, endInterestAdj, endAccrued }
}

export function l4MainRows(variant: L4Variant, rows: readonly L4DetailSourceRow[] | undefined) {
  if (rows === undefined) return undefined
  return rows.filter((row) => String(row.bondName ?? '').trim()).map((row) => {
    const end = calculated(row)
    const label = String(row.bondName ?? '').trim()
    if (variant === 'listed') {
      return {
        label,
        endFaceValue: num(row.faceValue),
        endInterestAdj: end.endInterestAdj,
        endAccruedInterest: end.endAccrued,
        endTotal: num(row.faceValue) + end.endInterestAdj + end.endAccrued,
        priorFaceValue: num(row.beginCostPrincipal),
        priorInterestAdj: num(row.beginCostInterestAdj),
        priorAccruedInterest: num(row.beginCostAccrued),
        priorTotal: num(row.beginCostPrincipal) + num(row.beginCostInterestAdj) + num(row.beginCostAccrued),
      }
    }
    return {
      bondName: label,
      faceValue: num(row.faceValue),
      issueDate: String(row.issueDate ?? ''),
      term: String(row.maturityDate ?? ''),
      balance: end.endPrincipal + end.endInterestAdj + end.endAccrued,
      accruedInterest: end.endAccrued,
      rate: num(row.couponRate),
    }
  })
}

export function l4MovementRows(rows: readonly L4DetailSourceRow[] | undefined) {
  if (rows === undefined) return undefined
  return rows.filter((row) => String(row.bondName ?? '').trim()).map((row) => {
    const end = calculated(row)
    return {
      label: String(row.bondName ?? '').trim(),
      beginFaceValue: num(row.beginCostPrincipal),
      beginInterestAdj: num(row.beginCostInterestAdj),
      beginAccruedInterest: num(row.beginCostAccrued),
      increaseFaceValue: num(row.creditIssue),
      increaseInterestAdj: num(row.creditInterestAdj),
      increaseAccruedInterest: num(row.couponInterest),
      decreaseFaceValue: num(row.debitRedemption),
      decreaseInterestAdj: num(row.debitInterestAdj),
      decreaseAccruedInterest: num(row.redemptionAmount),
      endFaceValue: end.endPrincipal,
      endInterestAdj: end.endInterestAdj,
      endAccruedInterest: end.endAccrued,
    }
  })
}

export function buildL4DisclosureSyncBody(input: {
  variant: L4Variant
  wpId: string
  projectId: string
  state: L4DisclosureState
}) {
  const { variant, wpId, projectId, state } = input
  const noteTexts = state.noteText.trim()
    ? [{ section: 'l4-convertible-bond', title: '可转换公司债券', text: state.noteText.trim() }]
    : undefined
  const payload = buildL4SyncPayload({
    variant,
    wpId,
    projectId,
    mainRows: l4MainRows(variant, state.detailRows),
    movementRows: l4MovementRows(state.detailRows),
    noteTexts,
  })
  return {
    wp_id: wpId,
    sheet_name: L4_DISCLOSURE_SHEET_NAME[variant],
    section_id: L4_NOTE_SECTION[variant],
    current_standard: variant === 'listed' ? 'listed_standalone' : 'soe_standalone',
    sub_table_data: payload.sub_table_data,
    columns: payload._sub_table_columns,
  }
}
