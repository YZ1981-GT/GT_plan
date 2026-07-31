/**
 * l5NoteSectionMap — L5 长期应付款 / L6 专项应付款 披露表 ↔ 附注章节冻结映射
 *
 * 权威来源：
 * - `note_template_variant_matrix.json` · `chang_qi_ying_fu_kuan`
 *   → listed_standalone = 五、48 / soe_standalone = 八、53
 *   另 `yi_nian_nei_dao_qi_de_chang_qi_ying_fu_kuan` → soe 八、47（上市侧为 null）
 * - 源 xlsx `backend/wp_templates/L/L5 长期应付款.xlsx`
 *   `附注披露信息（上市公司）` / `附注披露信息（国企）`（**都无「核对」二字**）
 * - 源 xlsx `backend/wp_templates/L/L6 专项应付款.xlsx`
 *   `附注披露（上市公司）信息` / `附注披露（国企）信息`（**括号在中间**，源模板即如此）
 *
 * 🔴 **L6 专项应付款无独立章节，与 L5 共章节**：源 xlsx L6 两版都写着
 * 「【长期应付款与专项应付款的合计数披露详见P5-1】」。两个底稿分别推**不同子表**，
 * 靠后端 `sub_table_data` 按 key 浅合并（同 H4→H2 已验证范式）：
 *   - L5 推「长期应付款」主表 +「（按款项性质列示）/①前5 项」
 *   - L6 推「专项应付款」/「①专项应付款期末余额最大的前5 项」
 * 两者**不得互相覆盖对方的表**（各自 payload 只含自己那几张）。
 */
import { defineColumns, type ColumnDef } from './disclosureColumnDefs'

export type L5DisclosureVariant = 'listed' | 'soe'

export const L5_NOTE_SECTION = {
  listed: '五、48',
  soe: '八、53',
} as const satisfies Record<L5DisclosureVariant, string>

/** 一年内到期的长期应付款 —— 仅国企有独立章节（上市侧并入 五、48 主表减项） */
export const L5_WITHIN1Y_NOTE_SECTION = { soe: '八、47' } as const

export const L5_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<L5DisclosureVariant, string>

/** L6 源 xlsx tab 名 —— **括号在中间**，源模板字面，勿"修正" */
export const L6_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露（上市公司）信息',
  soe: '附注披露（国企）信息',
} as const satisfies Record<L5DisclosureVariant, string>

/** 与 note_template `tables[].name` 逐字一致（L5 自己推送的表） */
export const L5_LISTED_SUBTABLE = {
  main: '长期应付款',
  byNature: '长期应付款（按款项性质列示）',
} as const

export const L5_SOE_SUBTABLE = {
  main: '长期应付款',
  top5: '①长期应付款项期末余额最大的前5 项',
} as const

/** L6 专项应付款推送的表（在 L5 章节内） */
export const L6_LISTED_SUBTABLE = {
  special: '专项应付款',
} as const

export const L6_SOE_SUBTABLE = {
  special: '①专项应付款期末余额最大的前5 项',
} as const

/** 八、47 子表 */
export const L5_WITHIN1Y_SUBTABLE = {
  main: '（3）一年内到期的长期应付款',
} as const

export const L5_TOTAL_LABEL = '合计'
export const L5_SUBTOTAL_LABEL = '小计'

/** 「减：未确认融资费用：」分组标签行（源 xlsx r15），其下明细与毛额段一一对应 */
export const L5_UNRECOGNIZED_FINANCE_LABEL = '减：未确认融资费用：'

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function normalizeLabel(v: unknown): string {
  return String(v ?? '').replace(/\s+/g, '')
}

function isTotalLabel(v: unknown): boolean {
  return normalizeLabel(v) === L5_TOTAL_LABEL
}

function isSubtotalLabel(v: unknown): boolean {
  return normalizeLabel(v) === L5_SUBTOTAL_LABEL
}

export function isL5DisclosureApplicable(
  variant: L5DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = (applicableStandards || []).map((s) => String(s).trim().toLowerCase()).filter(Boolean)
  if (list.length === 0) return true
  const hasListed = list.some((s) => s.includes('listed') || s.includes('上市'))
  const hasSoe = list.some((s) => s.includes('soe') || s.includes('state_owned') || s.includes('国'))
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveL5CurrentStandard(
  variant: L5DisclosureVariant,
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

// ── 列定义（全部单级表头 → 显式 flat） ──────────────────────────────────────

function twoPeriod(endLabel: string, priorLabel: string): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'end_amount', label: endLabel, format: 'amount', align: 'right' },
    { key: 'prior_amount', label: priorLabel, format: 'amount', align: 'right' },
  ])
}

