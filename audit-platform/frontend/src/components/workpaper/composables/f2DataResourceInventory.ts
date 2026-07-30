/**
 * f2DataResourceInventory — 「确认为存货的数据资源」表纯函数模型（上市/国企共用）
 *
 * 行结构逐字取自附注模版：
 *   `基础数据/附注模版/上市报表附注.md` §存货 → 确认为存货的数据资源
 *   `基础数据/附注模版/国企报表附注.md` §存货 → 确认为存货的数据资源
 * 唯一差异：第 12 行段标题上市为「二、存货跌价准备」、国企为「二、跌价准备」。
 *
 * 公式口径对齐平台校验预设 `note_check_preset_formulas.json`：
 *   F9-7  账面原值段：1.期初 + 2.本期增加 − 3.本期减少 = 4.期末（逐列）
 *   F9-8  跌价准备段：同上
 *   F9-9  期末账面价值 = 账面原值期末 − 跌价准备期末（逐列）
 *   F9-9a 期初账面价值 = 账面原值期初 − 跌价准备期初（逐列）
 *   F9-10 「其中」子项之和 ≤ 父项（**校验**而非公式 → 父项独立录入，超额仅告警）
 *   F9-11 每行合计列 = 外购 + 自行加工 + 其他方式
 *
 * Spec: .kiro/specs/f2-inventory-disclosure-template-alignment/ R3
 */
import { parseNum } from './useF2InvMaiFormulaEngine'

export type F2DrVariant = 'listed' | 'soe'

/** 三个可录入来源列（`total` 为派生列，不在此列举） */
export type DrColKey = 'purchased' | 'selfProcessed' | 'other'

export const DR_INPUT_COLS: readonly DrColKey[] = ['purchased', 'selfProcessed', 'other']

/** 列头逐字取自附注模版 */
export const DR_COL_LABELS: Record<DrColKey | 'total', string> = {
  purchased: '外购的数据资源存货',
  selfProcessed: '自行加工的数据资源存货',
  other: '其他方式取得的数据资源存货',
  total: '合计',
}

/**
 * - `section`：段标题行（一/二/三），不可录入
 * - `input`：可录入行
 * - `sub`：「其中」子项，可录入，缩进显示
 * - `derived`：公式行，只读
 */
export type DrRowKind = 'section' | 'input' | 'sub' | 'derived'

export interface DrRawValues {
  purchased: number
  selfProcessed: number
  other: number
}

/** 持久化形状：仅存 `input` / `sub` 行的三个来源列 */
export type DrValueMap = Record<string, Partial<DrRawValues>>

interface DrRowDef {
  rowKey: string
  label: string
  kind: DrRowKind
  /** 0=顶层，1=「其中」子项 */
  indent: 0 | 1
  /** 父项 rowKey（仅 `sub` 行有） */
  parent?: string
}

/** 21 行骨架（顺序即渲染顺序，逐字对齐附注模版） */
const ROW_DEFS: readonly DrRowDef[] = [
  { rowKey: 'gross-section', label: '一、账面原值', kind: 'section', indent: 0 },
  { rowKey: 'gross-open', label: '1.期初余额', kind: 'input', indent: 0 },
  { rowKey: 'gross-inc', label: '2.本期增加金额', kind: 'input', indent: 0 },
  { rowKey: 'gross-inc-purchase', label: '其中：购入', kind: 'sub', indent: 1, parent: 'gross-inc' },
  { rowKey: 'gross-inc-collect', label: '采集加工', kind: 'sub', indent: 1, parent: 'gross-inc' },
  { rowKey: 'gross-inc-other', label: '其他增加', kind: 'sub', indent: 1, parent: 'gross-inc' },
  { rowKey: 'gross-dec', label: '3.本期减少金额', kind: 'input', indent: 0 },
  { rowKey: 'gross-dec-sale', label: '其中：出售', kind: 'sub', indent: 1, parent: 'gross-dec' },
  { rowKey: 'gross-dec-invalid', label: '失效且终止确认', kind: 'sub', indent: 1, parent: 'gross-dec' },
  { rowKey: 'gross-dec-other', label: '其他减少', kind: 'sub', indent: 1, parent: 'gross-dec' },
  { rowKey: 'gross-end', label: '4.期末余额', kind: 'derived', indent: 0 },
  { rowKey: 'imp-section', label: '二、存货跌价准备', kind: 'section', indent: 0 },
  { rowKey: 'imp-open', label: '1.期初余额', kind: 'input', indent: 0 },
  { rowKey: 'imp-inc', label: '2.本期增加金额', kind: 'input', indent: 0 },
  { rowKey: 'imp-dec', label: '3.本期减少金额', kind: 'input', indent: 0 },
  { rowKey: 'imp-dec-reversal', label: '其中：转回', kind: 'sub', indent: 1, parent: 'imp-dec' },
  { rowKey: 'imp-dec-writeoff', label: '转销', kind: 'sub', indent: 1, parent: 'imp-dec' },
  { rowKey: 'imp-end', label: '4.期末余额', kind: 'derived', indent: 0 },
  { rowKey: 'nv-section', label: '三、账面价值', kind: 'section', indent: 0 },
  { rowKey: 'nv-end', label: '1.期末账面价值', kind: 'derived', indent: 0 },
  { rowKey: 'nv-open', label: '2.期初账面价值', kind: 'derived', indent: 0 },
]

