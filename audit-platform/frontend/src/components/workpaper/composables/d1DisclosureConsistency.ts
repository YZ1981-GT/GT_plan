/**
 * D1 应收票据披露表内部勾稽校验（纯函数，上市 / 国企双变体）
 *
 * 规则真源 = `note_check_preset_formulas.json` 的 `F4-*`（应收票据校验预设，
 * 平台最全的循环之一，共 30 条）。本引擎只实现**可判定**的勾稽，不猜业务意图：
 *
 * | 预设 | 勾稽 |
 * |---|---|
 * | `F4-3`  | ①主表各票据种类行之和 = 合计行（期末 / 期初 三列各自） |
 * | `F4-3a` | ①主表：账面余额 − 坏账准备 = 账面价值（期末 / 期初） |
 * | `F4-8/9/10` | ①主表合计 = ②分类表合计（账面余额 / 坏账准备 / 账面价值） |
 * | `F4-11` | ②分类表：账面余额 − 坏账准备 = 账面价值 |
 * | `F4-12` | ②分类表：预期信用损失率 = 坏账准备 ÷ 账面余额 |
 * | `F4-25` | ②分类表：合计行比例 = 100% |
 * | `F4-4/5` | ②分类表单项行 = ③单项明细小计；组合行 = ④组合明细小计 |
 * | `F4-6`  | ①主表坏账准备期末合计 = ⑤变动表期末合计 |
 * | `F4-7`  | ⑤变动表逐行：期初 + 计提 − 收回或转回 − 核销 − 其他变动 = 期末 |
 * | `F4-19` | ⑤变动表：单项行 + 组合行 = 合计行 |
 * | `F4-20` | ⑤变动表：「其中：」下明细行之和 = 按组合计提行 |
 * | `F4-21/22/23` | ⑥质押 / ⑦背书贴现 / ⑧转应收账款：明细行之和 = 合计行 |
 * | `F4-24` | ⑨核销：逐项明细之和 = 核销总额；核销总额 = ⑤变动表「本期核销」 |
 *
 * 设计约定（同 H1 范式）：
 * - 相等类容差 0.01 元（分）；差异非零报 `error`
 * - 任一侧**完全无数据**（两侧都为 0）→ `skip`，不刷屏
 * - 不做不等式外推、不做「应该有数据」的完整性判断（那属 `F4-14/27/29`，需 LLM/人工）
 *
 * spec: .kiro/specs/d1-notes-receivable-disclosure-alignment/ R10
 */

/** 金额容差：1 分 */
export const D1_AMOUNT_TOLERANCE = 0.01
/** 比率容差：0.01 个百分点（内部存分数 → 1e-4） */
export const D1_RATE_TOLERANCE = 0.0001

export type D1CheckLevel = 'ok' | 'warn' | 'error' | 'skip'

export interface D1ConsistencyCheck {
  id: string
  /** 校验项名（UI 首列） */
  label: string
  /** 勾稽规则文字（含预设编号），供审计追溯 */
  rule: string
  level: D1CheckLevel
  left: number
  right: number
  /** left − right */
  diff: number
  detail: string
  /** 相关索引（GtIndexChip / 附注章节），供跳转追溯 */
  refs: string[]
}

export interface D1ConsistencySummary {
  checks: D1ConsistencyCheck[]
  errorCount: number
  warnCount: number
  okCount: number
  skipCount: number
  allPass: boolean
}

// ─── 入参形状（与 buildD1SyncPayload 的 snapshot 同源，保证面板与附注一致）──────

export interface D1CheckSummaryRow {
  category: string
  endBalance: number; endProvision: number; endBookValue: number
  priorBalance: number; priorProvision: number; priorBookValue: number
}
export interface D1CheckClassRow {
  label: string
  balance: number; ratio: number; provision: number; lossRate: number; bookValue: number
}
export interface D1CheckAmountRow { balance: number; provision: number }
export interface D1CheckMovementRow {
  label?: string
  priorBalance: number; provision: number; reversal: number
  writeOff: number; transfer: number; other: number; endBalance: number
}
export interface D1CheckSimpleRow { amount: number }