function specialPayable(beginLabel: string, endLabel: string, withReason: boolean): ColumnDef[] {
  const defs: Array<Partial<ColumnDef> & { key: string; label: string }> = [
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'begin_amount', label: beginLabel, format: 'amount', align: 'right' },
    { key: 'increase', label: '本期增加', format: 'amount', align: 'right' },
    { key: 'decrease', label: '本期减少', format: 'amount', align: 'right' },
    { key: 'end_amount', label: endLabel, format: 'amount', align: 'right' },
  ]
  if (withReason) defs.push({ key: 'reason', label: '形成原因', format: 'text' })
  return defineColumns(defs)
}

/** L5 自己的两张表 */
export function l5ColumnsFor(variant: L5DisclosureVariant): Record<string, ColumnDef[]> {
  if (variant === 'listed') {
    return {
      [L5_LISTED_SUBTABLE.main]: twoPeriod('期末数', '上年年末余额'),
      [L5_LISTED_SUBTABLE.byNature]: twoPeriod('期末数', '上年年末余额'),
    }
  }
  return {
    [L5_SOE_SUBTABLE.main]: twoPeriod('期末数', '期初数'),
    [L5_SOE_SUBTABLE.top5]: twoPeriod('期末余额', '年初余额'),
  }
}

export const buildL5ListedColumns = () => l5ColumnsFor('listed')
export const buildL5SoeColumns = () => l5ColumnsFor('soe')

/** L6 专项应付款表（国企侧无「形成原因」列；列头取附注模版字面） */
export function l6ColumnsFor(variant: L5DisclosureVariant): Record<string, ColumnDef[]> {
  return variant === 'listed'
    ? { [L6_LISTED_SUBTABLE.special]: specialPayable('期初数', '期末数', true) }
    : { [L6_SOE_SUBTABLE.special]: specialPayable('期初余额', '期末余额', false) }
}

export const buildL6ListedColumns = () => l6ColumnsFor('listed')
export const buildL6SoeColumns = () => l6ColumnsFor('soe')

export function l5Within1yColumns(): Record<string, ColumnDef[]> {
  return { [L5_WITHIN1Y_SUBTABLE.main]: twoPeriod('期末余额', '期初余额') }
}

// ── 行模型 ───────────────────────────────────────────────────────────────────

/** 两期金额行（主表 / 按性质列示 / 前5 项 共用） */
export interface L5TwoPeriodRow {
  label: string
  endAmount: number
  priorAmount: number
}

/** 专项应付款行（L6） */
export interface L6SpecialRow {
  label: string
  beginAmount: number
  increase: number
  decrease: number
  reason?: string
}

/** 期末余额读时派生（禁持久化派生值） */
export function l6SpecialEndAmount(r: L6SpecialRow): number {
  return num(r.beginAmount) + num(r.increase) - num(r.decrease)
}

export interface L5SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  columns?: Record<string, ColumnDef[]>
}

/**
 * 主表两行（长期应付款 / 专项应付款）+ 合计。
 *
 * 「专项应付款」行金额由 L6 侧提供（组件可从 L6 快照带入；无值则 0，
 * 不臆造 —— 附注侧该行也会被 L6 推送的明细表印证）。
 */
export function buildL5MainRows(
  longTerm: { end: number; prior: number },
  special: { end: number; prior: number },
): Record<string, unknown>[] {
  const rows = [
    { label: '长期应付款', end_amount: num(longTerm.end), prior_amount: num(longTerm.prior) },
    { label: '专项应付款', end_amount: num(special.end), prior_amount: num(special.prior) },
  ]
  return [
    ...rows,
    {
      label: L5_TOTAL_LABEL,
      end_amount: rows.reduce((s, r) => s + num(r.end_amount), 0),
      prior_amount: rows.reduce((s, r) => s + num(r.prior_amount), 0),
      is_total: true,
    },
  ]
}

/**
 * 上市「（按款项性质列示）」：毛额段 + `减：未确认融资费用：` 标签行 + 未确认段
 * + 小计 + 减一年内到期 + 合计。
 *
 * 小计 = Σ毛额 − Σ未确认融资费用；合计 = 小计 − 一年内到期。
 */