/** 国企版段标题用词差异（附注模版：国企作「二、跌价准备」） */
const SOE_LABEL_OVERRIDES: Record<string, string> = {
  'imp-section': '二、跌价准备',
}

export interface DrRow extends DrRawValues {
  rowKey: string
  label: string
  kind: DrRowKind
  indent: 0 | 1
  /** 合计列 = 三个来源列之和（F9-11） */
  total: number
  /** 父项行且「其中」子项之和超过父项 → true（仅告警，不阻断） */
  subExcess: boolean
}

/** 合计列：外购 + 自行加工 + 其他方式（F9-11） */
export function calcDrTotals(v: DrRawValues): number {
  return parseNum(v.purchased) + parseNum(v.selfProcessed) + parseNum(v.other)
}

/** 期末余额 = 期初 + 本期增加 − 本期减少（F9-7 / F9-8） */
export function calcDrEnding(open: number, inc: number, dec: number): number {
  return parseNum(open) + parseNum(inc) - parseNum(dec)
}

/** 「其中」子项之和是否超过父项（F9-10 为 ≤ 校验，超出即异常） */
export function checkDrSubExcess(parent: number, subs: readonly number[]): boolean {
  const sum = subs.reduce((s, x) => s + parseNum(x), 0)
  // 容差 0.01 元，避免分位舍入误报
  return sum - parseNum(parent) > 0.01
}

function readCol(values: DrValueMap, rowKey: string, col: DrColKey): number {
  return parseNum(values?.[rowKey]?.[col])
}

/** 全部可录入行（`input` + `sub`）三列皆 0 → 视为未填 */
export function isDataResourceEmpty(values: DrValueMap | null | undefined): boolean {
  if (!values) return true
  for (const def of ROW_DEFS) {
    if (def.kind !== 'input' && def.kind !== 'sub') continue
    for (const col of DR_INPUT_COLS) {
      if (parseNum(values[def.rowKey]?.[col]) !== 0) return false
    }
  }
  return true
}

/**
 * 按持久化值构建 21 行渲染模型：派生行读时重算，不依赖落库值。
 *
 * @param values 持久化的 `input` / `sub` 行值
 * @param variant 上市 / 国企（仅影响第 12 行段标题）
 */
export function buildDataResourceRows(
  values: DrValueMap | null | undefined,
  variant: F2DrVariant,
): DrRow[] {
  const v = values || {}

  // 先算派生行的三列值（逐列独立，F9-7~F9-9a）
  const derived: Record<string, DrRawValues> = {
    'gross-end': { purchased: 0, selfProcessed: 0, other: 0 },
    'imp-end': { purchased: 0, selfProcessed: 0, other: 0 },
    'nv-end': { purchased: 0, selfProcessed: 0, other: 0 },
    'nv-open': { purchased: 0, selfProcessed: 0, other: 0 },
  }
  for (const col of DR_INPUT_COLS) {
    const grossOpen = readCol(v, 'gross-open', col)
    const grossEnd = calcDrEnding(grossOpen, readCol(v, 'gross-inc', col), readCol(v, 'gross-dec', col))
    const impOpen = readCol(v, 'imp-open', col)
    const impEnd = calcDrEnding(impOpen, readCol(v, 'imp-inc', col), readCol(v, 'imp-dec', col))
    derived['gross-end'][col] = grossEnd
    derived['imp-end'][col] = impEnd
    derived['nv-end'][col] = grossEnd - impEnd
    derived['nv-open'][col] = grossOpen - impOpen
  }

  // 父项 → 子项 rowKey 索引（用于超额告警）
  const subsByParent = new Map<string, string[]>()
  for (const def of ROW_DEFS) {
    if (def.kind === 'sub' && def.parent) {
      const list = subsByParent.get(def.parent) || []
      list.push(def.rowKey)
      subsByParent.set(def.parent, list)
    }
  }

  return ROW_DEFS.map((def) => {
    const label = variant === 'soe' ? (SOE_LABEL_OVERRIDES[def.rowKey] ?? def.label) : def.label

    let vals: DrRawValues
    if (def.kind === 'section') {
      vals = { purchased: 0, selfProcessed: 0, other: 0 }
    } else if (def.kind === 'derived') {
      vals = derived[def.rowKey] ?? { purchased: 0, selfProcessed: 0, other: 0 }
    } else {
      vals = {
        purchased: readCol(v, def.rowKey, 'purchased'),
        selfProcessed: readCol(v, def.rowKey, 'selfProcessed'),
        other: readCol(v, def.rowKey, 'other'),
      }
    }

    // 超额判定按「合计列」口径（三列之和），与 UI 告警粒度一致
    let subExcess = false
    const subKeys = subsByParent.get(def.rowKey)
    if (subKeys?.length) {
      subExcess = checkDrSubExcess(
        calcDrTotals(vals),
        subKeys.map((k) => calcDrTotals({
          purchased: readCol(v, k, 'purchased'),
          selfProcessed: readCol(v, k, 'selfProcessed'),
          other: readCol(v, k, 'other'),
        })),
      )
    }

    return {
      rowKey: def.rowKey,
      label,
      kind: def.kind,
      indent: def.indent,
      ...vals,
      total: def.kind === 'section' ? 0 : calcDrTotals(vals),
      subExcess,
    }
  })
}

