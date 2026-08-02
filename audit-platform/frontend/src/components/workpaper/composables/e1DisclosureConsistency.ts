/**
 * e1DisclosureConsistency — E1 货币资金披露内部勾稽（纯函数）
 *
 * **规则全部取自真源，禁自造校验**：
 *
 * ① `note_check_preset_formulas.json`（两版各 6 条，**listed 与 soe 完全相同**）
 *
 * | id   | 表 | 公式 |
 * |------|----|------|
 * | F1-1 | ①货币资金分类表 | 报表.货币资金期末 = ①表.合计行.期末余额 |
 * | F1-2 | ①货币资金分类表 | 报表.货币资金期初 = ①表.合计行.期初余额 |
 * | F1-3 | ①货币资金分类表 | ①表 sum(合计行以外的所有明细行) = 合计行（每个数值列独立校验） |
 * | F1-4 | ②受限制的货币资金明细表 | ②表 sum(合计行以外的所有明细行) = 合计行（每列独立） |
 * | F1-5 | ②受限制的货币资金明细表 | ②表.合计行.期末 = 报表.货币资金期末 − 补充资料③表."期末现金及现金等价物余额" |
 * | F1-6 | ②受限制的货币资金明细表 | ②表.合计行.期初 = 报表.货币资金期初 − 补充资料③表."期初现金及现金等价物余额" |
 *
 * ② 源 xlsx「附注披露信息(上市公司)」自带的两条表内公式
 *
 * - `B16 = B14 − D62`：主表合计 − 原币表人民币金额合计（应为 0）—— 这是**勾稽校验行**，
 *   不是披露行，故不进附注载荷，只进本引擎。
 * - `B29 = B40+B46+B52+B58`：外币性货币项目某币种 = 原币表**四个分组**同币种之和。
 *
 * **F1-5 / F1-6 的数据可得性**：「现金及现金等价物余额」在现金流量表补充资料
 * （`CFSS-*` 行）里，**E1 披露表本身拿不到**。故设计为：
 * - 调用方能提供时（`cashEquivalents`）→ 真实比对
 * - 拿不到 → `level='skip'` 并给出**推算值**（货币资金合计 − 受限合计），
 *   供审计师与补充资料③表人工核对。**不伪造、不塌成 0**（共享原语的 `eqCheck` 语义）。
 *
 * spec: .kiro/specs/e1-four-table-extraction-and-disclosure-alignment/
 *       Requirements 9.1, 9.2 / Property 14
 */
import {
  eqCheck,
  nz,
  segmentSumCheck,
  summarizeChecks,
  sumNullable,
  type NullableAmount,
  type WpCheckResult,
  type WpCheckSummary,
} from './shared/disclosureConsistency'

// ─── 输入 ─────────────────────────────────────────────────────────────────────

/** ①主表一行（合计行由 `isTotal` 标识；「其中：」备注行由 `isMemo` 标识，不参与加总） */
export interface E1CheckMainRow {
  key: string
  label: string
  endingAmount: NullableAmount
  openingAmount: NullableAmount
  isTotal?: boolean
  isMemo?: boolean
}

/** ②受限表一行 */
export interface E1CheckRestrictedRow {
  label: string
  endingAmount: NullableAmount
  openingAmount: NullableAmount
}

/** 原币表一行（源 xlsx R38~R62；分组行不参与，只取币种叶子行） */
export interface E1CheckFxRow {
  groupSlot: string
  currencyKey: string
  currencyLabel: string
  isGroup: boolean
  endRmb: NullableAmount
  endForeign: NullableAmount
}

export interface E1ConsistencyInput {
  variant: 'listed' | 'soe'
  /** ①主表行（含合计行） */
  mainRows: readonly E1CheckMainRow[]
  /** ②受限表行（不含合计行 —— 合计由本引擎推算，与 UI 同源） */
  restrictedRows: readonly E1CheckRestrictedRow[]
  /**
   * 报表「货币资金」金额（四表口径：`tb_values.total_closing` / `total_opening`）。
   * 拿不到传 `null` → F1-1/F1-2 skip 而非误报。
   */
  reportEnding?: NullableAmount
  reportOpening?: NullableAmount
  /** 原币表行（可空 —— 未启用详细版时不产出相关条目） */
  fxRows?: readonly E1CheckFxRow[]
  /**
   * 现金流量表补充资料③表的「现金及现金等价物余额」。
   * 拿不到传 `null` → F1-5/F1-6 skip，并给出推算值供人工核对。
   */
  cashEquivalentsEnding?: NullableAmount
  cashEquivalentsOpening?: NullableAmount
}

