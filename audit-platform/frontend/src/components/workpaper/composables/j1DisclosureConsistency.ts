/**
 * j1DisclosureConsistency — J1 应付职工薪酬披露表内部勾稽校验（纯函数，上市 / 国企双变体）
 *
 * 规则**只取源模板可判定的关系**（逐格读 `backend/wp_templates/J/J1 应付职工薪酬.xlsx`
 * 得到的 Excel 公式），不自造审计判断：
 *
 * | 规则 | 源模板证据 |
 * |---|---|
 * | 表1「短期薪酬」= 表2 合计 | 两者同引 `'明细表J1-2 '!J33`（上市 B7 / 国企 B9） |
 * | 表1「离职后福利-设定提存计划」= 表3 合计 | 两者同引 `'明细表J1-2 '!J46` |
 * | 表2「社会保险费」= Σ 其中项 | 上市 `B20=SUM(B21:B27)`；国企 `B19=SUM(B20:B23)` |
 * | 表3「离职后福利」= Σ 其中项 | 上市 `B41=SUM(B42:B45)`；国企 `B32=SUM(B33:B36)` |
 * | 逐行 期末 = 期初 + 增加 − 减少 | 国企 E 列全部显式 `=B+C-D` |
 * | 表1 合计期末 = J1-1 期末审定合计 | 审定表→披露表勾稽（跨底稿） |
 *
 * 🔴 **裁决 4（见 spec design）**：源模板里三张表**都独立引 J1-2 明细表**，
 * 表1 与表2/表3 之间是"应当相等的**勾稽**关系"，不是"表1 由表2 派生" →
 * 差异在此报出，而**不静默覆盖**用户在表1 的录入。
 *
 * 容差 1 分（0.01 元）。金额勾稽无"警告"中间态：超容差即 `error`。
 *
 * spec: .kiro/specs/j1-disclosure-template-alignment/ Task 3.1
 */
import {
  buildDisclosureSubtotal,
  type J1DisclosureRow,
} from '@/composables/workpaper/j1/j1DisclosureRowModel'
import { categoryForSummaryLabel } from '@/composables/workpaper/j1/useJ1DisclosureSections'

/** 金额容差：1 分 */
export const J1_AMOUNT_TOLERANCE = 0.01

export type J1CheckLevel = 'ok' | 'error'

export interface J1CheckResult {
  id: string
  /** 校验项名（UI 首列） */
  label: string
  /** 勾稽规则文字（tooltip），供审计追溯 */
  rule: string
  level: J1CheckLevel
  left: number
  right: number
  /** left − right */
  diff: number
  detail: string
  /** 相关索引（GtIndexChip 值），供跳转追溯 */
  refs: string[]
}

export interface J1ConsistencySummary {
  checks: J1CheckResult[]
  errorCount: number
  okCount: number
  allPass: boolean
}

export type J1ConsistencyVariant = 'listed' | 'soe'

type AmountKey = 'beginBalance' | 'increase' | 'decrease' | 'endBalance'

/** 四个金额列的列头（源模板上市 / 国企各自口径） */
const COLUMN_LABELS: Record<J1ConsistencyVariant, Record<AmountKey, string>> = {
  listed: {
    beginBalance: '上年年末数',
    increase: '本期增加',
    decrease: '本期减少',
    endBalance: '期末数',
  },
  soe: {
    beginBalance: '期初余额',
    increase: '本期增加',
    decrease: '本期减少',
    endBalance: '期末余额',
  },
}

const AMOUNT_KEYS: AmountKey[] = ['beginBalance', 'increase', 'decrease', 'endBalance']

function round2(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? Math.round(n * 100) / 100 : 0
}

function eqCheck(args: {
  id: string
  label: string
  rule: string
  left: number
  right: number
  refs?: string[]
  leftName?: string
  rightName?: string
}): J1CheckResult {
  const left = round2(args.left)
  const right = round2(args.right)
  const diff = round2(left - right)
  const pass = Math.abs(diff) <= J1_AMOUNT_TOLERANCE
  const ln = args.leftName ?? '本表'
  const rn = args.rightName ?? '勾稽值'
  return {
    id: args.id,
    label: args.label,
    rule: args.rule,
    left,
    right,
    diff,
    level: pass ? 'ok' : 'error',
    detail: pass
      ? '一致'
      : `${ln} ${left.toFixed(2)} 与${rn} ${right.toFixed(2)} 相差 ${diff.toFixed(2)}`,
    refs: args.refs ?? [],
  }
}

