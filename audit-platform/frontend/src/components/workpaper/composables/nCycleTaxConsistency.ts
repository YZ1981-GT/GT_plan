/**
 * N 循环税务类披露内部勾稽（N2 应交税费 / N4 税金及附加 / N5 所得税费用）
 *
 * 规则**全部取自源模板公式**，不自造校验：
 *
 * | 规则 | 源模板依据 |
 * |---|---|
 * | N2 上市 合计 = 各税项之和 | `B23=SUM(B8:B22)` / `C23=SUM(C8:C22)` |
 * | N2 国企 每行 期末余额 = 期初 + 本期应交 − 本期已交 | `E8=B8+C8-D8` |
 * | N2 国企 四列合计 = 各列之和 | `B23..E23=SUM(…)` |
 * | N4 上市 合计 = 各税费之和 | `B17=SUM(B8:B16)` / `C17=SUM(C8:C16)` |
 * | N5 表(1) 合计 = 当期所得税 + 递延所得税 | 上市 `C11=SUM(C9:C10)` / 国企 `C11=SUM(C8:C10)` |
 * | N5 上市 表(2)「所得税费用」行 = 第 2 行至倒数第 2 行之和 | 上市注 1 |
 * | N5 国企 表(2) 合计 = 各调整项之和 | `合  计` 行 |
 * | N5 跨表：表(2) 所得税费用 = 表(1) 合计 | 同一金额两处列示 |
 *
 * 共用原语（容差 0.01 元 / null → skip / 汇总）在
 * `composables/shared/disclosureConsistency.ts`。
 *
 * spec: `.kiro/specs/n-cycle-tax-disclosure-alignment/` R4 / Task 7.2
 */
import {
  eqCheck,
  nz,
  segmentSumCheck,
  sumNullable,
  type NullableAmount,
  type WpCheckResult,
} from './shared/disclosureConsistency'

export type { NullableAmount, WpCheckResult } from './shared/disclosureConsistency'

// ─── N2 应交税费 ─────────────────────────────────────────────────────────────

/** 上市：双期余额行 */
export interface N2ListedRowLike {
  item: string
  end: NullableAmount
  prior: NullableAmount
}

/** 国企：变动行（`end` 为行内公式结果，由编制模型算出后传入） */
export interface N2SoeRowLike {
  item: string
  opening: NullableAmount
  payable: NullableAmount
  paid: NullableAmount
  end: NullableAmount
}

export interface N2ListedTotals {
  end: NullableAmount
  prior: NullableAmount
}

export interface N2SoeTotals {
  opening: NullableAmount
  payable: NullableAmount
  paid: NullableAmount
  end: NullableAmount
}

const _R_N2_LISTED_SUM = '合计 = 各税项之和（源模板 =SUM(B8:B22) / =SUM(C8:C22)）'
const _R_N2_SOE_ROW = '期末余额 = 期初余额 + 本期应交 − 本期已交（源模板 =B8+C8-D8）'
const _R_N2_SOE_SUM = '合计 = 该列各税项之和（源模板 =SUM(B8:B22) 等四列）'

export function runN2ListedChecks(
  rows: readonly N2ListedRowLike[],
  totals: N2ListedTotals,
): WpCheckResult[] {
  return [
    segmentSumCheck('合计（期末余额）', _R_N2_LISTED_SUM, rows.map((r) => nz(r.end)), totals.end, ['N2-1']),
    segmentSumCheck('合计（上年年末余额）', _R_N2_LISTED_SUM, rows.map((r) => nz(r.prior)), totals.prior, ['N2-1']),
  ].filter((x): x is WpCheckResult => x !== null)
}

export function runN2SoeChecks(
  rows: readonly N2SoeRowLike[],
  totals: N2SoeTotals,
): WpCheckResult[] {
  const out: WpCheckResult[] = []
  // 逐行恒等式（源模板行内公式）—— 任一项缺失即 skip，不误报
  for (const r of rows) {
    const right = sumNullable([nz(r.opening), nz(r.payable)])
    const expected =
      right === null || nz(r.paid) === null
        ? null
        : Math.round((right - (nz(r.paid) as number)) * 100) / 100
    out.push(
      eqCheck(`${r.item} 期末余额`, _R_N2_SOE_ROW, nz(r.end), expected, ['N2-2']),
    )
  }
  for (const [key, label] of [
    ['opening', '期初余额'],
    ['payable', '本期应交'],
    ['paid', '本期已交'],
    ['end', '期末余额'],
  ] as const) {
    const c = segmentSumCheck(
      `合计（${label}）`,
      _R_N2_SOE_SUM,
      rows.map((r) => nz(r[key])),
      totals[key],
      ['N2-2'],
    )
    if (c) out.push(c)
  }
  return out
}