export interface D1ConsistencyInput {
  variant: 'listed' | 'soe'
  /** ①主表明细行 + 合计 */
  summaryRows: readonly D1CheckSummaryRow[]
  summaryTotal: D1CheckSummaryRow
  /** ②分类表（展开行，含 合计）—— 期末 / 期初 */
  classEndRows: readonly D1CheckClassRow[]
  classPriorRows: readonly D1CheckClassRow[]
  classEndTotal: D1CheckClassRow
  classPriorTotal: D1CheckClassRow
  /** ③单项计提明细（期末） */
  individualEndRows: readonly D1CheckAmountRow[]
  /** ④组合计提明细（期末，两个票据种类合并后） */
  portfolioEndRows: readonly D1CheckAmountRow[]
  /** ②分类表里「按单项计提」/「按组合计提」两行（期末） */
  classEndIndividual: D1CheckAmountRow
  classEndPortfolio: D1CheckAmountRow
  /** ⑤变动表行（国企多行；上市为单行合计口径） */
  movementRows: readonly D1CheckMovementRow[]
  /** ⑤变动表「其中：」下明细行（仅国企） */
  movementDetailRows: readonly D1CheckMovementRow[]
  /** ⑤变动表「按组合计提」行（仅国企，用于 F4-20） */
  movementPortfolio?: D1CheckMovementRow
  /** ⑤变动表期末合计 */
  movementEndTotal: number
  /** ⑤变动表本期核销合计 */
  movementWriteOffTotal: number
  /** ⑥质押：明细行金额 + 合计 */
  pledgedRows: readonly D1CheckSimpleRow[]
  pledgedTotal: number
  /** ⑦背书贴现：终止确认 / 未终止确认 */
  endorsedRows: readonly { derecognized: number; notDerecognized: number }[]
  endorsedTotal: { derecognized: number; notDerecognized: number }
  /** ⑧转应收账款 */
  transferRows: readonly D1CheckSimpleRow[]
  transferTotal: number
  /** ⑨核销总额 + 逐项明细 */
  writeOffAmount: number
  writeOffDetailRows: readonly D1CheckSimpleRow[]
}

// ─── 内部工具 ────────────────────────────────────────────────────────────────

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}
function round2(v: number): number {
  return Math.round(num(v) * 100) / 100
}
function sum<T>(rows: readonly T[], pick: (r: T) => number): number {
  return rows.reduce((s, r) => s + num(pick(r)), 0)
}

/**
 * 相等类勾稽。两侧都为 0 → `skip`（无数据不刷屏）；|left − right| ≤ tol → `ok`。
 */
function eqCheck(
  id: string,
  label: string,
  rule: string,
  left: number,
  right: number,
  refs: string[],
  opts?: { leftName?: string; rightName?: string; tol?: number; level?: 'warn' | 'error' },
): D1ConsistencyCheck {
  const l = round2(left)
  const r = round2(right)
  const diff = round2(l - r)
  const tol = opts?.tol ?? D1_AMOUNT_TOLERANCE
  const ln = opts?.leftName ?? '本表'
  const rn = opts?.rightName ?? '勾稽对象'
  if (l === 0 && r === 0) {
    return { id, label, rule, level: 'skip', left: l, right: r, diff: 0, detail: '两侧均无数据，跳过', refs }
  }
  if (Math.abs(diff) <= tol) {
    return { id, label, rule, level: 'ok', left: l, right: r, diff, detail: '一致', refs }
  }
  return {
    id, label, rule, level: opts?.level ?? 'error', left: l, right: r, diff,
    detail: `${ln} ${l} 与 ${rn} ${r} 不一致，差异 ${diff}`,
    refs,
  }
}

const REF_MAIN = 'D1-1'
const REF_BAD_DEBT = 'D1-4'
const REF_PLEDGE = 'D1-12'
const REF_ENDORSE = 'D1-8'
const REF_WRITEOFF = 'D1-16'

