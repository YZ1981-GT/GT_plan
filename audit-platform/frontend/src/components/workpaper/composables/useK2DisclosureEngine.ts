/**
 * K2 披露表纯函数引擎（无 Vue 依赖，便于单测）
 *
 * 三类计算：
 * 1. `sumMainRows` —— 主表合计行（各明细行之和，逐列）
 * 2. `recalcContractCost` —— 合同取得成本：合计列 = 各类别之和；
 *    期末余额行 = 期初余额 + 本年增加 − 本年摊销 − 本年计提减值损失
 * 3. `checkK2Consistency` —— 披露内部勾稽（校验预设 F13-1 / F13-1a / F13-2 + 表②公式）
 *
 * spec: .kiro/specs/k2-other-current-assets-disclosure-alignment/ R6
 */
import {
  K2_CONTRACT_COST_ROWS,
  type K2ContractCostSnapshot,
  type K2MainRow,
} from './k2NoteSectionMap'

/** 金额比较容差（元） */
export const K2_TOLERANCE = 0.01

export interface K2MainTotals {
  end: number
  prior: number
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export function sumMainRows(rows: readonly K2MainRow[]): K2MainTotals {
  return (rows ?? []).reduce<K2MainTotals>(
    (acc, r) => ({
      end: acc.end + num(r?.endAmount),
      prior: acc.prior + num(r?.priorAmount),
    }),
    { end: 0, prior: 0 },
  )
}

const ROW_OPENING = K2_CONTRACT_COST_ROWS.indexOf('期初余额')
const ROW_INCREASE = K2_CONTRACT_COST_ROWS.indexOf('本年增加')
const ROW_AMORTIZE = K2_CONTRACT_COST_ROWS.indexOf('本年摊销')
const ROW_IMPAIRMENT = K2_CONTRACT_COST_ROWS.indexOf('本年计提减值损失')
const ROW_CLOSING = K2_CONTRACT_COST_ROWS.indexOf('期末余额')

/**
 * 重算合同取得成本矩阵：期末余额行按公式派生（只读行）。
 * 返回**新**矩阵（`cells[rowIdx][catIdx]`），不修改入参。
 */
export function recalcContractCost(cells: readonly number[][], catCount: number): number[][] {
  const n = Math.max(1, catCount)
  const out: number[][] = K2_CONTRACT_COST_ROWS.map((_l, rowIdx) =>
    Array.from({ length: n }, (_v, catIdx) => num(cells?.[rowIdx]?.[catIdx])),
  )
  for (let c = 0; c < n; c++) {
    out[ROW_CLOSING][c] =
      out[ROW_OPENING][c] + out[ROW_INCREASE][c] - out[ROW_AMORTIZE][c] - out[ROW_IMPAIRMENT][c]
  }
  return out
}

/** 合同取得成本某行的合计（各类别之和） */
export function contractCostRowTotal(cells: readonly number[][], rowIdx: number, catCount: number): number {
  let total = 0
  for (let c = 0; c < Math.max(1, catCount); c++) total += num(cells?.[rowIdx]?.[c])
  return total
}

export type K2CheckLevel = 'ok' | 'warn' | 'error'

export interface K2ConsistencyItem {
  /** 展示名 */
  label: string
  /** 规则原文（tooltip） */
  rule: string
  left: number
  right: number
  diff: number
  level: K2CheckLevel
  /** 补充说明（可空） */
  detail?: string
}

export interface K2ConsistencyInput {
  variant: 'listed' | 'soe'
  mainRows: readonly K2MainRow[]
  /** K2-1 审定表期末审定数（可空 → 跳过该项） */
  auditedEnd?: number | null
  /** K2-1 审定表期初数（可空 → 跳过该项） */
  auditedPrior?: number | null
  contractCost?: K2ContractCostSnapshot | null
}

function mk(
  label: string,
  rule: string,
  left: number,
  right: number,
  level: K2CheckLevel = 'error',
  detail?: string,
): K2ConsistencyItem {
  const diff = left - right
  return {
    label,
    rule,
    left,
    right,
    diff,
    level: Math.abs(diff) <= K2_TOLERANCE ? 'ok' : level,
    ...(detail ? { detail } : {}),
  }
}

/**
 * 披露内部勾稽。只取**源模板 / 校验预设可判定**的关系，不臆造。
 */
export function checkK2Consistency(input: K2ConsistencyInput): K2ConsistencyItem[] {
  const items: K2ConsistencyItem[] = []
  const totals = sumMainRows(input.mainRows ?? [])
  const priorLabel = input.variant === 'listed' ? '上年年末余额' : '期初余额'

  if (input.auditedEnd != null) {
    items.push(
      mk(
        '明细表合计期末 = 审定数',
        `F13-1：报表「其他流动资产」期末 = ①明细表合计行期末余额（数据来源 K2-1 审定表）`,
        totals.end,
        num(input.auditedEnd),
        'error',
        '差异通常源于披露明细未按审定数更新',
      ),
    )
  }
  if (input.auditedPrior != null) {
    items.push(
      mk(
        `明细表合计${priorLabel} = 期初审定数`,
        `F13-1a：报表「其他流动资产」期初 = ①明细表合计行${priorLabel}`,
        totals.prior,
        num(input.auditedPrior),
        'warn',
      ),
    )
  }

  const cc = input.contractCost
  if (input.variant === 'listed' && cc?.enabled) {
    const catCount = Math.max(1, (cc.categories ?? []).length)
    const closingActual = contractCostRowTotal(cc.cells ?? [], ROW_CLOSING, catCount)
    const closingExpected =
      contractCostRowTotal(cc.cells ?? [], ROW_OPENING, catCount)
      + contractCostRowTotal(cc.cells ?? [], ROW_INCREASE, catCount)
      - contractCostRowTotal(cc.cells ?? [], ROW_AMORTIZE, catCount)
      - contractCostRowTotal(cc.cells ?? [], ROW_IMPAIRMENT, catCount)
    items.push(
      mk(
        '合同取得成本期末余额',
        '期末余额 = 期初余额 + 本年增加 − 本年摊销 − 本年计提减值损失（合计列）',
        closingActual,
        closingExpected,
      ),
    )

    const ccRowLabel = '合同取得成本'
    const mainCc = (input.mainRows ?? []).find(r => String(r?.label ?? '').trim() === ccRowLabel)
    if (mainCc) {
      items.push(
        mk(
          '①表「合同取得成本」行 = ②表期末余额',
          '①明细表「合同取得成本」期末余额 = ②合同取得成本变动表期末余额合计列',
          num(mainCc.endAmount),
          closingActual,
          'warn',
          '源模板要求两表口径一致；②表按资产主要类别展开',
        ),
      )
    }
  }

  return items
}

/** 勾稽面板汇总态 */
export function k2ConsistencySummary(items: readonly K2ConsistencyItem[]): {
  total: number
  failed: number
  level: K2CheckLevel
} {
  const failedItems = items.filter(i => i.level !== 'ok')
  const hasError = failedItems.some(i => i.level === 'error')
  return {
    total: items.length,
    failed: failedItems.length,
    level: failedItems.length === 0 ? 'ok' : hasError ? 'error' : 'warn',
  }
}
