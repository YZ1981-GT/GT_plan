/**
 * G1 国企附注披露行结构 — 对齐 Excel / note_template_soe §八、2 / §八、3
 *
 * 编制逻辑：
 * 1. 交易性金融资产表：分类 FVTPL（债务/权益/其他）+ 指定 FVTPL（债务/其他）+ 合计
 * 2. 衍生金融资产表：明细行（前十大）+ 合计；金额默认从 G1-1 账面余额衍生品种汇总
 * 3. 取数口径：G1-1 审定表「（三）账面余额（公允价值）」carrying 段
 *    - 分类行 = trading + classified（准则「分类为 FVTPL」含交易性）
 *    - 指定行 = designated
 *    - 衍生单独进八、3，不计入交易性表「其他」
 */
import { parseG1AdjStore, type G1AdjAsset, type G1AdjClass } from './g1AdjudicationItems'
import { buildG1AdjudicationRows, type G1AdjudicationRow } from './useG1Adjudication'
import { parseNum } from './useG1TraFinFormulaEngine'

export type G1SoeRowKind = 'category' | 'detail' | 'total'

export interface G1SoeTradingRowDef {
  rowKey: string
  label: string
  kind: G1SoeRowKind
  indent: number
  /** 子项汇总到该行（category / total） */
  childKeys?: string[]
  /** 从审定表 carrying 叶子聚合 */
  source?: { classes: G1AdjClass[]; assets: G1AdjAsset[] }
  editable: boolean
}

export interface G1SoeTradingRow {
  rowKey: string
  label: string
  kind: G1SoeRowKind
  indent: number
  endAmount: number
  priorAmount: number
  autoFilled: boolean
  editable: boolean
}

export interface G1SoeDerivativeRow {
  rowId: string
  label: string
  endAmount: number
  priorAmount: number
  reason: string
  autoFilled: boolean
}

const CLASSIFIED_CLASSES: G1AdjClass[] = ['trading', 'classified']
const DESIGNATED_CLASSES: G1AdjClass[] = ['designated']
const OTHER_ASSETS: G1AdjAsset[] = ['wealth', 'structured', 'fund', 'other']
const DESIGNATED_OTHER_ASSETS: G1AdjAsset[] = ['equity', 'wealth', 'structured', 'fund', 'other']

/** 固定层级（不含合计行；合计由显示层计算） */
export const G1_SOE_TRADING_ROW_DEFS: G1SoeTradingRowDef[] = [
  {
    rowKey: 'classified',
    label: '分类以公允价值计量且其变动计入当期损益的金融资产',
    kind: 'category',
    indent: 0,
    childKeys: ['classified-debt', 'classified-equity', 'classified-other'],
    editable: false,
  },
  {
    rowKey: 'classified-debt',
    label: '其中：债务工具投资',
    kind: 'detail',
    indent: 1,
    source: { classes: CLASSIFIED_CLASSES, assets: ['debt'] },
    editable: true,
  },
  {
    rowKey: 'classified-equity',
    label: '权益工具投资',
    kind: 'detail',
    indent: 1,
    source: { classes: CLASSIFIED_CLASSES, assets: ['equity'] },
    editable: true,
  },
  {
    rowKey: 'classified-other',
    label: '其他',
    kind: 'detail',
    indent: 1,
    source: { classes: CLASSIFIED_CLASSES, assets: OTHER_ASSETS },
    editable: true,
  },
  {
    rowKey: 'designated',
    label: '指定为以公允价值计量且其变动计入当期损益的金融资产',
    kind: 'category',
    indent: 0,
    childKeys: ['designated-debt', 'designated-other'],
    editable: false,
  },
  {
    rowKey: 'designated-debt',
    label: '其中：债务工具投资',
    kind: 'detail',
    indent: 1,
    source: { classes: DESIGNATED_CLASSES, assets: ['debt'] },
    editable: true,
  },
  {
    rowKey: 'designated-other',
    label: '其他',
    kind: 'detail',
    indent: 1,
    source: { classes: DESIGNATED_CLASSES, assets: DESIGNATED_OTHER_ASSETS },
    editable: true,
  },
]

export function createEmptyDerivativeRow(partial?: Partial<G1SoeDerivativeRow>): G1SoeDerivativeRow {
  return {
    rowId: partial?.rowId
      ?? `drv-${typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : Date.now().toString(36) + Math.random().toString(36).slice(2)}`,
    label: partial?.label ?? '',
    endAmount: parseNum(partial?.endAmount),
    priorAmount: parseNum(partial?.priorAmount),
    reason: partial?.reason ?? '',
    autoFilled: !!partial?.autoFilled,
  }
}

export function sumCarryingAmounts(
  adjRows: G1AdjudicationRow[],
  classes: G1AdjClass[],
  assets: G1AdjAsset[],
): { endAmount: number; priorAmount: number } {
  let endAmount = 0
  let priorAmount = 0
  for (const r of adjRows) {
    if (r.section !== 'carrying' || r.kind !== 'leaf') continue
    if (!r.classKey || !r.assetKey) continue
    if (!classes.includes(r.classKey) || !assets.includes(r.assetKey)) continue
    endAmount += r.closingAudited
    priorAmount += r.openingAudited
  }
  return { endAmount, priorAmount }
}