export function buildL5ByNatureRows(input: {
  gross: readonly L5TwoPeriodRow[]
  unrecognized: readonly L5TwoPeriodRow[]
  within1y: { end: number; prior: number }
}): Record<string, unknown>[] {
  const gross = input.gross.filter((r) => String(r.label ?? '').trim())
  const unrec = input.unrecognized.filter((r) => String(r.label ?? '').trim())
  const out: Record<string, unknown>[] = gross.map((r) => ({
    label: r.label,
    end_amount: num(r.endAmount),
    prior_amount: num(r.priorAmount),
  }))
  // 分组标签行（源 xlsx r15）：无金额，仅承载「以下为减项」语义
  out.push({ label: L5_UNRECOGNIZED_FINANCE_LABEL, end_amount: null, prior_amount: null })
  for (const r of unrec) {
    out.push({ label: r.label, end_amount: num(r.endAmount), prior_amount: num(r.priorAmount) })
  }
  const subEnd = gross.reduce((s, r) => s + num(r.endAmount), 0)
    - unrec.reduce((s, r) => s + num(r.endAmount), 0)
  const subPrior = gross.reduce((s, r) => s + num(r.priorAmount), 0)
    - unrec.reduce((s, r) => s + num(r.priorAmount), 0)
  out.push({ label: L5_SUBTOTAL_LABEL, end_amount: subEnd, prior_amount: subPrior, is_total: true })
  out.push({
    label: '减：一年内到期长期应付款',
    end_amount: num(input.within1y.end),
    prior_amount: num(input.within1y.prior),
  })
  out.push({
    label: L5_TOTAL_LABEL,
    end_amount: subEnd - num(input.within1y.end),
    prior_amount: subPrior - num(input.within1y.prior),
    is_total: true,
  })
  return out
}

/** 国企「①前5 项」：明细 + 其他 + 小计 + 减一年内到期 + 合计 */
export function buildL5SoeTop5Rows(input: {
  items: readonly L5TwoPeriodRow[]
  other: { end: number; prior: number }
  within1y: { end: number; prior: number }
}): Record<string, unknown>[] {
  const items = input.items
    .filter((r) => String(r.label ?? '').trim() && !isTotalLabel(r.label) && !isSubtotalLabel(r.label))
  const out: Record<string, unknown>[] = items.map((r) => ({
    label: r.label,
    end_amount: num(r.endAmount),
    prior_amount: num(r.priorAmount),
  }))
  out.push({ label: '其他', end_amount: num(input.other.end), prior_amount: num(input.other.prior) })
  const subEnd = items.reduce((s, r) => s + num(r.endAmount), 0) + num(input.other.end)
  const subPrior = items.reduce((s, r) => s + num(r.priorAmount), 0) + num(input.other.prior)
  out.push({ label: L5_SUBTOTAL_LABEL, end_amount: subEnd, prior_amount: subPrior, is_total: true })
  out.push({
    label: '减：一年内到期长期应付款项',
    end_amount: num(input.within1y.end),
    prior_amount: num(input.within1y.prior),
  })
  out.push({
    label: L5_TOTAL_LABEL,
    end_amount: subEnd - num(input.within1y.end),
    prior_amount: subPrior - num(input.within1y.prior),
    is_total: true,
  })
  return out
}

/** L6 专项应付款行（期末余额读时派生） */
export function buildL6SpecialRows(
  rows: readonly L6SpecialRow[],
  variant: L5DisclosureVariant,
): Record<string, unknown>[] {
  const data = rows.filter((r) => String(r.label ?? '').trim() && !isTotalLabel(r.label))
  const out: Record<string, unknown>[] = data.map((r) => {
    const row: Record<string, unknown> = {
      label: String(r.label).trim(),
      begin_amount: num(r.beginAmount),
      increase: num(r.increase),
      decrease: num(r.decrease),
      end_amount: l6SpecialEndAmount(r),
    }
    if (variant === 'listed') row.reason = r.reason ?? ''
    return row
  })
  const total: Record<string, unknown> = {
    label: L5_TOTAL_LABEL,
    begin_amount: data.reduce((s, r) => s + num(r.beginAmount), 0),
    increase: data.reduce((s, r) => s + num(r.increase), 0),
    decrease: data.reduce((s, r) => s + num(r.decrease), 0),
    end_amount: data.reduce((s, r) => s + l6SpecialEndAmount(r), 0),
    is_total: true,
  }
  if (variant === 'listed') total.reason = ''
  out.push(total)
  return out
}

// ── 载荷 ─────────────────────────────────────────────────────────────────────

export interface L5SyncSnapshot {
  variant: L5DisclosureVariant
  /** 主表「长期应付款」行 */
  longTerm: { end: number; prior: number }
  /** 主表「专项应付款」行（由 L6 底稿维护，此处仅为主表勾稽用） */
  special: { end: number; prior: number }
  /** 上市：按款项性质列示 */
  byNature?: {
    gross: readonly L5TwoPeriodRow[]
    unrecognized: readonly L5TwoPeriodRow[]
    within1y: { end: number; prior: number }
  }
  /** 国企：前 5 项 */
  top5?: {
    items: readonly L5TwoPeriodRow[]
    other: { end: number; prior: number }
    within1y: { end: number; prior: number }
  }
}

/**
 * L5 载荷 —— 只推「长期应付款」主表 + 自己那张明细表。
 *
 * 🔴 **不含「专项应付款」表**（由 L6 推送）：同章节不同子表按 key 浅合并，
 * 若两侧都推同一张表会互相覆盖。
 */