/** 勾稽容差：0.01 元，避免分位舍入误报 */
const TIE_TOLERANCE = 0.01

/** 数据资源表 ↔ (1) 分类表「数据资源」行的一条勾稽 */
export interface DrTieCheck {
  key: 'gross-end' | 'gross-open' | 'imp-end' | 'imp-open'
  /** 校验预设编号（`note_check_preset_formulas.json`） */
  preset: string
  label: string
  /** 本表合计列取值 */
  detail: number
  /** (1) 分类表「数据资源」行取值 */
  classified: number
  diff: number
  ok: boolean
}

/** (1) 分类表「数据资源」行的四个口径（上市/国企同形，期初列语义分别为上年年末/期初） */
export interface DrClassifiedRow {
  endGross: number
  endImpairment: number
  priorGross: number
  priorImpairment: number
}

/**
 * 数据资源明细表与 (1) 分类表「数据资源」行的交叉勾稽。
 *
 * 口径对齐平台校验预设：
 *   F9-12  账面原值段.期末余额.合计列 = ①分类表「数据资源」行.期末账面余额
 *   F9-12a 账面原值段.期初余额.合计列 = ①分类表「数据资源」行.期初账面余额
 *   F9-13  跌价准备段.期末余额.合计列 = ①分类表「数据资源」行.期末跌价准备
 *   F9-13a 跌价准备段.期初余额.合计列 = ①分类表「数据资源」行.期初跌价准备
 *
 * 本表未填（全 0）时返回空数组：避免「分类表有数但明细未编制」阶段满屏告警。
 */
export function buildDataResourceTieChecks(
  values: DrValueMap | null | undefined,
  classified: DrClassifiedRow | null | undefined,
  variant: F2DrVariant,
): DrTieCheck[] {
  if (isDataResourceEmpty(values)) return []

  const rows = buildDataResourceRows(values, variant)
  const totalOf = (rowKey: string): number =>
    rows.find((r) => r.rowKey === rowKey)?.total ?? 0

  const c = classified ?? { endGross: 0, endImpairment: 0, priorGross: 0, priorImpairment: 0 }
  const priorLabel = variant === 'soe' ? '期初' : '上年年末'

  const specs: Array<{
    key: DrTieCheck['key']
    preset: string
    label: string
    detail: number
    classified: number
  }> = [
    {
      key: 'gross-end',
      preset: 'F9-12',
      label: '账面原值期末余额',
      detail: totalOf('gross-end'),
      classified: parseNum(c.endGross),
    },
    {
      key: 'gross-open',
      preset: 'F9-12a',
      label: `账面原值${priorLabel}余额`,
      detail: totalOf('gross-open'),
      classified: parseNum(c.priorGross),
    },
    {
      key: 'imp-end',
      preset: 'F9-13',
      label: '跌价准备期末余额',
      detail: totalOf('imp-end'),
      classified: parseNum(c.endImpairment),
    },
    {
      key: 'imp-open',
      preset: 'F9-13a',
      label: `跌价准备${priorLabel}余额`,
      detail: totalOf('imp-open'),
      classified: parseNum(c.priorImpairment),
    },
  ]

  return specs.map((s) => {
    const diff = s.detail - s.classified
    return { ...s, diff, ok: Math.abs(diff) < TIE_TOLERANCE }
  })
}

/** 同步载荷行（键名与 `columns` 的 `key` 一致） */
export interface DrSyncRow {
  label: string
  purchased: number
  self_processed: number
  other: number
  total: number
}

export function buildDataResourceSyncRows(rows: readonly DrRow[]): DrSyncRow[] {
  return rows.map((r) => ({
    label: r.label,
    purchased: r.purchased,
    self_processed: r.selfProcessed,
    other: r.other,
    total: r.total,
  }))
}

/** 写入单元格：仅 `input` / `sub` 行可写，其余静默忽略 */
export function setDrCell(
  values: DrValueMap,
  rowKey: string,
  col: DrColKey,
  value: number | string | null | undefined,
): DrValueMap {
  const def = ROW_DEFS.find((d) => d.rowKey === rowKey)
  if (!def || (def.kind !== 'input' && def.kind !== 'sub')) return values
  return {
    ...values,
    [rowKey]: { ...(values[rowKey] || {}), [col]: parseNum(value) },
  }
}

export const F2_DR_ROW_COUNT = ROW_DEFS.length