// ─── 内部助手 ─────────────────────────────────────────────────────────────────

const IDX_MAIN = 'wp:E1-1'
const IDX_CASH = 'wp:E1-2'
const IDX_BANK = 'wp:E1-3'

function totalRow(rows: readonly E1CheckMainRow[]): E1CheckMainRow | undefined {
  return rows.find((r) => r.isTotal)
}

/** 参与合计的明细行（排除合计行与「其中：」备注行 —— 后者是主表合计之内的再分解） */
function summableRows(rows: readonly E1CheckMainRow[]): E1CheckMainRow[] {
  return rows.filter((r) => !r.isTotal && !r.isMemo)
}

function restrictedTotal(
  rows: readonly E1CheckRestrictedRow[],
  field: 'endingAmount' | 'openingAmount',
): NullableAmount {
  if (!rows.length) return null
  return sumNullable(rows.map((r) => nz(r[field])))
}

/** 原币表币种叶子行（排除分组行） */
function fxLeaves(rows: readonly E1CheckFxRow[] | undefined): E1CheckFxRow[] {
  return (rows ?? []).filter((r) => !r.isGroup)
}

// ─── 引擎 ─────────────────────────────────────────────────────────────────────

/**
 * 计算 E1 披露内部勾稽。**纯函数**，规则 id 覆盖 F1-1~F1-6 + 源 xlsx 两条。
 */
