/**
 * f1DisclosureConsistency — F1 预付款项披露内部勾稽引擎（纯函数，无 Vue 依赖）
 *
 * 规则**全部**取自 `backend/data/note_check_preset_formulas.json` 中
 * `note_section='五、7'` 的 F7-1~F7-14（listed / soe 各一份），不自造审计判断：
 *
 * | id     | 类型   | 口径 |
 * |--------|--------|------|
 * | F7-1   | 余额   | 报表.预付款项期末 = ①按账龄表.合计行.期末金额 |
 * | F7-2   | 余额   | 报表.预付款项期初 = ①按账龄表.合计行.期初金额 |
 * | F7-6   | 其中项 | ①各账龄段之和 = 小计行（期末/期初各独立） |
 * | F7-7   | 纵向   | ①合计行 = 小计行 − 减值准备行（期末/期初各独立） |
 * | F7-8   | 纵向   | ①比例 = 该行金额 ÷ 小计金额 × 100（小计应为 100；减值准备行与合计行不校验） |
 * | F7-3   | 其中项 | ②明细之和 = ②合计行 |
 * | F7-11  | 交叉   | ②合计 ≤ ①表 1 年以上各段期末之和（段集随账龄枚举自适配） |
 * | F7-9   | 完整性 | ②表期末余额 ≠ 0 的行关键列不得为空（上市仅债务人名称） |
 * | F7-4   | 其中项 | ③明细之和 = ③合计行（逐数值列） |
 * | F7-12  | 交叉   | ③合计账面余额 ≤ ①小计行期末金额 |
 * | F7-13  | 交叉   | ③合计减值准备 ≤ ①减值准备行期末（**仅国企**；上市③无该列 → 跳过） |
 * | F1-TB4 | 交叉   | 国企逐段减值准备合计 = 四表库「坏账准备-预付账款」期末（四表无数则跳过） |
 *
 * 缺数据一律 `skipped`（不是 `error`）—— 避免「未取数」被误读为「勾稽异常」。
 *
 * spec: .kiro/specs/f1-four-table-extraction-and-disclosure-alignment/ R8
 */
import { WP_CHECK_TOLERANCE } from './shared/disclosureConsistency'

export type F1CheckLevel = 'pass' | 'warning' | 'error' | 'skipped'

export interface F1CheckResult {
  /** 与校验预设 id 对齐（期末/期初拆分时加 `-end` / `-prior` 后缀） */
  id: string
  label: string
  /** 规则原文（界面 tooltip） */
  rule: string
  left: number | null
  right: number | null
  diff: number | null
  level: F1CheckLevel
  detail: string
  /** GtIndexChip 追溯值 */
  refs: string[]
}

/** 相等类容差：0.01 元。委托平台共用常量（`shared/disclosureConsistency.ts`）。 */
export const F1_AMOUNT_TOLERANCE = WP_CHECK_TOLERANCE
/** 比例类容差：0.01 个百分点 */
export const F1_PCT_TOLERANCE = 0.01

export interface F1AgingCheckRow {
  /** 账龄段 key（用于「1 年以上」段集判定） */
  key: string
  label: string
  endAmount: number
  endPct: number
  priorAmount: number
  priorPct: number
}

export interface F1Over1CheckRow {
  /** 上市 = 债务人名称；国企 = 债务单位 */
  name: string
  endBalance: number
  /** 国企专有（上市②表无该列） */
  creditorUnit?: string
  agingLabel?: string
  reason?: string
}

export interface F1Top5CheckRow {
  name: string
  endBalance: number
  proportionPct: number
  /** 国企专有（上市③表无减值准备列） */
  impairment?: number
}