// ─── 主入口 ──────────────────────────────────────────────────────────────────

/**
 * 跑一遍 D1 披露表内部勾稽。纯函数：同输入同输出、无 IO。
 *
 * 上市 / 国企的差异只在「哪些表存在」，规则口径完全一致（预设两份内容相同）。
 */
export function runD1DisclosureChecks(input: D1ConsistencyInput): D1ConsistencySummary {
  const checks: D1ConsistencyCheck[] = []
  const isSoe = input.variant === 'soe'

  // ── ① 主表：明细和 = 合计（F4-3）× 6 列 ────────────────────────────────
  const summaryCols: Array<[keyof D1CheckSummaryRow, string]> = [
    ['endBalance', '期末账面余额'],
    ['endProvision', '期末坏账准备'],
    ['endBookValue', '期末账面价值'],
    ['priorBalance', isSoe ? '期初账面余额' : '上年末账面余额'],
    ['priorProvision', isSoe ? '期初坏账准备' : '上年末坏账准备'],
    ['priorBookValue', isSoe ? '期初账面价值' : '上年末账面价值'],
  ]
  for (const [field, name] of summaryCols) {
    checks.push(eqCheck(
      `F4-3:${String(field)}`,
      `①分类总表 ${name}`,
      'F4-3 各票据种类行之和 = 合计行（每个数值列独立校验）',
      sum(input.summaryRows, r => num(r[field] as number)),
      num(input.summaryTotal[field] as number),
      [REF_MAIN],
      { leftName: '明细行之和', rightName: '合计行' },
    ))
  }

  // ── ① 主表：账面余额 − 坏账准备 = 账面价值（F4-3a）× 2 期 ────────────────
  for (const [period, bal, prov, bv] of [
    ['期末', 'endBalance', 'endProvision', 'endBookValue'],
    [isSoe ? '期初' : '上年末', 'priorBalance', 'priorProvision', 'priorBookValue'],
  ] as const) {
    checks.push(eqCheck(
      `F4-3a:${bv}`,
      `①分类总表 ${period}账面价值`,
      'F4-3a 账面余额 − 坏账准备 = 账面价值',
      num(input.summaryTotal[bal]) - num(input.summaryTotal[prov]),
      num(input.summaryTotal[bv]),
      [REF_MAIN],
      { leftName: '账面余额−坏账准备', rightName: '账面价值' },
    ))
  }

  // ── ①合计 = ②分类表合计（F4-8 / F4-9 / F4-10）────────────────────────────
  const crossCols: Array<[keyof D1CheckSummaryRow, keyof D1CheckClassRow, string, string]> = [
    ['endBalance', 'balance', '账面余额', 'F4-8'],
    ['endProvision', 'provision', '坏账准备', 'F4-9'],
    ['endBookValue', 'bookValue', '账面价值', 'F4-10'],
  ]
  for (const [sField, cField, name, preset] of crossCols) {
    checks.push(eqCheck(
      `${preset}:end`,
      `①合计 ↔ ②分类表 期末${name}`,
      `${preset} ①分类表.${name}期末合计 = ②按计提方法分类表.${name}期末合计`,
      num(input.summaryTotal[sField] as number),
      num(input.classEndTotal[cField] as number),
      [REF_MAIN, REF_BAD_DEBT],
      { leftName: '①合计', rightName: '②合计' },
    ))
  }

  // ── ② 分类表纵向（F4-11 / F4-12 / F4-25）逐行 ────────────────────────────
  const classSets: Array<[string, readonly D1CheckClassRow[], D1CheckClassRow]> = [
    ['期末', input.classEndRows, input.classEndTotal],
    [isSoe ? '期初' : '上年末', input.classPriorRows, input.classPriorTotal],
  ]
  for (const [period, rows, total] of classSets) {
    rows.forEach((r, i) => {
      const label = String(r.label || `第 ${i + 1} 行`).trim()
      if (!label || label === '其中：') return
      checks.push(eqCheck(
        `F4-11:${period}:${i}`,
        `②分类表（${period}）${label} 账面价值`,
        'F4-11 账面余额 − 坏账准备 = 账面价值',
        num(r.balance) - num(r.provision),
        num(r.bookValue),
        [REF_BAD_DEBT],
        { leftName: '账面余额−坏账准备', rightName: '账面价值' },
      ))
      checks.push(eqCheck(
        `F4-12:${period}:${i}`,
        `②分类表（${period}）${label} 预期信用损失率`,
        'F4-12 预期信用损失率 = 坏账准备 ÷ 账面余额',
        num(r.balance) ? num(r.provision) / num(r.balance) : 0,
        num(r.lossRate),
        [REF_BAD_DEBT],
        { leftName: '坏账准备÷账面余额', rightName: '损失率列', tol: D1_RATE_TOLERANCE },
      ))
    })
    checks.push(eqCheck(
      `F4-25:${period}`,
      `②分类表（${period}）合计行比例`,
      'F4-25 比例(%) = 该行账面余额 ÷ 合计行账面余额 × 100；合计行应为 100',
      num(total.balance) ? 1 : 0,
      num(total.ratio),
      [REF_BAD_DEBT],
      { leftName: '应为 100%', rightName: '合计行比例', tol: D1_RATE_TOLERANCE },
    ))
  }

  // ── ② 单项 / 组合行 = ③ / ④ 明细小计（F4-4 / F4-5）──────────────────────
  checks.push(eqCheck(
    'F4-4:individual',
    '②单项计提行 ↔ ③单项明细小计（账面余额）',
    'F4-4 ②按计提方法分类表.账面余额（按单项计提行）= ③单项计提表小计（期末）',
    num(input.classEndIndividual.balance),
    sum(input.individualEndRows, r => r.balance),
    [REF_BAD_DEBT],
    { leftName: '②单项行', rightName: '③小计' },
  ))
  checks.push(eqCheck(
    'F4-5:individual',
    '②单项计提行 ↔ ③单项明细小计（坏账准备）',
    'F4-5 ②按计提方法分类表.坏账准备（按单项计提行）= ③单项计提表小计（期末）',
    num(input.classEndIndividual.provision),
    sum(input.individualEndRows, r => r.provision),
    [REF_BAD_DEBT],
    { leftName: '②单项行', rightName: '③小计' },
  ))
  checks.push(eqCheck(
    'F4-4:portfolio',
    '②组合计提行 ↔ ④组合明细小计（账面余额）',
    'F4-4 ②按计提方法分类表.账面余额（按组合计提行）= ④组合计提表小计（期末）',
    num(input.classEndPortfolio.balance),
    sum(input.portfolioEndRows, r => r.balance),
    [REF_BAD_DEBT],
    { leftName: '②组合行', rightName: '④小计' },
  ))
  checks.push(eqCheck(
    'F4-5:portfolio',
    '②组合计提行 ↔ ④组合明细小计（坏账准备）',
    'F4-5 ②按计提方法分类表.坏账准备（按组合计提行）= ④组合计提表小计（期末）',
    num(input.classEndPortfolio.provision),
    sum(input.portfolioEndRows, r => r.provision),
    [REF_BAD_DEBT],
    { leftName: '②组合行', rightName: '④小计' },
  ))

  // ── ①坏账准备期末合计 = ⑤变动表期末合计（F4-6）──────────────────────────
  checks.push(eqCheck(
    'F4-6',
    '①坏账准备期末 ↔ ⑤变动表期末',
    'F4-6 ①分类表.坏账准备期末合计 = ⑤坏账准备变动表.期末余额合计',
    num(input.summaryTotal.endProvision),
    num(input.movementEndTotal),
    [REF_MAIN, REF_BAD_DEBT],
    { leftName: '①坏账准备期末', rightName: '⑤期末合计' },
  ))

  // ── ⑤ 变动表逐行平衡（F4-7）──────────────────────────────────────────────
  // 源模板 B100 / G48：期末 = 期初 + 计提 − 收回或转回 − 核销 − 转销 − 其他变动
  // （预设 F4-7 写的「+ 其他变动」是从应收账款泛化复制，不采纳）
  const movementAll = [...input.movementRows, ...input.movementDetailRows]
  movementAll.forEach((r, i) => {
    const label = String(r.label || `第 ${i + 1} 行`).trim()
    if (!label || label === '其中：') return
    checks.push(eqCheck(
      `F4-7:${i}`,
      `⑤变动表 ${label} 期末数`,
      'F4-7 期末 = 期初 + 计提 − 收回或转回 − 核销 − 转销 − 其他变动（源模板 G48 / B100 公式）',
      num(r.priorBalance) + num(r.provision) - num(r.reversal) - num(r.writeOff)
        - num(r.transfer) - num(r.other),
      num(r.endBalance),
      [REF_BAD_DEBT],
      { leftName: '按公式计算', rightName: '期末数列' },
    ))
  })

  // ── ⑤ 「其中：」明细之和 = 按组合计提行（F4-20，仅国企且有明细时）──────────
  if (isSoe && input.movementDetailRows.length > 0 && input.movementPortfolio) {
    const cols: Array<[keyof D1CheckMovementRow, string]> = [
      ['priorBalance', '期初数'],
      ['provision', '计提'],
      ['reversal', '收回或转回'],
      ['writeOff', '核销'],
      ['other', '其他变动'],
      ['endBalance', '期末数'],
    ]
    for (const [field, name] of cols) {
      checks.push(eqCheck(
        `F4-20:${String(field)}`,
        `⑤「其中：」明细之和 ↔ 按组合计提行 ${name}`,
        'F4-20 「其中：」下方所有明细行之和 = 按组合计提行（每个数值列独立校验）',
        sum(input.movementDetailRows, r => num(r[field] as number)),
        num(input.movementPortfolio[field] as number),
        [REF_BAD_DEBT],
        { leftName: '明细之和', rightName: '按组合计提行' },
      ))
    }
  }

  // ── ⑥⑦⑧ 明细和 = 合计（F4-21 / F4-22 / F4-23）───────────────────────────
  checks.push(eqCheck(
    'F4-21',
    '⑥期末已质押 合计',
    'F4-21 各明细行之和 = 合计行',
    sum(input.pledgedRows, r => r.amount),
    num(input.pledgedTotal),
    [REF_PLEDGE],
    { leftName: '明细之和', rightName: '合计行' },
  ))
  checks.push(eqCheck(
    'F4-22:derecognized',
    '⑦已背书或贴现 期末终止确认金额',
    'F4-22 各明细行之和 = 合计行（每个数值列独立校验）',
    sum(input.endorsedRows, r => r.derecognized),
    num(input.endorsedTotal.derecognized),
    [REF_ENDORSE],
    { leftName: '明细之和', rightName: '合计行' },
  ))
  checks.push(eqCheck(
    'F4-22:notDerecognized',
    '⑦已背书或贴现 期末未终止确认金额',
    'F4-22 各明细行之和 = 合计行（每个数值列独立校验）',
    sum(input.endorsedRows, r => r.notDerecognized),
    num(input.endorsedTotal.notDerecognized),
    [REF_ENDORSE],
    { leftName: '明细之和', rightName: '合计行' },
  ))
  checks.push(eqCheck(
    'F4-23',
    '⑧因出票人未履约转应收账款 合计',
    'F4-23 各明细行之和 = 合计行',
    sum(input.transferRows, r => r.amount),
    num(input.transferTotal),
    [REF_MAIN],
    { leftName: '明细之和', rightName: '合计行' },
  ))

  // ── ⑨ 核销（F4-24）+ 与⑤变动表「本期核销」对账 ──────────────────────────
  checks.push(eqCheck(
    'F4-24:detail',
    '⑨重要核销逐项之和 ↔ 核销总额',
    'F4-24 ⑨表（含子表）各明细行之和 = 合计行；逐项披露只覆盖重要者，差额为非重要核销',
    sum(input.writeOffDetailRows, r => r.amount),
    num(input.writeOffAmount),
    [REF_WRITEOFF],
    { leftName: '逐项之和', rightName: '核销总额', level: 'warn' },
  ))
  checks.push(eqCheck(
    'F4-24:movement',
    '⑨核销总额 ↔ ⑤变动表本期核销',
    '核销总额应与⑤坏账准备变动表「本期核销」列一致（源模板核销表编制提示）',
    num(input.writeOffAmount),
    num(input.movementWriteOffTotal),
    [REF_WRITEOFF, REF_BAD_DEBT],
    { leftName: '⑨核销总额', rightName: '⑤本期核销' },
  ))

  const errorCount = checks.filter(c => c.level === 'error').length
  const warnCount = checks.filter(c => c.level === 'warn').length
  const okCount = checks.filter(c => c.level === 'ok').length
  const skipCount = checks.filter(c => c.level === 'skip').length
  return { checks, errorCount, warnCount, okCount, skipCount, allPass: errorCount === 0 }
}