export function computeE1Consistency(input: E1ConsistencyInput): WpCheckResult[] {
  const out: WpCheckResult[] = []
  const total = totalRow(input.mainRows)
  const details = summableRows(input.mainRows)

  // ── F1-1 / F1-2：报表货币资金 = ①表合计行 ────────────────────────────────
  out.push(
    eqCheck(
      'F1-1 报表货币资金（期末）',
      '校验预设 F1-1：报表.货币资金期末 = ①货币资金分类表.合计行.期末余额',
      nz(input.reportEnding),
      nz(total?.endingAmount),
      [IDX_MAIN],
    ),
  )
  out.push(
    eqCheck(
      'F1-2 报表货币资金（期初）',
      '校验预设 F1-2：报表.货币资金期初 = ①货币资金分类表.合计行.期初余额',
      nz(input.reportOpening),
      nz(total?.openingAmount),
      [IDX_MAIN],
    ),
  )

  // ── F1-3：①表明细之和 = 合计行（每个数值列独立校验）────────────────────────
  const f1_3_end = segmentSumCheck(
    'F1-3 ①表明细合计（期末）',
    '校验预设 F1-3：①表 sum(合计行以外的所有明细行) = 合计行（期末列）。'
      + '「其中：存放在境外的款项总额」是合计之内的再分解，不参与加总。',
    details.map((r) => nz(r.endingAmount)),
    nz(total?.endingAmount),
    [IDX_MAIN],
  )
  if (f1_3_end) out.push(f1_3_end)
  const f1_3_open = segmentSumCheck(
    'F1-3 ①表明细合计（期初）',
    '校验预设 F1-3：①表 sum(明细行) = 合计行（期初列，独立校验）',
    details.map((r) => nz(r.openingAmount)),
    nz(total?.openingAmount),
    [IDX_MAIN],
  )
  if (f1_3_open) out.push(f1_3_open)

  // ── F1-4：②表明细之和 = 合计行（本引擎的合计即明细之和 → 恒成立，
  //          但仍产出条目以显式覆盖该校验预设，且当明细含 null 时会 skip）──────
  const rstEnd = restrictedTotal(input.restrictedRows, 'endingAmount')
  const rstOpen = restrictedTotal(input.restrictedRows, 'openingAmount')
  const f1_4_end = segmentSumCheck(
    'F1-4 ②表明细合计（期末）',
    '校验预设 F1-4：②受限制的货币资金明细表 sum(合计行以外的所有明细行) = 合计行（期末列）',
    input.restrictedRows.map((r) => nz(r.endingAmount)),
    rstEnd,
    [IDX_MAIN],
  )
  if (f1_4_end) out.push(f1_4_end)
  const f1_4_open = segmentSumCheck(
    'F1-4 ②表明细合计（期初）',
    '校验预设 F1-4：②表 sum(明细行) = 合计行（期初列，独立校验）',
    input.restrictedRows.map((r) => nz(r.openingAmount)),
    rstOpen,
    [IDX_MAIN],
  )
  if (f1_4_open) out.push(f1_4_open)

  // ── F1-5 / F1-6：②表合计 = 报表货币资金 − 现金及现金等价物余额 ─────────────
  //    现金及现金等价物在现金流量表补充资料③表，E1 披露表拿不到 → 拿不到就 skip，
  //    并在 rule 里给出推算值供人工核对（不伪造、不塌成 0）。
  const pushCashEquivCheck = (
    id: 'F1-5' | 'F1-6',
    period: '期末' | '期初',
    report: NullableAmount,
    equiv: NullableAmount,
    rstTotal: NullableAmount,
  ) => {
    const expected =
      report === null || equiv === null ? null : Math.round((report - equiv) * 100) / 100
    const derived =
      report === null || rstTotal === null ? null : Math.round((report - rstTotal) * 100) / 100
    const hint =
      equiv === null && derived !== null
        ? `（未取到补充资料③表数据 → 按本表推算：${period}现金及现金等价物 ≈ ${derived}，请与补充资料③表人工核对）`
        : ''
    out.push(
      eqCheck(
        `${id} 受限资金与现金等价物（${period}）`,
        `校验预设 ${id}：②表.合计行.${period} = 报表.货币资金${period} − `
          + `现金流量表补充资料③表."${period}现金及现金等价物余额"${hint}`,
        rstTotal,
        expected,
        [IDX_MAIN],
      ),
    )
  }
  pushCashEquivCheck(
    'F1-5',
    '期末',
    nz(input.reportEnding),
    nz(input.cashEquivalentsEnding),
    rstEnd,
  )
  pushCashEquivCheck(
    'F1-6',
    '期初',
    nz(input.reportOpening),
    nz(input.cashEquivalentsOpening),
    rstOpen,
  )

  // ── 源 xlsx B16 = B14 − D62：主表合计 = 原币表人民币金额合计 ────────────────
  const leaves = fxLeaves(input.fxRows)
  if (leaves.length) {
    out.push(
      eqCheck(
        '源模板 B16 主表合计 vs 原币表',
        '源 xlsx 上市侧 B16 = B14 − D62 / 国企侧 R12 列 E = B12 − 原币表 D62：'
          + '主表合计（期末）应等于「货币资金（原币）」表人民币金额合计。'
          + '两变体的外币两表逐字相同，故本规则对两版同样适用。'
          + '该单元格是勾稽校验行，不是披露行（故不进附注载荷）。',
        nz(total?.endingAmount),
        sumNullable(leaves.map((r) => nz(r.endRmb))),
        [IDX_MAIN, IDX_CASH, IDX_BANK],
      ),
    )
  }

  // ── 源 xlsx B29 = B40+B46+B52+B58：外币性货币项目各币种 = 原币表四段之和 ────
  //    本引擎的「外币性货币项目」表本就由原币表派生（读时推导），故这里校验的是
  //    **分组行小计** 与 **该组币种叶子之和** 一致（防手工改分组行导致两表打架）。
  const groups = (input.fxRows ?? []).filter((r) => r.isGroup)
  for (const g of groups) {
    const own = leaves.filter((r) => r.groupSlot === g.groupSlot)
    if (!own.length) continue
    const chk = segmentSumCheck(
      `原币表分组小计（${g.currencyLabel || g.groupSlot}）`,
      '源 xlsx 原币表 D38=SUM(D39:D43) 等：分组行人民币金额 = 该组各币种行之和。'
        + '「外币性货币项目」表各币种行 = 原币表四个分组同币种之和（B29=B40+B46+B52+B58）。',
      own.map((r) => nz(r.endRmb)),
      nz(g.endRmb),
      [IDX_CASH, IDX_BANK],
    )
    if (chk) out.push(chk)
  }

  return out
}

