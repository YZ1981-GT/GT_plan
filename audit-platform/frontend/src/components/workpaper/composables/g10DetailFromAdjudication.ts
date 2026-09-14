/**
 * G10-1 审定表 (一)(二)(三) 分项 → G10-2 明细骨架行
 * 与 pushG10DetailToAdjudication 互为反向操作（按叶节点 suffix 对齐）
 */
import type { G10LiabilityLineSuffix } from './g10AdjudicationItems'
import { G10_ADJ_ROWS_KEY, parseG10AdjStore, type G10AdjRowRaw } from './g10AdjStorage'
import { enrichG10DetailRow, type G10DetailRow } from './useG10Detail'
import { parseNum } from './useG10FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export const G10_BOOK_LEAF_SUFFIXES = [
  'trading_bond',
  'derivative_liability',
  'other',
  'designated_bond',
  'hybrid_tool',
  'other_designated',
] as const satisfies readonly G10LiabilityLineSuffix[]

export interface G10DetailLeafMeta {
  suffix: string
  liabilityType: string
  liabilityCategory: string
  defaultName: string
  isDerivative?: boolean
}

export const G10_ADJ_BOOK_TO_DETAIL: Record<string, G10DetailLeafMeta> = {
  trading_bond: {
    suffix: 'trading_bond',
    liabilityType: '交易性债券',
    liabilityCategory: '交易类',
    defaultName: '发行的交易性债券',
  },
  derivative_liability: {
    suffix: 'derivative_liability',
    liabilityType: '衍生金融负债',
    liabilityCategory: '交易类',
    defaultName: '衍生金融负债',
    isDerivative: true,
  },
  other: {
    suffix: 'other',
    liabilityType: '其他',
    liabilityCategory: '交易类',
    defaultName: '其他交易性负债',
  },
  designated_bond: {
    suffix: 'designated_bond',
    liabilityType: '其他',
    liabilityCategory: '指定类',
    defaultName: '指定—债券',
  },
  hybrid_tool: {
    suffix: 'hybrid_tool',
    liabilityType: '结构化产品',
    liabilityCategory: '指定类',
    defaultName: '混合工具',
  },
  other_designated: {
    suffix: 'other_designated',
    liabilityType: '其他',
    liabilityCategory: '指定类',
    defaultName: '指定—其他',
  },
}

function readAdjPair(store: Record<string, G10AdjRowRaw>, rowKey: string): { opening: number; closing: number } {
  const raw = store[rowKey]
  return {
    opening: parseNum(raw?.openingUnadjusted),
    closing: parseNum(raw?.closingUnadjusted),
  }
}

function hasAmount(opening: number, closing: number): boolean {
  return Math.abs(opening) > 0.005 || Math.abs(closing) > 0.005
}

export type G10DetailFromAdjMode = 'fill-empty' | 'overwrite'

export interface G10DetailFromAdjResult {
  rows: G10DetailRow[]
  filled: number
  added: number
  updated: number
}

export function buildG10DetailRowsFromAdjudication(
  store: Record<string, G10AdjRowRaw>,
  existingRows: G10DetailRow[],
  genRowId: () => string,
  mode: G10DetailFromAdjMode = 'fill-empty',
): G10DetailFromAdjResult {
  const next = existingRows.map((r, i) => enrichG10DetailRow(r, i + 1))
  let filled = 0
  let added = 0
  let updated = 0

  for (const suffix of G10_BOOK_LEAF_SUFFIXES) {
    const meta = G10_ADJ_BOOK_TO_DETAIL[suffix]
    const init = readAdjPair(store, `init_${suffix}`)
    const fv = readAdjPair(store, `fv_${suffix}`)
    const book = readAdjPair(store, `book_${suffix}`)
    if (!hasAmount(book.opening, book.closing) && !hasAmount(init.opening, init.closing)) continue

    filled += 1
    const matchIdx = next.findIndex(
      (r) => r.liabilityType === meta.liabilityType
        && r.liabilityCategory === meta.liabilityCategory
        && (!r.liabilityName.trim() || r.liabilityName === meta.defaultName),
    )

    const movementInitialAmount = init.closing - init.opening
    const movementFvChange = fv.closing - fv.opening

    const patch: Partial<G10DetailRow> = {
      liabilityCategory: meta.liabilityCategory,
      liabilityType: meta.liabilityType,
      liabilityName: meta.defaultName,
      isDerivative: !!meta.isDerivative,
      openingInitialAmount: init.opening,
      openingFvAccum: fv.opening,
      movementInitialAmount,
      movementFvChange,
      remark: '由 G10-1 分项带入',
    }

    if (matchIdx >= 0) {
      const prev = next[matchIdx]
      const shouldUpdate = mode === 'overwrite'
        || !prev.liabilityName.trim()
        || Math.abs(prev.closingFairValue) <= 0.005
      if (shouldUpdate) {
        next[matchIdx] = enrichG10DetailRow({ ...prev, ...patch, rowId: prev.rowId }, matchIdx + 1)
        updated += 1
      }
    } else {
      next.push(enrichG10DetailRow({ rowId: genRowId(), ...patch }, next.length + 1))
      added += 1
    }
  }

  return {
    rows: next.map((r, i) => enrichG10DetailRow(r, i + 1)),
    filled,
    added,
    updated,
  }
}

export function pullG10DetailFromAdjudicationResponses(
  responses: Map<string, ChecklistResponse>,
  existingRows: G10DetailRow[],
  genRowId: () => string,
  mode: G10DetailFromAdjMode = 'fill-empty',
): G10DetailFromAdjResult {
  const store = parseG10AdjStore(responses.get(G10_ADJ_ROWS_KEY)?.remark)
  return buildG10DetailRowsFromAdjudication(store, existingRows, genRowId, mode)
}