// ─── N4 税金及附加（仅上市）──────────────────────────────────────────────────

export interface N4RowLike {
  item: string
  current: NullableAmount
  prior: NullableAmount
}

const _R_N4_SUM = '合计 = 各税费项目之和（源模板 =SUM(B8:B16) / =SUM(C8:C16)）'

export function runN4ListedChecks(
  rows: readonly N4RowLike[],
  totals: { current: NullableAmount; prior: NullableAmount },
): WpCheckResult[] {
  return [
    segmentSumCheck('合计（本期发生额）', _R_N4_SUM, rows.map((r) => nz(r.current)), totals.current, ['N4-1']),
    segmentSumCheck('合计（上期发生额）', _R_N4_SUM, rows.map((r) => nz(r.prior)), totals.prior, ['N4-1']),
  ].filter((x): x is WpCheckResult => x !== null)
}

// ─── N5 所得税费用 ───────────────────────────────────────────────────────────

export interface N5RowLike {
  item: string
  current: NullableAmount
  prior: NullableAmount
}

export type N5Variant = 'listed' | 'soe'

export interface N5ConsistencyInput {
  /** 表(1) 明细行（不含合计） */
  detailRows: readonly N5RowLike[]
  /** 表(1) 合计 */
  detailTotals: { current: NullableAmount; prior: NullableAmount }
  /**
   * 表(2) 行。
   * - 上市：末行是「所得税费用」勾稽落点（**不是**合计行）
   * - 国企：末行是「合  计」
   * 传入时**不含**末行，末行单独由 `reconcileTail` 给出。
   */
  reconcileRows: readonly N5RowLike[]
  /** 表(2) 末行（上市=所得税费用行 / 国企=合计行） */
  reconcileTail: { current: NullableAmount; prior: NullableAmount }
}

const _R_N5_DETAIL_SUM_LISTED =
  '合计 = 按税法计算的当期所得税 + 递延所得税费用（源模板 =SUM(C9:C10)）'
const _R_N5_DETAIL_SUM_SOE =
  '合计 = 当期所得税费用 + 递延所得税调整 + 其他（源模板 =SUM(C8:C10)）'
const _R_N5_TAIL_LISTED =
  '「所得税费用」行 = 第二行至倒数第二行之和（源模板注 1）'
const _R_N5_TAIL_SOE = '合计 = 各调整项之和（源模板 合  计 行）'
const _R_N5_CROSS =
  '表(2) 所得税费用 / 合计 = 表(1) 合计（同一金额两处列示）'

export function runN5Checks(
  variant: N5Variant,
  input: N5ConsistencyInput,
): WpCheckResult[] {
  const out: Array<WpCheckResult | null> = []
  const detailRule = variant === 'listed' ? _R_N5_DETAIL_SUM_LISTED : _R_N5_DETAIL_SUM_SOE
  const tailRule = variant === 'listed' ? _R_N5_TAIL_LISTED : _R_N5_TAIL_SOE
  const tailLabel = variant === 'listed' ? '表(2)「所得税费用」行' : '表(2) 合计'

  for (const [key, label] of [['current', '本期发生额'], ['prior', '上期发生额']] as const) {
    out.push(
      segmentSumCheck(
        `表(1) 合计（${label}）`,
        detailRule,
        input.detailRows.map((r) => nz(r[key])),
        input.detailTotals[key],
        ['N5-1'],
      ),
    )
    out.push(
      segmentSumCheck(
        `${tailLabel}（${label}）`,
        tailRule,
        input.reconcileRows.map((r) => nz(r[key])),
        input.reconcileTail[key],
        ['N5-2'],
      ),
    )
    // 跨表：两处列示的同一金额必须相等
    out.push(
      eqCheck(
        `跨表 ${tailLabel} = 表(1) 合计（${label}）`,
        _R_N5_CROSS,
        input.reconcileTail[key],
        input.detailTotals[key],
        ['N5-1', 'N5-2'],
      ),
    )
  }
  return out.filter((x): x is WpCheckResult => x !== null)
}
