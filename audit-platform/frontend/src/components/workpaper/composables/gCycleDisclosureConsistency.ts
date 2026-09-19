/**
 * gCycleDisclosureConsistency — G10/G11/G13/G14 披露表内部勾稽引擎。
 *
 * 规则全取源模板公式或审计逻辑（禁自造校验）：
 * - 披露合计 = 审定表审定合计（跨表勾稽）
 * - 各损益类：本期发生额合计 ↔ 试算表 TB 本期发生额
 * - 资产负债表类：期末余额合计 ↔ 试算表 TB 期末余额
 *
 * 复用 `shared/disclosureConsistency.ts` 的 `eqCheck`/`summarizeChecks`。
 *
 * spec: g-cycle-extraction-mapping-and-disclosure-alignment Wave 6.4
 */
import {
  eqCheck,
  nz,
  summarizeChecks,
  type NullableAmount,
  type WpCheckResult,
  type WpCheckSummary,
} from './shared/disclosureConsistency'

// ─── G11 投资收益 ─────────────────────────────────────────────────────────

export interface G11ConsistencyInput {
  /** 披露表本期发生额合计（各行 currentAmount 之和） */
  disclosureTotal: NullableAmount
  /** 审定表 G11-1 本期审定合计 */
  adjudicationTotal: NullableAmount
  /** 试算表 TB 6111 本期发生额 */
  tbAmount: NullableAmount
}

export function checkG11Consistency(input: G11ConsistencyInput): WpCheckResult[] {
  const results: WpCheckResult[] = []
  const r1 = eqCheck(
    '披露合计↔审定合计',
    '披露表投资收益合计 = G11-1 本期审定合计',
    nz(input.disclosureTotal),
    nz(input.adjudicationTotal),
    ['wp:G11-1'],
  )
  if (r1) results.push(r1)
  const r2 = eqCheck(
    '审定合计↔TB',
    'G11-1 本期审定合计 = TB(6111,本期发生额)',
    nz(input.adjudicationTotal),
    nz(input.tbAmount),
    ['tb:6111'],
  )
  if (r2) results.push(r2)
  return results
}

// ─── G13 公允价值变动收益 ──────────────────────────────────────────────────

export interface G13ConsistencyInput {
  disclosureTotal: NullableAmount
  adjudicationTotal: NullableAmount
  tbAmount: NullableAmount
}

export function checkG13Consistency(input: G13ConsistencyInput): WpCheckResult[] {
  const results: WpCheckResult[] = []
  const r1 = eqCheck(
    '披露合计↔审定合计',
    '披露表公允价值变动收益合计 = G13-1 本期审定合计',
    nz(input.disclosureTotal),
    nz(input.adjudicationTotal),
    ['wp:G13-1'],
  )
  if (r1) results.push(r1)
  const r2 = eqCheck(
    '审定合计↔TB',
    'G13-1 本期审定合计 = TB(6101,本期发生额)',
    nz(input.adjudicationTotal),
    nz(input.tbAmount),
    ['tb:6101'],
  )
  if (r2) results.push(r2)
  return results
}

// ─── G14 信用减值损失 ──────────────────────────────────────────────────────

export interface G14ConsistencyInput {
  disclosureTotal: NullableAmount
  adjudicationTotal: NullableAmount
  tbAmount: NullableAmount
}

export function checkG14Consistency(input: G14ConsistencyInput): WpCheckResult[] {
  const results: WpCheckResult[] = []
  const r1 = eqCheck(
    '披露合计↔审定合计',
    '披露表信用减值损失合计 = G14-1 本期审定合计',
    nz(input.disclosureTotal),
    nz(input.adjudicationTotal),
    ['wp:G14-1'],
  )
  if (r1) results.push(r1)
  const r2 = eqCheck(
    '审定合计↔TB',
    'G14-1 本期审定合计 = TB(6702,本期发生额)',
    nz(input.adjudicationTotal),
    nz(input.tbAmount),
    ['tb:6702'],
  )
  if (r2) results.push(r2)
  return results
}

// ─── G10 交易性金融负债 ───────────────────────────────────────────────────

export interface G10ConsistencyInput {
  /** 披露表期末余额合计 */
  disclosureEndTotal: NullableAmount
  /** 审定表 G10-1 期末审定合计 */
  adjudicationEndTotal: NullableAmount
  /** 试算表 TB 2101 期末余额 */
  tbEndAmount: NullableAmount
}

export function checkG10Consistency(input: G10ConsistencyInput): WpCheckResult[] {
  const results: WpCheckResult[] = []
  const r1 = eqCheck(
    '披露合计↔审定合计',
    '披露表交易性金融负债期末合计 = G10-1 期末审定合计',
    nz(input.disclosureEndTotal),
    nz(input.adjudicationEndTotal),
    ['wp:G10-1'],
  )
  if (r1) results.push(r1)
  const r2 = eqCheck(
    '审定合计↔TB',
    'G10-1 期末审定合计 = TB(2101,期末余额)',
    nz(input.adjudicationEndTotal),
    nz(input.tbEndAmount),
    ['tb:2101'],
  )
  if (r2) results.push(r2)
  return results
}

// ─── 统一导出 ─────────────────────────────────────────────────────────────

export { summarizeChecks }
export type { WpCheckResult, WpCheckSummary, NullableAmount }