/** 从 G1-1 store JSON 抽出国企披露明细金额 */
export function extractSoeAmountsFromAdjStore(raw: string | null | undefined): Record<string, { endAmount: number; priorAmount: number }> {
  const store = parseG1AdjStore(raw)
  const adjRows = buildG1AdjudicationRows(store)
  const out: Record<string, { endAmount: number; priorAmount: number }> = {}
  for (const def of G1_SOE_TRADING_ROW_DEFS) {
    if (!def.source) continue
    out[def.rowKey] = sumCarryingAmounts(adjRows, def.source.classes, def.source.assets)
  }
  out.derivative = sumCarryingAmounts(
    adjRows,
    ['trading', 'classified', 'designated'],
    ['derivative'],
  )
  return out
}

export function buildDefaultTradingRows(
  amounts?: Record<string, { endAmount: number; priorAmount: number }>,
): G1SoeTradingRow[] {
  const byKey = new Map<string, G1SoeTradingRow>()
  for (const def of G1_SOE_TRADING_ROW_DEFS) {
    const amt = amounts?.[def.rowKey]
    byKey.set(def.rowKey, {
      rowKey: def.rowKey,
      label: def.label,
      kind: def.kind,
      indent: def.indent,
      endAmount: amt?.endAmount ?? 0,
      priorAmount: amt?.priorAmount ?? 0,
      autoFilled: !!amt && (amt.endAmount !== 0 || amt.priorAmount !== 0),
      editable: def.editable,
    })
  }
  // category = 子项合计
  for (const def of G1_SOE_TRADING_ROW_DEFS) {
    if (def.kind !== 'category' || !def.childKeys) continue
    const row = byKey.get(def.rowKey)!
    row.endAmount = def.childKeys.reduce((s, k) => s + (byKey.get(k)?.endAmount ?? 0), 0)
    row.priorAmount = def.childKeys.reduce((s, k) => s + (byKey.get(k)?.priorAmount ?? 0), 0)
    row.autoFilled = def.childKeys.some((k) => byKey.get(k)?.autoFilled)
  }
  return G1_SOE_TRADING_ROW_DEFS.map((d) => byKey.get(d.rowKey)!)
}

export function recomputeCategoryTotals(rows: G1SoeTradingRow[]): G1SoeTradingRow[] {
  const byKey = new Map(rows.map((r) => [r.rowKey, { ...r }]))
  for (const def of G1_SOE_TRADING_ROW_DEFS) {
    if (def.kind !== 'category' || !def.childKeys) continue
    const row = byKey.get(def.rowKey)
    if (!row) continue
    row.endAmount = def.childKeys.reduce((s, k) => s + (byKey.get(k)?.endAmount ?? 0), 0)
    row.priorAmount = def.childKeys.reduce((s, k) => s + (byKey.get(k)?.priorAmount ?? 0), 0)
  }
  return G1_SOE_TRADING_ROW_DEFS.map((d) => byKey.get(d.rowKey)!).filter(Boolean)
}

export function tradingTotal(rows: G1SoeTradingRow[]): { endAmount: number; priorAmount: number } {
  const cats = rows.filter((r) => r.kind === 'category')
  return {
    endAmount: cats.reduce((s, r) => s + r.endAmount, 0),
    priorAmount: cats.reduce((s, r) => s + r.priorAmount, 0),
  }
}

export interface G1SoePersistedV2 {
  version: 2
  trading: Array<{ rowKey: string; endAmount: number; priorAmount: number; autoFilled?: boolean }>
  derivative: G1SoeDerivativeRow[]
}

export function serializeSoeRows(trading: G1SoeTradingRow[], derivative: G1SoeDerivativeRow[]): string {
  const payload: G1SoePersistedV2 = {
    version: 2,
    trading: trading.map((r) => ({
      rowKey: r.rowKey,
      endAmount: r.endAmount,
      priorAmount: r.priorAmount,
      autoFilled: r.autoFilled,
    })),
    derivative,
  }
  return JSON.stringify(payload)
}

export function parseSoePersisted(
  jsonStr: string | null | undefined,
): { trading: G1SoeTradingRow[]; derivative: G1SoeDerivativeRow[] } | null {
  if (!jsonStr) return null
  try {
    const parsed = JSON.parse(jsonStr)
    if (parsed && parsed.version === 2 && Array.isArray(parsed.trading)) {
      const byKey = new Map(
        (parsed.trading as G1SoePersistedV2['trading']).map((r) => [r.rowKey, r]),
      )
      const trading = recomputeCategoryTotals(
        G1_SOE_TRADING_ROW_DEFS.map((def) => {
          const saved = byKey.get(def.rowKey)
          return {
            rowKey: def.rowKey,
            label: def.label,
            kind: def.kind,
            indent: def.indent,
            endAmount: parseNum(saved?.endAmount),
            priorAmount: parseNum(saved?.priorAmount),
            autoFilled: !!saved?.autoFilled,
            editable: def.editable,
          }
        }),
      )
      const derivative = Array.isArray(parsed.derivative)
        ? (parsed.derivative as G1SoeDerivativeRow[]).map((r) => createEmptyDerivativeRow(r))
        : []
      return { trading, derivative }
    }
    // 旧版扁平数组：无法可靠映射，返回 null 走默认模板
    return null
  } catch {
    return null
  }
}
