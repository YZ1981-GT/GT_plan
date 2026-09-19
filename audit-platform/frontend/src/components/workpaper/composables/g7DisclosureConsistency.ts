/**
 * g7DisclosureConsistency — G7 长期股权投资披露内部勾稽引擎（纯函数，无 Vue 依赖）
 *
 * 6 条规则全部取自 design.md §7（勾稽引擎），不自造审计判断：
 *
 * | 规则          | 表达式                                              | 级别  |
 * |---------------|-----------------------------------------------------|-------|
 * | 分类表合计    | 小计 − 减：长期股权投资减值准备 = 合计              | error |
 * | 主表 roll-forward | 期初 + Σ增加 − Σ减少 = 期末（逐行）           | error |
 * | 分类表 ↔ 主表 | 分类表 小计.期末 ≥ 主表合计                         | warn  |
 * | 披露 ↔ 审定   | 主表 期末账面价值 合计 ↔ G7-1 审定数（1511）        | error |
 * | 减值 ↔ G7-17  | 减值准备期末 ↔ 减值测试表 G7-17 合计                | warn  |
 * | 超额亏损小计  | 合营小计 + 联营小计 = 合计                          | error |
 *
 * 容差 0.01 元；输出 WpCheckResult（平台共用形态）。
 * 缺数据一律 `skip`（不误报）。
 *
 * spec: .kiro/specs/g7-four-table-extraction-and-disclosure-alignment/ Task 6.2
 */
import {
  eqCheck,
  type NullableAmount,
  type WpCheckResult,
  WP_CHECK_TOLERANCE,
  nz,
  sumNullable,
} from './shared/disclosureConsistency'

// ─── 输入接口 ─────────────────────────────────────────────────────────────────

export interface G7ClassificationRow {
  /** 行标签（对子公司投资 / 对合营企业投资 / 对联营企业投资） */
  label: string
  /** 期末余额 */
  endAmount: NullableAmount
}

export interface G7MainTableRow {
  /** 被投资单位名称 */
  name: string
  /** 期初余额（账面价值） */
  openingBook: NullableAmount
  /** 本期增加各列之和（追加/新增 + 权益法损益 + OCI + 其他权益变动 + 其他） */
  totalIncrease: NullableAmount
  /** 本期减少各列之和（减少投资 + 宣告发放现金股利或利润 + 计提减值准备） */
  totalDecrease: NullableAmount
  /** 期末余额（账面价值） */
  closingBook: NullableAmount
}

export interface G7ExcessLossInput {
  /** 合营企业小计 */
  jvSubtotal: NullableAmount
  /** 联营企业小计 */
  associateSubtotal: NullableAmount
  /** 合计 */
  total: NullableAmount
}

export interface G7ConsistencyInput {
  // ── 分类表 ──
  /** 分类表各行（不含小计/减值准备/合计） */
  classificationRows: G7ClassificationRow[]
  /** 分类表「小计」行期末金额 */
  classificationSubtotal: NullableAmount
  /** 分类表「减：长期股权投资减值准备」期末金额 */
  classificationImpairment: NullableAmount
  /** 分类表「合计」行期末金额 */
  classificationTotal: NullableAmount

  // ── 主表 ──
  /** 主表各行（逐行校验 roll-forward） */
  mainTableRows: G7MainTableRow[]
  /** 主表期末账面价值合计（所有行的 closingBook 之和） */
  mainTableClosingTotal: NullableAmount

  // ── 审定数 ──
  /** G7-1 审定数（1511 审定期末账面价值） */
  adjudicatedAmount: NullableAmount

  // ── 减值 ──
  /** 披露表减值准备期末合计 */
  disclosureImpairmentEnd: NullableAmount
  /** G7-17 减值测试表合计 */
  g7_17ImpairmentTotal: NullableAmount

  // ── 超额亏损 ──
  excessLoss: G7ExcessLossInput | null
}

// ─── helpers ─────────────────────────────────────────────────────────────────

function round2(v: number): number {
  return Math.round(v * 100) / 100
}

/** 子集/不等式类：left ≤ right 或 left ≥ right */
function geCheck(
  label: string,
  rule: string,
  left: NullableAmount,
  right: NullableAmount,
  refs: string[],
): WpCheckResult {
  if (left === null || left === undefined || right === null || right === undefined) {
    return { label, rule, left: left ?? null, right: right ?? null, diff: null, level: 'skip', refs }
  }
  const diff = round2(left - right)
  // 分类表小计.期末 ≥ 主表合计（允许容差）
  const ok = diff >= -WP_CHECK_TOLERANCE
  return {
    label,
    rule,
    left: round2(left),
    right: round2(right),
    diff,
    level: ok ? 'ok' : 'warn',
    refs,
  }
}