/** 汇总表里按分类定位行（复用既有 `categoryForSummaryLabel`，不重写关键词表） */
function findSummaryRow(
  rows: readonly J1DisclosureRow[],
  category: 'short_term' | 'post_employment',
): J1DisclosureRow | undefined {
  return rows.find((r) => !r.isSubtotal && categoryForSummaryLabel(r.label) === category)
}

/** 父行 → 其紧邻缩进子行（与 `j1DisclosureRowModel.parentChildSpans` 同口径） */
function firstParentWithChildren(
  rows: readonly J1DisclosureRow[],
): { parent: J1DisclosureRow; children: J1DisclosureRow[] } | null {
  for (let i = 0; i < rows.length; i += 1) {
    const parent = rows[i]
    if (parent.isSubtotal || parent.indent) continue
    const children: J1DisclosureRow[] = []
    for (let j = i + 1; j < rows.length; j += 1) {
      const next = rows[j]
      if (next.isSubtotal || !next.indent) break
      children.push(next)
    }
    if (children.length > 0) return { parent, children }
  }
  return null
}

export interface J1ConsistencyInput {
  variant: J1ConsistencyVariant
  /** 表1 汇总表数据行（不含合计行） */
  summary: readonly J1DisclosureRow[]
  /** 表2 短期薪酬数据行 */
  shortTerm: readonly J1DisclosureRow[]
  /** 表3 设定提存计划数据行 */
  postEmployment: readonly J1DisclosureRow[]
  /** J1-1 期末审定合计（跨底稿键 `J1-1-audited-total`）；0 表示审定表未编制 */
  adjudicationEndTotal?: number
}

/**
 * 生成全部勾稽结论。
 *
 * 顺序固定（UI 折叠明细按此展示）：跨表两组 × 4 列 → 父子两组 → 逐行期末公式 → 审定表勾稽。
 */