export interface F1ConsistencyInput {
  /** 报表「预付款项」期末 / 期初（来自 render `project_context.prepaid_tb_amount`；0 = 未取数） */
  reportEndAmount?: number | null
  reportPriorAmount?: number | null
  /** ①按账龄表数据行（不含小计 / 减值准备 / 合计） */
  agingRows: F1AgingCheckRow[]
  agingSubtotal: { endAmount: number; endPct: number; priorAmount: number; priorPct: number }
  agingImpairment: { endAmount: number; priorAmount: number }
  agingNet: { endAmount: number; priorAmount: number }
  /** 「1 年以上」账龄段 key 集合（由 useF1AgingScope 的段定义派生，3/5/自定义自适配） */
  overOneYearKeys: string[]
  /** ②账龄超过 1 年的重要 / 大额预付款项 */
  over1Rows: F1Over1CheckRow[]
  over1Total: { endBalance: number }
  /** ③前五名 */
  top5Rows: F1Top5CheckRow[]
  top5Total: { endBalance: number; proportionPct: number; impairment?: number }
  /** 国企：四表库「坏账准备-预付账款」期末（null = 四表库无该科目 → F1-TB4 跳过） */
  fourTableImpairmentEnd?: number | null
  /** 上市③是否为「汇总披露格式」（此时无明细表 → F7-4 / F7-12 / F7-14 跳过） */
  top5SummaryOnly?: boolean
}

// ─── helpers ─────────────────────────────────────────────────────────────────

function n(v: number | null | undefined): number {
  const x = Number(v ?? 0)
  return Number.isFinite(x) ? x : 0
}

function round2(v: number): number {
  return Number(v.toFixed(2))
}

function eqCheck(
  id: string,
  label: string,
  rule: string,
  left: number | null,
  right: number | null,
  refs: string[],
  tolerance = F1_AMOUNT_TOLERANCE,
  skipDetail = '未取数',
): F1CheckResult {
  if (left === null || right === null) {
    return { id, label, rule, left, right, diff: null, level: 'skipped', detail: skipDetail, refs }
  }
  const diff = round2(left - right)
  const ok = Math.abs(diff) <= tolerance
  return {
    id,
    label,
    rule,
    left: round2(left),
    right: round2(right),
    diff,
    level: ok ? 'pass' : 'error',
    detail: ok ? '一致' : `差异 ${diff}`,
    refs,
  }
}

/** 子集类：left ≤ right（超出即异常） */
function subsetCheck(
  id: string,
  label: string,
  rule: string,
  left: number | null,
  right: number | null,
  refs: string[],
  skipDetail = '未取数',
): F1CheckResult {
  if (left === null || right === null) {
    return { id, label, rule, left, right, diff: null, level: 'skipped', detail: skipDetail, refs }
  }
  const diff = round2(left - right)
  const ok = diff <= F1_AMOUNT_TOLERANCE
  return {
    id,
    label,
    rule,
    left: round2(left),
    right: round2(right),
    diff,
    level: ok ? 'pass' : 'error',
    detail: ok ? '未超出' : `超出 ${diff}`,
    refs,
  }
}

const REF_AGING = ['wp:F1-1', 'wp:F1-2']
const REF_OVER1 = ['wp:F1-5']
const REF_TOP5 = ['wp:F1-2']

// ─── 引擎 ─────────────────────────────────────────────────────────────────────