// ─── 勾稽差异 → A13 未更正错报汇总 ───────────────────────────────────────────

/** 应收票据科目编码（附注 五、4 / 八、4 对应科目）。 */
export const D1_ACCOUNT_CODE = '1121'
export const D1_ACCOUNT_NAME = '应收票据'

/** `a13:push-misstatement` 的行草稿（形态 A：`{items:[...]}`，见 `useA13MisstatementBridge`）。 */
export interface D1MisstatementItem {
  wpCode: string
  description: string
  accountCode: string
  accountName: string
  amount: number
  indexRef: string
}

export interface D1MisstatementPayload {
  wpCode: string
  accountCode: string
  accountName: string
  source: string
  items: D1MisstatementItem[]
}

/**
 * 勾稽差异 → A13 错报推送载荷（纯函数）。
 *
 * 平台通道：`eventBus.emit('a13:push-misstatement', payload)` →
 * `useA13MisstatementBridge`（挂在 WorkpaperEditor Shell）→
 * `POST /api/projects/{pid}/misstatements` 写 `unadjusted_misstatements`。
 * 载荷用**形态 A**（`items[]`），桥会按 `amount` 归一并截断 `source_wp_code` ≤20 字符。
 *
 * 规则：
 * - 只推 `error`（`warn` 是「逐项披露只覆盖重要者」这类正常差额，不是错报）
 * - `|diff| ≤ 容差` 或为 0 的不推（桥对 amount ≤0 也会丢弃，这里提前过滤）
 * - 描述内联规则编号与两侧金额，便于错报汇总里直接溯源
 */
export function buildD1MisstatementPayload(
  summary: D1ConsistencySummary,
  opts?: { checkIds?: readonly string[] },
): D1MisstatementPayload | null {
  const wanted = opts?.checkIds ? new Set(opts.checkIds) : null
  const items: D1MisstatementItem[] = []
  for (const c of summary.checks) {
    if (wanted ? !wanted.has(c.id) : c.level !== 'error') continue
    const amount = Math.abs(round2(c.diff))
    if (amount <= D1_AMOUNT_TOLERANCE) continue
    items.push({
      wpCode: 'D1',
      description:
        `应收票据披露勾稽差异：${c.label}（${c.id}）—— `
        + `本表 ${round2(c.left)}，勾稽对象 ${round2(c.right)}，差异 ${round2(c.diff)}。`
        + `规则：${c.rule}`,
      accountCode: D1_ACCOUNT_CODE,
      accountName: D1_ACCOUNT_NAME,
      amount,
      indexRef: c.refs.join('/'),
    })
  }
  if (items.length === 0) return null
  return {
    wpCode: 'D1',
    accountCode: D1_ACCOUNT_CODE,
    accountName: D1_ACCOUNT_NAME,
    source: 'D1披露勾稽校验',
    items,
  }
}