export function buildJ1ConsistencyChecks(input: J1ConsistencyInput): J1CheckResult[] {
  const { variant, summary, shortTerm, postEmployment } = input
  const cols = COLUMN_LABELS[variant]
  const checks: J1CheckResult[] = []

  const shortTermTotal = buildDisclosureSubtotal('c-st', '合计', 'short_term', [...shortTerm])
  const postTotal = buildDisclosureSubtotal('c-pe', '合计', 'post_employment', [...postEmployment])

  // ── 跨表勾稽（源模板三张表同引 J1-2，故应相等） ─────────────────────────
  const crossRules: Array<{
    key: 'short_term' | 'post_employment'
    tableName: string
    total: J1DisclosureRow
    evidence: string
  }> = [
    {
      key: 'short_term',
      tableName: variant === 'soe' ? '短期薪酬列示' : '短期薪酬',
      total: shortTermTotal,
      evidence: `源模板两处同引「明细表J1-2 」!J33（${variant === 'soe' ? '国企 B9' : '上市 B7'}）`,
    },
    {
      key: 'post_employment',
      tableName: variant === 'soe' ? '设定提存计划列示' : '设定提存计划',
      total: postTotal,
      evidence: `源模板两处同引「明细表J1-2 」!J46（${variant === 'soe' ? '国企 B10' : '上市 B8'}）`,
    },
  ]

  for (const r of crossRules) {
    const row = findSummaryRow(summary, r.key)
    if (!row) continue
    for (const key of AMOUNT_KEYS) {
      checks.push(
        eqCheck({
          id: `cross-${r.key}-${key}`,
          label: `汇总表「${row.label}」↔「${r.tableName}」合计（${cols[key]}）`,
          rule: `汇总表该行 = ${r.tableName}表合计行。${r.evidence}`,
          left: row[key],
          right: r.total[key],
          leftName: '汇总表',
          rightName: `${r.tableName}表合计`,
          refs: ['wp:J1-2'],
        }),
      )
    }
  }

  // ── 同表父子勾稽（源模板父行是 SUM 公式） ───────────────────────────────
  const parentRules: Array<{
    id: string
    rows: readonly J1DisclosureRow[]
    evidence: string
  }> = [
    {
      id: 'parent-short-term',
      rows: shortTerm,
      evidence: variant === 'soe' ? '源模板国企 B19=SUM(B20:B23)' : '源模板上市 B20=SUM(B21:B27)',
    },
    {
      id: 'parent-post-employment',
      rows: postEmployment,
      evidence: variant === 'soe' ? '源模板国企 B32=SUM(B33:B36)' : '源模板上市 B41=SUM(B42:B45)',
    },
  ]

  for (const r of parentRules) {
    const hit = firstParentWithChildren(r.rows)
    if (!hit) continue
    const childSum = hit.children.reduce((s, c) => s + (c.endBalance || 0), 0)
    checks.push(
      eqCheck({
        id: r.id,
        label: `「${hit.parent.label}」= Σ 其下「其中：」子项（${cols.endBalance}）`,
        rule: `父行为派生量，等于其下各「其中：」子项之和。${r.evidence}`,
        left: hit.parent.endBalance,
        right: childSum,
        leftName: '父行',
        rightName: '子项之和',
      }),
    )
  }

  // ── 逐行期末公式（源模板国企 E 列显式 =B+C-D） ──────────────────────────
  const allRows: Array<{ table: string; row: J1DisclosureRow }> = [
    ...summary.map((row) => ({ table: '汇总表', row })),
    ...shortTerm.map((row) => ({ table: '短期薪酬', row })),
    ...postEmployment.map((row) => ({ table: '设定提存计划', row })),
  ]
  const offender = allRows.find(({ row }) => {
    if (row.isSubtotal) return false
    const want = round2((row.beginBalance || 0) + (row.increase || 0) - (row.decrease || 0))
    return Math.abs(round2(row.endBalance) - want) > J1_AMOUNT_TOLERANCE
  })
  checks.push(
    eqCheck({
      id: 'end-formula',
      label: offender
        ? `逐行期末公式（${offender.table}「${offender.row.label}」）`
        : '逐行期末公式',
      rule: `每行 ${cols.endBalance} = ${cols.beginBalance} + ${cols.increase} − ${cols.decrease}（负债贷方口径；源模板国企 E 列显式 =B+C-D）`,
      left: offender ? round2(offender.row.endBalance) : 0,
      right: offender
        ? round2(
            (offender.row.beginBalance || 0) +
              (offender.row.increase || 0) -
              (offender.row.decrease || 0),
          )
        : 0,
      leftName: '期末列',
      rightName: '公式值',
    }),
  )

  // ── 审定表勾稽（仅在 J1-1 已编制时有意义） ──────────────────────────────
  const adjTotal = round2(input.adjudicationEndTotal ?? 0)
  if (adjTotal !== 0) {
    const summaryTotal = buildDisclosureSubtotal('c-sum', '合计', 'summary', [...summary])
    checks.push(
      eqCheck({
        id: 'vs-adjudication',
        label: `汇总表合计（${cols.endBalance}）↔ J1-1 期末审定合计`,
        rule: '披露汇总表合计行期末 = 审定表 J1-1 期末审定合计 = 资产负债表「应付职工薪酬」期末数',
        left: summaryTotal.endBalance,
        right: adjTotal,
        leftName: '披露合计',
        rightName: 'J1-1 审定',
        refs: ['wp:J1-1'],
      }),
    )
  }

  return checks
}

/** 汇总统计（供紧凑单行 bar 展示） */
export function summarizeJ1Consistency(checks: readonly J1CheckResult[]): J1ConsistencySummary {
  const list = [...checks]
  const errorCount = list.filter((c) => c.level === 'error').length
  return {
    checks: list,
    errorCount,
    okCount: list.length - errorCount,
    allPass: errorCount === 0,
  }
}

/** 一步到位：入参 → 汇总结论 */
export function buildJ1Consistency(input: J1ConsistencyInput): J1ConsistencySummary {
  return summarizeJ1Consistency(buildJ1ConsistencyChecks(input))
}