export function buildF1ConsistencyChecks(
  variant: 'listed' | 'soe',
  input: F1ConsistencyInput,
): F1CheckResult[] {
  const out: F1CheckResult[] = []
  const noteRef = variant === 'listed' ? 'Note:五、7' : 'Note:八、7'
  const priorLabel = variant === 'listed' ? '上年年末' : '期初'
  const agingRefs = [...REF_AGING, noteRef]

  // ── F7-1 / F7-2：报表 ↔ ①合计行 ──────────────────────────────────────────
  const reportEnd = input.reportEndAmount == null || n(input.reportEndAmount) === 0
    ? null
    : n(input.reportEndAmount)
  const reportPrior = input.reportPriorAmount == null || n(input.reportPriorAmount) === 0
    ? null
    : n(input.reportPriorAmount)

  out.push(eqCheck(
    'F7-1',
    '报表「预付款项」期末 = ①合计行期末金额',
    "报表.预付款项期末 = ①按账龄表.合计行.期末金额",
    reportEnd,
    n(input.agingNet.endAmount),
    agingRefs,
    F1_AMOUNT_TOLERANCE,
    '报表数未取到（四表库未入库或科目映射缺失）',
  ))
  out.push(eqCheck(
    'F7-2',
    `报表「预付款项」${priorLabel} = ①合计行${priorLabel}金额`,
    '报表.预付款项期初 = ①按账龄表.合计行.期初金额',
    reportPrior,
    n(input.agingNet.priorAmount),
    agingRefs,
    F1_AMOUNT_TOLERANCE,
    '报表上期数未取到',
  ))

  // ── F7-6：各账龄段之和 = 小计（期末 / 期初各独立） ────────────────────────
  const sumEnd = input.agingRows.reduce((s, r) => s + n(r.endAmount), 0)
  const sumPrior = input.agingRows.reduce((s, r) => s + n(r.priorAmount), 0)
  out.push(eqCheck(
    'F7-6-end',
    '①各账龄段之和 = 小计行（期末）',
    '①按账龄表: sum(所有账龄段明细行) = 小计行（期末）',
    sumEnd,
    n(input.agingSubtotal.endAmount),
    agingRefs,
  ))
  out.push(eqCheck(
    'F7-6-prior',
    `①各账龄段之和 = 小计行（${priorLabel}）`,
    '①按账龄表: sum(所有账龄段明细行) = 小计行（期初）',
    sumPrior,
    n(input.agingSubtotal.priorAmount),
    agingRefs,
  ))

  // ── F7-7：合计行 = 小计 − 减值准备（期末 / 期初各独立） ───────────────────
  out.push(eqCheck(
    'F7-7-end',
    '①合计行 = 小计 − 减：减值准备（期末）',
    '①按账龄表: 合计行 = 小计行 - 减值准备行（期末）',
    n(input.agingNet.endAmount),
    n(input.agingSubtotal.endAmount) - n(input.agingImpairment.endAmount),
    agingRefs,
  ))
  out.push(eqCheck(
    'F7-7-prior',
    `①合计行 = 小计 − 减：减值准备（${priorLabel}）`,
    '①按账龄表: 合计行 = 小计行 - 减值准备行（期初）',
    n(input.agingNet.priorAmount),
    n(input.agingSubtotal.priorAmount) - n(input.agingImpairment.priorAmount),
    agingRefs,
  ))

  // ── F7-8：比例 = 该行金额 ÷ 小计金额 × 100（逐行；小计应为 100） ──────────
  const pctIssues: string[] = []
  for (const r of input.agingRows) {
    for (const [field, total, pct, periodLabel] of [
      ['end', n(input.agingSubtotal.endAmount), n(r.endPct), '期末'],
      ['prior', n(input.agingSubtotal.priorAmount), n(r.priorPct), priorLabel],
    ] as const) {
      if (total === 0) continue
      const amount = field === 'end' ? n(r.endAmount) : n(r.priorAmount)
      const want = (amount / total) * 100
      if (Math.abs(want - pct) > F1_PCT_TOLERANCE) {
        pctIssues.push(`${r.label}·${periodLabel}（应 ${round2(want)}%，实 ${round2(pct)}%）`)
      }
    }
  }
  const hasPctBase = n(input.agingSubtotal.endAmount) !== 0 || n(input.agingSubtotal.priorAmount) !== 0
  out.push({
    id: 'F7-8',
    label: '①比例% = 该行金额 ÷ 小计金额 × 100',
    rule: '①按账龄表: 比例(%) = 该行金额 / 小计行金额 × 100（小计行应为 100；减值准备行与合计行不参与）',
    left: null,
    right: null,
    diff: null,
    level: !hasPctBase ? 'skipped' : (pctIssues.length ? 'error' : 'pass'),
    detail: !hasPctBase
      ? '小计为 0，无比例基数'
      : (pctIssues.length ? `${pctIssues.length} 行比例不符：${pctIssues.join('；')}` : '逐行一致'),
    refs: agingRefs,
  })

  // ── F7-3：②明细之和 = ②合计行 ────────────────────────────────────────────
  const over1Sum = input.over1Rows.reduce((s, r) => s + n(r.endBalance), 0)
  out.push(eqCheck(
    'F7-3',
    '②明细行之和 = ②合计行（期末余额）',
    '②表: sum(合计行以外的所有明细行) = 合计行（期末余额列独立校验）',
    over1Sum,
    n(input.over1Total.endBalance),
    [...REF_OVER1, noteRef],
  ))

  // ── F7-11：②合计 ≤ ①表 1 年以上各段期末之和（段集随账龄枚举自适配） ──────
  const overKeys = new Set(input.overOneYearKeys)
  const over1Base = input.agingRows
    .filter((r) => overKeys.has(r.key))
    .reduce((s, r) => s + n(r.endAmount), 0)
  out.push(subsetCheck(
    'F7-11',
    '②合计 ≤ ①表 1 年以上各段期末之和',
    '②表.合计行.期末余额 ≤ ①按账龄表中1年以上各段期末金额之和（引擎自动适配 3/5 段）',
    n(input.over1Total.endBalance),
    over1Base,
    [...REF_OVER1, ...REF_AGING, noteRef],
    input.agingRows.length ? '未取数' : '①表无账龄段数据',
  ))

  // ── F7-9：②表完整性（上市仅债务人名称；国企四列） ─────────────────────────
  const incomplete: string[] = []
  for (const r of input.over1Rows) {
    if (n(r.endBalance) === 0) continue
    const missing: string[] = []
    if (!String(r.name || '').trim()) missing.push(variant === 'listed' ? '债务人名称' : '债务单位')
    if (variant === 'soe') {
      if (!String(r.creditorUnit || '').trim()) missing.push('债权单位')
      if (!String(r.agingLabel || '').trim()) missing.push('账龄')
      if (!String(r.reason || '').trim()) missing.push('未结算的原因')
    }
    if (missing.length) incomplete.push(`${r.name || '(未命名)'}：缺 ${missing.join('/')}`)
  }
  const over1WithAmount = input.over1Rows.filter((r) => n(r.endBalance) !== 0)
  out.push({
    id: 'F7-9',
    label: variant === 'listed' ? '②表债务人名称完整性' : '②表关键列完整性',
    rule: variant === 'listed'
      ? '②表（排除合计行）: 若账面余额 ≠ 0，则债务人名称列不应为空'
      : '②表（排除合计行）: 若期末余额 ≠ 0，则债权单位、债务单位、账龄、未结算的原因列均不应为空',
    left: null,
    right: null,
    diff: null,
    level: !over1WithAmount.length ? 'skipped' : (incomplete.length ? 'warning' : 'pass'),
    detail: !over1WithAmount.length
      ? '②表无非零金额行'
      : (incomplete.length ? `${incomplete.length} 行不完整：${incomplete.join('；')}` : '逐行完整'),
    refs: [...REF_OVER1, noteRef],
  })

  // ── ③前五名（上市「汇总披露格式」下无明细表 → 相关规则跳过） ───────────────
  const top5Skip = variant === 'listed' && input.top5SummaryOnly === true
  const top5SkipDetail = '当前为「汇总披露格式」，③明细表不列示'

  const top5Sum = input.top5Rows.reduce((s, r) => s + n(r.endBalance), 0)
  out.push(
    top5Skip
      ? {
        id: 'F7-4',
        label: '③明细行之和 = ③合计行',
        rule: '③表: sum(合计行以外的所有明细行) = 合计行（每个数值列独立校验）',
        left: null, right: null, diff: null, level: 'skipped',
        detail: top5SkipDetail, refs: [...REF_TOP5, noteRef],
      }
      : eqCheck(
        'F7-4',
        '③明细行之和 = ③合计行（账面余额）',
        '③表: sum(合计行以外的所有明细行) = 合计行（每个数值列独立校验）',
        top5Sum,
        n(input.top5Total.endBalance),
        [...REF_TOP5, noteRef],
      ),
  )

  out.push(
    top5Skip
      ? {
        id: 'F7-12',
        label: '③合计账面余额 ≤ ①小计行期末金额',
        rule: '③前五名表.合计行.账面余额 ≤ ①按账龄表.小计行.期末金额',
        left: null, right: null, diff: null, level: 'skipped',
        detail: top5SkipDetail, refs: [...REF_TOP5, ...REF_AGING, noteRef],
      }
      : subsetCheck(
        'F7-12',
        '③合计账面余额 ≤ ①小计行期末金额',
        '③前五名表.合计行.账面余额 ≤ ①按账龄表.小计行.期末金额（前五名不超过全部小计）',
        n(input.top5Total.endBalance),
        n(input.agingSubtotal.endAmount) === 0 ? null : n(input.agingSubtotal.endAmount),
        [...REF_TOP5, ...REF_AGING, noteRef],
      ),
  )

  // F7-13：上市③表**无**减值准备列（预设明确「此校验不适用，跳过」）
  out.push(
    variant === 'listed'
      ? {
        id: 'F7-13',
        label: '③合计减值准备 ≤ ①减值准备行期末',
        rule: '③前五名表.合计行.减值准备 ≤ ①按账龄表.减值准备行.期末金额',
        left: null, right: null, diff: null, level: 'skipped',
        detail: '上市版③表无「减值准备」列，本校验不适用（F7-13 listed）',
        refs: [...REF_TOP5, ...REF_AGING, noteRef],
      }
      : subsetCheck(
        'F7-13',
        '③合计减值准备 ≤ ①减值准备行期末',
        '③前五名表.合计行.减值准备 ≤ ①按账龄表.减值准备行.期末金额',
        n(input.top5Total.impairment),
        n(input.agingImpairment.endAmount) === 0 ? null : n(input.agingImpairment.endAmount),
        [...REF_TOP5, ...REF_AGING, noteRef],
        '①减值准备行期末为 0，无可比基数',
      ),
  )

  // F7-14：③占比 = 该行账面余额 ÷ ①小计行期末 × 100
  const top5Base = n(input.agingSubtotal.endAmount)
  const top5PctIssues: string[] = []
  if (!top5Skip && top5Base !== 0) {
    for (const r of input.top5Rows) {
      const want = (n(r.endBalance) / top5Base) * 100
      if (Math.abs(want - n(r.proportionPct)) > F1_PCT_TOLERANCE) {
        top5PctIssues.push(`${r.name || '(未命名)'}（应 ${round2(want)}%，实 ${round2(n(r.proportionPct))}%）`)
      }
    }
  }
  out.push({
    id: 'F7-14',
    label: '③占比 = 该行账面余额 ÷ ①小计行期末 × 100',
    rule: '③前五名表: 占预付款项合计的比例(%) = 该行账面余额 / ①按账龄表.小计行.期末金额 × 100',
    left: null,
    right: null,
    diff: null,
    level: top5Skip ? 'skipped' : (top5Base === 0 ? 'skipped' : (top5PctIssues.length ? 'error' : 'pass')),
    detail: top5Skip
      ? top5SkipDetail
      : (top5Base === 0
        ? '①小计行期末为 0，无比例基数'
        : (top5PctIssues.length ? `${top5PctIssues.length} 行占比不符：${top5PctIssues.join('；')}` : '逐行一致')),
    refs: [...REF_TOP5, ...REF_AGING, noteRef],
  })

  // ── F7-5 账龄衔接（合理性）：本期某段期末 ≤ 上期「前一段」期初 ─────────────
  //   金额只会随时间向后滚动（1年以内 → 1至2年 → …），故本期第 i 段期末不应超过
  //   上期第 i-1 段期初；超出即提示（可能是账龄划分有误或新增挂账被错分到长龄段）。
  const agingRollIssues: string[] = []
  for (let i = 1; i < input.agingRows.length; i += 1) {
    const cur = input.agingRows[i]
    const prevSegPrior = n(input.agingRows[i - 1].priorAmount)
    if (n(cur.endAmount) - prevSegPrior > F1_AMOUNT_TOLERANCE) {
      agingRollIssues.push(
        `${cur.label} 期末 ${round2(n(cur.endAmount))} > ${input.agingRows[i - 1].label} ${priorLabel} ${round2(prevSegPrior)}`,
      )
    }
  }
  out.push({
    id: 'F7-5',
    label: '①账龄衔接（本期各段期末 ≤ 上期前一段）',
    rule: '①按账龄表: 账龄衔接校验（使用「金额」列，按通用规则逐段比较期末 vs 期初前一账龄段，合理性校验；引擎自动适配 3 段或 5 段）',
    left: null,
    right: null,
    diff: null,
    level: input.agingRows.length < 2
      ? 'skipped'
      : (agingRollIssues.length ? 'warning' : 'pass'),
    detail: input.agingRows.length < 2
      ? '账龄段少于 2 档，无衔接关系'
      : (agingRollIssues.length
        ? `${agingRollIssues.length} 处衔接异常：${agingRollIssues.join('；')}`
        : '逐段衔接合理'),
    refs: agingRefs,
  })

  // ── F7-10 LLM 审核：需模型判断表述是否规范，不在纯函数勾稽内评估 ─────────────
  out.push({
    id: 'F7-10',
    label: variant === 'listed'
      ? '②表 LLM 审核（上市不适用）'
      : '②表名称 / 账龄 / 原因表述 LLM 审核',
    rule: variant === 'listed'
      ? '上市版②表无「账龄」和「未结算的原因」列，此校验不适用，跳过'
      : '②表（排除合计行，仅期末余额 ≠ 0 且对应列非空的行）: 债权单位 / 债务单位 / 账龄 / 未结算的原因 表述规范性由 LLM 判断',
    left: null,
    right: null,
    diff: null,
    level: 'skipped',
    detail: variant === 'listed'
      ? '上市版②表无「账龄」「未结算的原因」列，本校验不适用（F7-10 listed）'
      : '需模型判断表述规范性 —— 请用文本域旁的「🤖 AI 辅助」生成/复核说明',
    refs: [...REF_OVER1, noteRef],
  })

  // ── F1-TB4（国企附加）：逐段减值准备合计 = 四表库「坏账准备-预付账款」期末 ──
  if (variant === 'soe') {
    const fourTable = input.fourTableImpairmentEnd
    out.push(eqCheck(
      'F1-TB4',
      '逐段减值准备合计 = 四表库「坏账准备-预付账款」期末',
      '①按账龄表.减值准备行.期末金额 = tb_balance「坏账准备-预付账款」(1231-04) 期末余额',
      n(input.agingImpairment.endAmount),
      fourTable == null ? null : n(fourTable),
      [...REF_AGING, noteRef],
      F1_AMOUNT_TOLERANCE,
      '四表库无「坏账准备-预付账款」科目（未计提或未映射）',
    ))
  }

  return out
}

/** 汇总统计（供紧凑单行 bar 展示） */
export function summarizeF1Checks(results: F1CheckResult[]): {
  pass: number
  warning: number
  error: number
  skipped: number
  total: number
} {
  const acc = { pass: 0, warning: 0, error: 0, skipped: 0, total: results.length }
  for (const r of results) acc[r.level] += 1
  return acc
}
