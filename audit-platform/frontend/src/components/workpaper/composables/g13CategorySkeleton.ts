/**
 * G13-2 分类骨架汇总 — 对齐致同明细表固定行（与 G13-1 同序）
 * 「其中」为备忘子集，不计入合计，避免与主行双重加计。
 */
import {
  G13_ADJUDICATION_ITEMS,
  G13_SOURCE_INDEX_BY_BELONG,
  isG13AdjRowInTotal,
  mapBelongToAdjRow,
  mapBelongToOfWhichRow,
  type G13AdjRowKind,
} from './g13Constants'
import {
  parseNum,
  calcSubtotal,
  isBsFvReconciled,
  isPlReconciled,
} from './useG13FormulaEngine'

export interface G13DetailLikeForSkeleton {
  rowId?: string
  belongAccount: string
  instrumentType?: string
  remark?: string
  currentUnadjusted?: number
  adjustment?: number
  currentAudited?: number
  cost?: number
  periodFvChange?: number
  cumulativeFvChange?: number
  fairValue?: number
  amountInPl?: number
  fvChange?: number
}

export interface G13CategorySkeletonRow {
  rowKey: string
  label: string
  kind: G13AdjRowKind
  indent: number
  emphasize: boolean
  currentUnadjusted: number
  adjustment: number
  currentAudited: number
  cost: number
  periodFvChange: number
  cumulativeFvChange: number
  fairValue: number
  amountInPl: number
  bsReconciled: boolean
  plReconciled: boolean
  sourceIndex: string
  instrumentCount: number
}

function emptyAgg(): Omit<G13CategorySkeletonRow, 'rowKey' | 'label' | 'kind' | 'indent' | 'emphasize' | 'sourceIndex' | 'bsReconciled' | 'plReconciled'> {
  return {
    currentUnadjusted: 0,
    adjustment: 0,
    currentAudited: 0,
    cost: 0,
    periodFvChange: 0,
    cumulativeFvChange: 0,
    fairValue: 0,
    amountInPl: 0,
    instrumentCount: 0,
  }
}

function addRow(
  agg: ReturnType<typeof emptyAgg>,
  r: G13DetailLikeForSkeleton,
): void {
  agg.currentUnadjusted += parseNum(r.currentUnadjusted)
  agg.adjustment += parseNum(r.adjustment)
  agg.currentAudited += parseNum(r.currentAudited)
  agg.cost += parseNum(r.cost)
  agg.periodFvChange += parseNum(r.periodFvChange ?? r.fvChange)
  agg.cumulativeFvChange += parseNum(r.cumulativeFvChange)
  agg.fairValue += parseNum(r.fairValue)
  agg.amountInPl += parseNum(r.amountInPl)
  agg.instrumentCount += 1
}

function sourceIndexForRowKey(rowKey: string): string {
  const def = G13_ADJUDICATION_ITEMS.find((d) => d.rowKey === rowKey)
  const acct = def?.sourceAccounts[0]
  return acct ? (G13_SOURCE_INDEX_BY_BELONG[acct] ?? '') : ''
}

/** 按致同固定行汇总工具明细 */
export function buildG13CategorySkeleton(
  detailRows: G13DetailLikeForSkeleton[],
): G13CategorySkeletonRow[] {
  const data = detailRows.filter((r) => r.rowId !== 'total')
  const byMain = new Map<string, ReturnType<typeof emptyAgg>>()
  const byOfWhich = new Map<string, ReturnType<typeof emptyAgg>>()

  for (const r of data) {
    const mainKey = mapBelongToAdjRow(r.belongAccount, r.instrumentType)
    if (!byMain.has(mainKey)) byMain.set(mainKey, emptyAgg())
    addRow(byMain.get(mainKey)!, r)

    const ofWhichKey = mapBelongToOfWhichRow(r.belongAccount, r.instrumentType, r.remark)
    if (ofWhichKey) {
      if (!byOfWhich.has(ofWhichKey)) byOfWhich.set(ofWhichKey, emptyAgg())
      addRow(byOfWhich.get(ofWhichKey)!, r)
    }
  }

  return G13_ADJUDICATION_ITEMS.map((def) => {
    const agg = def.kind === 'ofWhich'
      ? (byOfWhich.get(def.rowKey) ?? emptyAgg())
      : (byMain.get(def.rowKey) ?? emptyAgg())
    const bsFilled = agg.cost !== 0 || agg.cumulativeFvChange !== 0 || agg.fairValue !== 0
    const plFilled = agg.amountInPl !== 0 || agg.currentAudited !== 0
    return {
      rowKey: def.rowKey,
      label: def.label,
      kind: def.kind,
      indent: def.indent,
      emphasize: !!def.emphasize,
      ...agg,
      bsReconciled: !bsFilled || isBsFvReconciled(agg.cost, agg.cumulativeFvChange, agg.fairValue),
      plReconciled: !plFilled || isPlReconciled(agg.amountInPl, agg.currentAudited),
      sourceIndex: sourceIndexForRowKey(def.rowKey),
    }
  })
}

export function buildG13CategoryTotalRow(
  skeletonRows: G13CategorySkeletonRow[],
): G13CategorySkeletonRow {
  const rows = skeletonRows.filter((r) => isG13AdjRowInTotal(r.kind))
  const cost = calcSubtotal(rows.map((r) => r.cost))
  const cumulativeFvChange = calcSubtotal(rows.map((r) => r.cumulativeFvChange))
  const fairValue = calcSubtotal(rows.map((r) => r.fairValue))
  const amountInPl = calcSubtotal(rows.map((r) => r.amountInPl))
  const currentAudited = calcSubtotal(rows.map((r) => r.currentAudited))
  const bsFilled = cost !== 0 || cumulativeFvChange !== 0 || fairValue !== 0
  const plFilled = amountInPl !== 0 || currentAudited !== 0
  return {
    rowKey: 'total',
    label: '合计',
    kind: 'main',
    indent: 0,
    emphasize: false,
    currentUnadjusted: calcSubtotal(rows.map((r) => r.currentUnadjusted)),
    adjustment: calcSubtotal(rows.map((r) => r.adjustment)),
    currentAudited,
    cost,
    periodFvChange: calcSubtotal(rows.map((r) => r.periodFvChange)),
    cumulativeFvChange,
    fairValue,
    amountInPl,
    bsReconciled: !bsFilled || isBsFvReconciled(cost, cumulativeFvChange, fairValue),
    plReconciled: !plFilled || isPlReconciled(amountInPl, currentAudited),
    sourceIndex: '',
    instrumentCount: calcSubtotal(rows.map((r) => r.instrumentCount)),
  }
}

/** 指定类明细按「其中」rowKey 汇总（供回写 G13-1 备忘行） */
export function aggregateDesignatedOfWhich(
  detailRows: G13DetailLikeForSkeleton[],
): Record<string, { unadjusted: number; adjustment: number; audited: number }> {
  const acc: Record<string, { unadjusted: number; adjustment: number; audited: number }> = {}
  for (const r of detailRows) {
    if (r.rowId === 'total') continue
    const key = mapBelongToOfWhichRow(r.belongAccount, r.instrumentType, r.remark)
    if (!key) continue
    if (!acc[key]) acc[key] = { unadjusted: 0, adjustment: 0, audited: 0 }
    acc[key].unadjusted += parseNum(r.currentUnadjusted)
    acc[key].adjustment += parseNum(r.adjustment)
    acc[key].audited += parseNum(r.currentAudited)
  }
  return acc
}
