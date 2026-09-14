/**
 * l8NoteSectionMap — L8 财务费用 披露表 ↔ 附注章节冻结映射
 *
 * 权威来源：
 * - `note_template_variant_matrix.json` · `cai_wu_fei_yong`
 *   → listed_standalone = 五、67 / soe_standalone = 八、68
 * - 源 xlsx `backend/wp_templates/L/L8 财务费用.xlsx` 的
 *   `附注披露信息（上市公司）` / `附注披露信息（国企）` 两 sheet 的 r7~r18
 * - 表名逐字 = 上市「财务费用（按费用性质列示）」/ 国企「财务费用」
 *
 * 🔴 **两版行集完全相同（源 xlsx 实证）**：共 11 个明细行 + 合计，其中
 * 「利息费用 / 利息净支出 / 汇兑净损失」是源模板的**计算行**，与合计一样
 * 由 `deriveL8Rows()` 读时推导，**不持久化**（派生列持久化会在编辑后错位）。
 *
 * 原组件两版行结构均为自造且互不相同（上市 7 行 / 国企 10 行），已按源模板统一。
 * 国企侧「其中：金融机构借款利息 / 非金融机构借款利息 / 资金占用费」源模板没有
 * → 保留在底稿做审计分析、**不推附注**（禁自造披露内容）。
 */
import { defineColumns, type ColumnDef } from './disclosureColumnDefs'

export type L8DisclosureVariant = 'listed' | 'soe'

export const L8_NOTE_SECTION = {
  listed: '五、67',
  soe: '八、68',
} as const satisfies Record<L8DisclosureVariant, string>

export const L8_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<L8DisclosureVariant, string>

/** 与 note_template `tables[].name` 逐字一致 */
export const L8_LISTED_SUBTABLE = {
  main: '财务费用（按费用性质列示）',
} as const

export const L8_SOE_SUBTABLE = {
  main: '财务费用',
} as const

export const L8_SUBTABLE = { ...L8_LISTED_SUBTABLE, ...L8_SOE_SUBTABLE } as const

/** 合计行字面 —— 本章节模板实证值（两版都是无空格「合计」） */
export const L8_TOTAL_LABEL = '合计'

export function l8MainTableName(variant: L8DisclosureVariant): string {
  return variant === 'listed' ? L8_LISTED_SUBTABLE.main : L8_SOE_SUBTABLE.main
}

// ── 行模型（源 xlsx r7~r18 逐字） ────────────────────────────────────────────

/** 录入行键（8 个，用户填数） */
export type L8InputKey =
  | 'interestTotal'
  | 'interestCapitalized'
  | 'interestIncome'
  | 'acceptanceDiscount'
  | 'exchangeLoss'
  | 'exchangeGain'
  | 'exchangeCapitalized'
  | 'feeAndOther'

/** 派生行键（4 个，读时推导） */
export type L8DerivedKey = 'interestExpense' | 'interestNet' | 'exchangeNet' | 'total'

export type L8RowKey = L8InputKey | L8DerivedKey

/** 行顺序与中文标签 —— 逐字取源 xlsx，禁改 */
export const L8_ROW_ORDER: readonly { key: L8RowKey; label: string; derived: boolean }[] = [
  { key: 'interestTotal', label: '利息费用总额', derived: false },
  { key: 'interestCapitalized', label: '减：利息资本化', derived: false },
  { key: 'interestExpense', label: '利息费用', derived: true },
  { key: 'interestIncome', label: '减：利息收入', derived: false },
  { key: 'interestNet', label: '利息净支出', derived: true },
  { key: 'acceptanceDiscount', label: '承兑汇票贴息', derived: false },
  { key: 'exchangeLoss', label: '汇兑损失', derived: false },
  { key: 'exchangeGain', label: '减：汇兑收益', derived: false },
  { key: 'exchangeCapitalized', label: '减：汇兑损益资本化', derived: false },
  { key: 'exchangeNet', label: '汇兑净损失', derived: true },
  { key: 'feeAndOther', label: '手续费及其他', derived: false },
  { key: 'total', label: L8_TOTAL_LABEL, derived: true },
]

export const L8_INPUT_KEYS: readonly L8InputKey[] = L8_ROW_ORDER
  .filter((r) => !r.derived)
  .map((r) => r.key as L8InputKey)

/** 一期的录入值 */
export type L8PeriodValues = Record<L8InputKey, number>