export function buildL5SyncPayload(
  wpId: string,
  snapshot: L5SyncSnapshot,
  applicableStandards?: readonly string[] | null,
): L5SyncPayload | null {
  const { variant } = snapshot
  if (!isL5DisclosureApplicable(variant, applicableStandards)) return null

  const sub: Record<string, Record<string, unknown>[]> = {}
  const columns: Record<string, ColumnDef[]> = {}
  const all = l5ColumnsFor(variant)

  if (variant === 'listed') {
    sub[L5_LISTED_SUBTABLE.main] = buildL5MainRows(snapshot.longTerm, snapshot.special)
    columns[L5_LISTED_SUBTABLE.main] = all[L5_LISTED_SUBTABLE.main]
    if (snapshot.byNature) {
      sub[L5_LISTED_SUBTABLE.byNature] = buildL5ByNatureRows(snapshot.byNature)
      columns[L5_LISTED_SUBTABLE.byNature] = all[L5_LISTED_SUBTABLE.byNature]
    }
  } else {
    sub[L5_SOE_SUBTABLE.main] = buildL5MainRows(snapshot.longTerm, snapshot.special)
    columns[L5_SOE_SUBTABLE.main] = all[L5_SOE_SUBTABLE.main]
    if (snapshot.top5) {
      sub[L5_SOE_SUBTABLE.top5] = buildL5SoeTop5Rows(snapshot.top5)
      columns[L5_SOE_SUBTABLE.top5] = all[L5_SOE_SUBTABLE.top5]
    }
  }

  return {
    wp_id: wpId,
    sheet_name: L5_DISCLOSURE_SHEET_NAME[variant],
    section_id: L5_NOTE_SECTION[variant],
    current_standard: resolveL5CurrentStandard(variant, applicableStandards),
    sub_table_data: sub,
    columns,
  }
}

export interface L6SyncSnapshot {
  variant: L5DisclosureVariant
  rows: readonly L6SpecialRow[]
  /** 专项应付款来源 / 用途 / 使用限制说明（源模板要求） */
  narrative?: string
}

/**
 * L6 载荷 —— 只推「专项应付款」表（在 L5 的章节里）。
 *
 * sheet_name 用 **L6 自己的 tab 名**（`附注披露（上市公司）信息`，括号在中间），
 * 这样附注侧「打开同步底稿」会跳到 L6 而非 L5。
 */
export function buildL6SyncPayload(
  wpId: string,
  snapshot: L6SyncSnapshot,
  applicableStandards?: readonly string[] | null,
): L5SyncPayload | null {
  const { variant, rows } = snapshot
  if (!isL5DisclosureApplicable(variant, applicableStandards)) return null

  const tableName = variant === 'listed'
    ? L6_LISTED_SUBTABLE.special
    : L6_SOE_SUBTABLE.special

  const sub: Record<string, unknown> = {
    [tableName]: buildL6SpecialRows(rows, variant),
  }
  if (snapshot.narrative?.trim()) {
    sub._note_texts = [{
      section: `l6-${variant}-special-payable`,
      title: '专项应付款说明',
      text: snapshot.narrative.trim(),
    }] as unknown as Record<string, unknown>[]
  }

  return {
    wp_id: wpId,
    sheet_name: L6_DISCLOSURE_SHEET_NAME[variant],
    section_id: L5_NOTE_SECTION[variant],
    current_standard: resolveL5CurrentStandard(variant, applicableStandards),
    sub_table_data: sub as Record<string, Record<string, unknown>[]>,
    columns: l6ColumnsFor(variant),
  }
}

/** 八、47 一年内到期的长期应付款（仅国企） */
export function buildL5Within1ySyncPayload(
  wpId: string,
  rows: readonly L5TwoPeriodRow[],
  applicableStandards?: readonly string[] | null,
): L5SyncPayload | null {
  if (!isL5DisclosureApplicable('soe', applicableStandards)) return null
  const data = rows.filter((r) => String(r.label ?? '').trim() && !isTotalLabel(r.label))
  const out: Record<string, unknown>[] = data.map((r) => ({
    label: String(r.label).trim(),
    end_amount: num(r.endAmount),
    prior_amount: num(r.priorAmount),
  }))
  out.push({
    label: L5_TOTAL_LABEL,
    end_amount: data.reduce((s, r) => s + num(r.endAmount), 0),
    prior_amount: data.reduce((s, r) => s + num(r.priorAmount), 0),
    is_total: true,
  })
  return {
    wp_id: wpId,
    sheet_name: L5_DISCLOSURE_SHEET_NAME.soe,
    section_id: L5_WITHIN1Y_NOTE_SECTION.soe,
    current_standard: resolveL5CurrentStandard('soe', applicableStandards),
    sub_table_data: { [L5_WITHIN1Y_SUBTABLE.main]: out },
    columns: l5Within1yColumns(),
  }
}