/** 汇总（复用平台共享原语）。 */
export function summarizeE1Consistency(results: readonly WpCheckResult[]): WpCheckSummary {
  return summarizeChecks(results)
}

/** 本引擎覆盖的校验预设 id 全集（守卫据此断言 Property 14 的完备性）。 */
export const E1_COVERED_PRESET_IDS: readonly string[] = Object.freeze([
  'F1-1',
  'F1-2',
  'F1-3',
  'F1-4',
  'F1-5',
  'F1-6',
])

// ─── 勾稽差异 → A13 未更正错报汇总 ───────────────────────────────────────────

/**
 * 货币资金科目编码与名称。
 *
 * **不写死取数用的科目码** —— 取数走 `semantic_account_resolver`（逐项目按科目名定位）；
 * 这里的 `1001` 只作**错报汇总的展示口径**（A13 按报表项目归集，货币资金项目下
 * `1001/1002/1012` 三个科目共用一个报表行 `BS-002`），故取报表项目的首个科目码。
 */
export const E1_ACCOUNT_CODE = '1001'
export const E1_ACCOUNT_NAME = '货币资金'
export const E1_REPORT_ROW_CODE = 'BS-002'

/** `a13:push-misstatement` 的行草稿（形态 A，见 `useA13MisstatementBridge`）。 */
export interface E1MisstatementItem {
  wpCode: string
  description: string
  accountCode: string
  accountName: string
  amount: number
  indexRef: string
}

export interface E1MisstatementPayload {
  wpCode: string
  accountCode: string
  accountName: string
  source: string
  items: E1MisstatementItem[]
}

/**
 * 勾稽差异 → A13 错报推送载荷（纯函数）。
 *
 * 平台通道：`eventBus.emit('a13:push-misstatement', payload)` →
 * `useA13MisstatementBridge` → `POST /api/projects/{pid}/misstatements`。
 *
 * 规则（与 D1 同口径）：
 * - 只推 `level === 'error'`（`skip` 是「跨底稿取数未就绪」不是错报，绝不推）
 * - `|diff| ≤ 0.01` 的不推（桥对 `amount ≤ 0` 也会丢弃，这里提前过滤）
 * - `labels` 指定时按 label 精确推送（单行推送场景）
 * - 描述内联规则 label、两侧金额与规则原文，便于错报汇总里直接溯源
 */
export function buildE1MisstatementPayload(
  results: readonly WpCheckResult[],
  opts?: { labels?: readonly string[] },
): E1MisstatementPayload | null {
  const wanted = opts?.labels ? new Set(opts.labels) : null
  const items: E1MisstatementItem[] = []
  for (const c of results) {
    if (wanted ? !wanted.has(c.label) : c.level !== 'error') continue
    // 指定 labels 时也只推真差异（不把 skip/ok 当错报）
    if (c.level !== 'error' || c.diff === null) continue
    const amount = Math.round(Math.abs(c.diff) * 100) / 100
    if (amount <= 0.01) continue
    items.push({
      wpCode: 'E1',
      description:
        `货币资金披露勾稽差异：${c.label} —— `
        + `本表 ${c.left ?? '—'}，勾稽对象 ${c.right ?? '—'}，差异 ${c.diff}。`
        + `规则：${c.rule}`,
      accountCode: E1_ACCOUNT_CODE,
      accountName: E1_ACCOUNT_NAME,
      amount,
      indexRef: (c.refs ?? []).join('/'),
    })
  }
  if (items.length === 0) return null
  return {
    wpCode: 'E1',
    accountCode: E1_ACCOUNT_CODE,
    accountName: E1_ACCOUNT_NAME,
    source: 'E1披露勾稽校验',
    items,
  }
}