export function createEmptyL8Period(): L8PeriodValues {
  return {
    interestTotal: 0,
    interestCapitalized: 0,
    interestIncome: 0,
    acceptanceDiscount: 0,
    exchangeLoss: 0,
    exchangeGain: 0,
    exchangeCapitalized: 0,
    feeAndOther: 0,
  }
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 源模板派生关系（纯函数，读时推导）：
 *   利息费用   = 利息费用总额 − 减：利息资本化
 *   利息净支出 = 利息费用 − 减：利息收入
 *   汇兑净损失 = 汇兑损失 − 减：汇兑收益 − 减：汇兑损益资本化
 *   合计       = 利息净支出 + 承兑汇票贴息 + 汇兑净损失 + 手续费及其他
 */
export function deriveL8Period(input: L8PeriodValues): Record<L8RowKey, number> {
  const interestExpense = num(input.interestTotal) - num(input.interestCapitalized)
  const interestNet = interestExpense - num(input.interestIncome)
  const exchangeNet =
    num(input.exchangeLoss) - num(input.exchangeGain) - num(input.exchangeCapitalized)
  const total =
    interestNet + num(input.acceptanceDiscount) + exchangeNet + num(input.feeAndOther)
  return {
    interestTotal: num(input.interestTotal),
    interestCapitalized: num(input.interestCapitalized),
    interestExpense,
    interestIncome: num(input.interestIncome),
    interestNet,
    acceptanceDiscount: num(input.acceptanceDiscount),
    exchangeLoss: num(input.exchangeLoss),
    exchangeGain: num(input.exchangeGain),
    exchangeCapitalized: num(input.exchangeCapitalized),
    exchangeNet,
    feeAndOther: num(input.feeAndOther),
    total,
  }
}

export interface L8DisplayRow {
  key: L8RowKey
  label: string
  derived: boolean
  current: number
  prior: number
}

/** 供组件渲染的 12 行（含派生值） */
export function buildL8DisplayRows(
  current: L8PeriodValues,
  prior: L8PeriodValues,
): L8DisplayRow[] {
  const c = deriveL8Period(current)
  const p = deriveL8Period(prior)
  return L8_ROW_ORDER.map((r) => ({
    key: r.key,
    label: r.label,
    derived: r.derived,
    current: c[r.key],
    prior: p[r.key],
  }))
}

// ── 列定义 / 载荷 ────────────────────────────────────────────────────────────

export function l8ColumnsFor(variant: L8DisclosureVariant): Record<string, ColumnDef[]> {
  return {
    [l8MainTableName(variant)]: defineColumns([
      { key: 'label', label: '项目', is_label: true, flat: true },
      { key: 'current_amount', label: '本期发生额', format: 'amount', align: 'right' },
      { key: 'prior_amount', label: '上期发生额', format: 'amount', align: 'right' },
    ]),
  }
}

export const buildL8ListedColumns = () => l8ColumnsFor('listed')
export const buildL8SoeColumns = () => l8ColumnsFor('soe')

export function isL8DisclosureApplicable(
  variant: L8DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = (applicableStandards || []).map((s) => String(s).trim().toLowerCase()).filter(Boolean)
  if (list.length === 0) return true
  const hasListed = list.some((s) => s.includes('listed') || s.includes('上市'))
  const hasSoe = list.some((s) => s.includes('soe') || s.includes('state_owned') || s.includes('国'))
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveL8CurrentStandard(
  variant: L8DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): string {
  const list = (applicableStandards || []).map((s) => String(s).toLowerCase())
  if (variant === 'listed') {
    return list.some((s) => s === 'listed_consolidated' || (s.includes('listed') && s.includes('consol')))
      ? 'listed_consolidated'
      : 'listed_standalone'
  }
  return list.some((s) => s === 'soe_consolidated' || (s.includes('soe') && s.includes('consol')))
    ? 'soe_consolidated'
    : 'soe_standalone'
}

export interface L8SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  columns?: Record<string, ColumnDef[]>
}

export function buildL8MainRows(
  current: L8PeriodValues,
  prior: L8PeriodValues,
): Record<string, unknown>[] {
  return buildL8DisplayRows(current, prior).map((r) => ({
    label: r.label,
    current_amount: r.current,
    prior_amount: r.prior,
    ...(r.key === 'total' ? { is_total: true } : {}),
    ...(r.derived && r.key !== 'total' ? { is_subtotal: true } : {}),
  }))
}

export interface L8SyncSnapshot {
  variant: L8DisclosureVariant
  current: L8PeriodValues
  prior: L8PeriodValues
  /** 上市侧资本化率说明（源 xlsx r20）；国企侧源模板无此段 */
  capitalizationNote?: string
}

export function buildL8SyncPayload(
  wpId: string,
  snapshot: L8SyncSnapshot,
  applicableStandards?: readonly string[] | null,
): L8SyncPayload | null {
  const { variant, current, prior } = snapshot
  if (!isL8DisclosureApplicable(variant, applicableStandards)) return null

  const sub: Record<string, unknown> = {
    [l8MainTableName(variant)]: buildL8MainRows(current, prior),
  }

  // 🔴 仅上市侧有说明段（源 xlsx r19/r20「利息资本化金额已计入…资本化率为XX%」）
  if (variant === 'listed' && snapshot.capitalizationNote?.trim()) {
    sub._note_texts = [{
      section: 'l8-listed-capitalization',
      title: '利息资本化说明',
      text: snapshot.capitalizationNote.trim(),
    }] as unknown as Record<string, unknown>[]
  }

  return {
    wp_id: wpId,
    sheet_name: L8_DISCLOSURE_SHEET_NAME[variant],
    section_id: L8_NOTE_SECTION[variant],
    current_standard: resolveL8CurrentStandard(variant, applicableStandards),
    sub_table_data: sub as Record<string, Record<string, unknown>[]>,
    columns: l8ColumnsFor(variant),
  }
}