/** warn 级别的相等校验 */
function warnEqCheck(
  label: string,
  rule: string,
  left: NullableAmount,
  right: NullableAmount,
  refs: string[],
): WpCheckResult {
  if (left === null || left === undefined || right === null || right === undefined) {
    return { label, rule, left: left ?? null, right: right ?? null, diff: null, level: 'skip', refs }
  }
  const diff = round2(left - right)
  const ok = Math.abs(diff) <= WP_CHECK_TOLERANCE
  return {
    label,
    rule,
    left: round2(left),
    right: round2(right),
    diff,
    level: ok ? 'ok' : 'warn',
    refs,
  }
}

// ─── 引擎 ─────────────────────────────────────────────────────────────────────

const REFS_CLASS = ['Note:五、18', 'Note:八、18']
const REFS_MAIN = ['wp:G7-1', 'wp:G7-2']
const REFS_ADJ = ['wp:G7-1']
const REFS_IMPAIRMENT = ['wp:G7-17']
const REFS_EXCESS = ['Note:五、18', 'Note:八、18']

export function buildG7ConsistencyChecks(input: G7ConsistencyInput): WpCheckResult[] {
  const out: WpCheckResult[] = []

  // ── 规则 1：分类表合计 = 小计 − 减：长期股权投资减值准备 ──────────────────
  const derivedTotal =
    input.classificationSubtotal === null || input.classificationImpairment === null
      ? null
      : round2((input.classificationSubtotal ?? 0) - (input.classificationImpairment ?? 0))

  out.push(eqCheck(
    '分类表合计',
    '小计 − 减：长期股权投资减值准备 = 合计',
    input.classificationTotal,
    derivedTotal,
    REFS_CLASS,
  ))

  // ── 规则 2：主表 roll-forward（逐行：期初 + Σ增加 − Σ减少 = 期末） ───────
  const rollIssues: string[] = []
  for (const row of input.mainTableRows) {
    if (row.openingBook === null && row.totalIncrease === null &&
      row.totalDecrease === null && row.closingBook === null) {
      continue // 全空行跳过
    }
    const expected = round2(
      (row.openingBook ?? 0) + (row.totalIncrease ?? 0) - (row.totalDecrease ?? 0),
    )
    const actual = nz(row.closingBook)
    if (actual === null) continue
    const diff = round2(actual - expected)
    if (Math.abs(diff) > WP_CHECK_TOLERANCE) {
      rollIssues.push(`${row.name || '(未命名)'}：期初${row.openingBook ?? 0}+增${row.totalIncrease ?? 0}−减${row.totalDecrease ?? 0}=${expected}，期末${actual}，差${diff}`)
    }
  }
  const hasMainRows = input.mainTableRows.length > 0
  out.push({
    label: '主表 roll-forward',
    rule: '期初 + Σ增加 − Σ减少 = 期末（逐行）',
    left: null,
    right: null,
    diff: null,
    level: !hasMainRows ? 'skip' : (rollIssues.length ? 'error' : 'ok'),
    detail: !hasMainRows
      ? '主表无数据行'
      : (rollIssues.length
        ? `${rollIssues.length} 行不平：${rollIssues.join('；')}`
        : '逐行 roll-forward 一致'),
    refs: REFS_MAIN,
  } as WpCheckResult & { detail?: string })

  // ── 规则 3：分类表 ↔ 主表（分类表小计.期末 ≥ 主表合计） ──────────────────
  // 主表只含权益法投资，成本法子公司投资不在主表
  out.push(geCheck(
    '分类表 ↔ 主表',
    '分类表 小计.期末 ≥ 主表合计（主表只含权益法投资，成本法子公司投资不在主表）',
    input.classificationSubtotal,
    input.mainTableClosingTotal,
    [...REFS_CLASS, ...REFS_MAIN],
  ))

  // ── 规则 4：披露 ↔ 审定（主表期末账面价值合计 ↔ G7-1 审定数 1511） ────────
  out.push(eqCheck(
    '披露 ↔ 审定',
    '主表 期末账面价值 合计 ↔ G7-1 审定数（1511）',
    input.mainTableClosingTotal,
    input.adjudicatedAmount,
    REFS_ADJ,
  ))

  // ── 规则 5：减值 ↔ G7-17（减值准备期末 ↔ 减值测试表 G7-17 合计） ──────────
  out.push(warnEqCheck(
    '减值 ↔ G7-17',
    '减值准备期末 ↔ 减值测试表 G7-17 合计',
    input.disclosureImpairmentEnd,
    input.g7_17ImpairmentTotal,
    REFS_IMPAIRMENT,
  ))

  // ── 规则 6：超额亏损小计（合营小计 + 联营小计 = 合计） ────────────────────
  if (input.excessLoss) {
    const { jvSubtotal, associateSubtotal, total } = input.excessLoss
    const derivedExcess = sumNullable([jvSubtotal, associateSubtotal])
    out.push(eqCheck(
      '超额亏损小计',
      '合营小计 + 联营小计 = 合计',
      total,
      derivedExcess,
      REFS_EXCESS,
    ))
  } else {
    out.push({
      label: '超额亏损小计',
      rule: '合营小计 + 联营小计 = 合计',
      left: null,
      right: null,
      diff: null,
      level: 'skip',
      refs: REFS_EXCESS,
    })
  }

  return out
}
