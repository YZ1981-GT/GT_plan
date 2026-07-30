/**
 * G5 长期应收款披露 → `disclosure_notes` 同步载荷
 *
 * 列结构逐字对齐 `note_template_listed.json §五、16` / `note_template_soe.json §八、17`
 * （由 `backend/scripts/fix/fix_note_g_cycle_structure.py` 按权威模板
 * `backend/wp_templates/G/G5 长期应收款.xlsx` 重建）。
 *
 * 🔴 三处必须知道的口径：
 * 1. **「坏账准备计提情况」源模版是三级表头**（期末/期初 > 账面余额·坏账准备·账面价值 >
 *    金额·比例），平台只支持两级 → 父表头取期间，子列名用限定名（`账面余额-金额`）。
 *    改动列名必须同步改模板（`fix_note_g_cycle_structure.py`），否则孤儿列。
 * 2. **组合计提表是动态多表**：每个组合一张，表名 `组合计提项目：{组合名}`。
 *    组合改名 / 删除会在附注侧留下孤儿表 → 用 `disclosureSyncedTables` 的
 *    `buildRemovedTableKeys` 上报 `_removed_table_keys`。
 * 3. **国企侧不推坏账准备系列表**：国企附注模版对「坏账准备计提情况」只有交叉引用、无表。
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.2
 */
import type { ColumnDef } from './disclosureColumnDefs'
import { defineColumns } from './disclosureColumnDefs'
import {
  G5_DISCLOSURE_SHEET_NAME,
  G5_LISTED_SUBTABLE,
  G5_NOTE_SECTION,
  G5_PORTFOLIO_PREFIX,
  G5_SOE_SUBTABLE,
  isG5DisclosureApplicable,
  resolveG5CurrentStandard,
  type G5DisclosureVariant,
} from './g5NoteSectionMap'

const AMOUNT = 'amount' as const
const PERCENT = 'percent' as const

export const G5_TOTAL_LABEL = '合计'
export const G5_SUBTOTAL_LABEL = '小计'

// ─────────────────────────── 列定义 ───────────────────────────

/** 按性质披露：账面余额/坏账准备/账面价值 × 两期 + 折现率区间（独立列，跨两行） */
function natureColumns(variant: G5DisclosureVariant): ColumnDef[] {
  const endGroup = variant === 'listed' ? '期末余额' : '期末余额'
  const priorGroup = variant === 'listed' ? '上年年末余额' : '期初余额'
  const rateLabel = variant === 'listed' ? '折现率区间' : '期末折现率区间'
  return defineColumns([
    { key: 'label', label: '项目', is_label: true },
    { key: 'end_gross', label: '账面余额', group: endGroup, format: AMOUNT, align: 'right' },
    { key: 'end_provision', label: '坏账准备', group: endGroup, format: AMOUNT, align: 'right' },
    { key: 'end_net', label: '账面价值', group: endGroup, format: AMOUNT, align: 'right' },
    { key: 'prior_gross', label: '账面余额', group: priorGroup, format: AMOUNT, align: 'right' },
    { key: 'prior_provision', label: '坏账准备', group: priorGroup, format: AMOUNT, align: 'right' },
    { key: 'prior_net', label: '账面价值', group: priorGroup, format: AMOUNT, align: 'right' },
    { key: 'discount_rate_range', label: rateLabel },
  ])
}

/** 坏账准备计提情况：三级 → 两级投影（父取期间，子用限定名） */
function provisionColumns(): ColumnDef[] {
  const leaves: Array<[string, string, typeof AMOUNT | typeof PERCENT]> = [
    ['gross_amount', '账面余额-金额', AMOUNT],
    ['gross_pct', '账面余额-比例(%)', PERCENT],
    ['provision_amount', '坏账准备-金额', AMOUNT],
    ['provision_rate', '坏账准备-预期信用损失率(%)', PERCENT],
    ['net', '账面价值', AMOUNT],
  ]
  const defs: Array<Partial<ColumnDef> & { key: string; label: string }> = [
    { key: 'label', label: '类别', is_label: true },
  ]
  for (const [prefix, group] of [['end', '期末余额'], ['prior', '上年年末余额']] as const) {
    for (const [key, label, fmt] of leaves) {
      defs.push({ key: `${prefix}_${key}`, label, group, format: fmt, align: 'right' })
    }
  }
  return defineColumns(defs)
}

/** 按单项计提坏账准备（期末 / 上年年末各一张） */
function individualColumns(group: string, prefix: 'end' | 'prior'): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '名称', is_label: true },
    { key: `${prefix}_gross`, label: '账面余额', group, format: AMOUNT, align: 'right' },
    { key: `${prefix}_provision`, label: '坏账准备', group, format: AMOUNT, align: 'right' },
    { key: `${prefix}_rate`, label: '预期信用损失率(%)', group, format: PERCENT, align: 'right' },
    { key: `${prefix}_reason`, label: '计提理由', group },
  ])
}

/** 组合计提项目（按账龄段） */
function portfolioColumns(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '账龄', is_label: true },
    { key: 'end_gross', label: '长期应收款', group: '期末余额', format: AMOUNT, align: 'right' },
    { key: 'end_provision', label: '坏账准备', group: '期末余额', format: AMOUNT, align: 'right' },
    { key: 'end_rate', label: '预期信用损失率(%)', group: '期末余额', format: PERCENT, align: 'right' },
    { key: 'prior_gross', label: '长期应收款', group: '上年年末余额', format: AMOUNT, align: 'right' },
    { key: 'prior_provision', label: '坏账准备', group: '上年年末余额', format: AMOUNT, align: 'right' },
    { key: 'prior_rate', label: '预期信用损失率(%)', group: '上年年末余额', format: PERCENT, align: 'right' },
  ])
}

function flat(defs: Array<Partial<ColumnDef> & { key: string; label: string }>): ColumnDef[] {
  return defineColumns(defs.map((d, i) => (i === 0 ? { ...d, is_label: true, flat: true } : d)))
}

const MOVEMENT_COLUMNS = flat([
  { key: 'label', label: '项目' },
  { key: 'amount', label: '坏账准备金额', format: AMOUNT, align: 'right' },
])

const WRITEOFF_COLUMNS = flat([
  { key: 'label', label: '项目' },
  { key: 'writeoff_amount', label: '核销金额', format: AMOUNT, align: 'right' },
])

const WRITEOFF_DETAIL_COLUMNS = flat([
  { key: 'label', label: '项目' },
  { key: 'nature', label: '长期应收款性质' },
  { key: 'amount', label: '核销金额', format: AMOUNT, align: 'right' },
  { key: 'reason', label: '核销原因' },
  { key: 'procedure', label: '履行的核销程序' },
  { key: 'related_party', label: '是否由关联交易产生' },
])

const DERECOG_COLUMNS = flat([
  { key: 'label', label: '项目' },
  { key: 'transfer_method', label: '转移方式' },
  { key: 'derecognized_amount', label: '终止确认金额', format: AMOUNT, align: 'right' },
  { key: 'gain_or_loss', label: '与终止确认相关的利得或损失', format: AMOUNT, align: 'right' },
])

const CONTINUING_COLUMNS = flat([
  { key: 'label', label: '项目' },
  { key: 'end_amount', label: '期末数', format: AMOUNT, align: 'right' },
])

/** 上市列定义（组合表按实际组合名逐张给同一套列） */
export function buildG5ListedColumns(
  portfolioNames: readonly string[] = [],
): Record<string, ColumnDef[]> {
  const out: Record<string, ColumnDef[]> = {
    [G5_LISTED_SUBTABLE.nature]: natureColumns('listed'),
    [G5_LISTED_SUBTABLE.provision]: provisionColumns(),
    [G5_LISTED_SUBTABLE.individualEnd]: individualColumns('期末余额', 'end'),
    [G5_LISTED_SUBTABLE.individualPrior]: individualColumns('上年年末余额', 'prior'),
    [G5_LISTED_SUBTABLE.movement]: MOVEMENT_COLUMNS,
    [G5_LISTED_SUBTABLE.writeoff]: WRITEOFF_COLUMNS,
    [G5_LISTED_SUBTABLE.writeoffDetail]: WRITEOFF_DETAIL_COLUMNS,
  }
  const names = portfolioNames.length ? portfolioNames : [G5_LISTED_SUBTABLE.portfolioSeed]
  for (const name of names) out[name] = portfolioColumns()
  return out
}

export function buildG5SoeColumns(): Record<string, ColumnDef[]> {
  return {
    [G5_SOE_SUBTABLE.nature]: natureColumns('soe'),
    [G5_SOE_SUBTABLE.derecognition]: DERECOG_COLUMNS,
    [G5_SOE_SUBTABLE.continuing]: CONTINUING_COLUMNS,
  }
}

/** 组合表名：空名回退到骨架名，避免产出 `组合计提项目：` 空后缀键 */
export function g5PortfolioTableName(name: string): string {
  const trimmed = String(name ?? '').trim()
  return trimmed ? `${G5_PORTFOLIO_PREFIX}${trimmed}` : G5_LISTED_SUBTABLE.portfolioSeed
}

// ─────────────────────────── 行构建 ───────────────────────────

export interface G5PeriodAmtLike {
  balance?: number
  provision?: number
}

export interface G5NatureRowLike {
  label?: string
  rowKey?: string
  kind?: string
  end?: G5PeriodAmtLike
  prior?: G5PeriodAmtLike
  endDiscountRate?: string
  priorDiscountRate?: string
}

export interface G5MethodRowLike {
  label?: string
  rowKey?: string
  kind?: string
  end?: G5PeriodAmtLike
  prior?: G5PeriodAmtLike
}

export interface G5IndividualRowLike {
  name?: string
  endBalance?: number
  endProvision?: number
  endReason?: string
  priorBalance?: number
  priorProvision?: number
  priorReason?: string
}

export interface G5AgingRowLike {
  label?: string
  kind?: string
  endBalance?: number
  endProvision?: number
  priorBalance?: number
  priorProvision?: number
}

export interface G5PortfolioLike {
  name?: string
  agingRows?: readonly G5AgingRowLike[]
}

export interface G5MovementRowLike {
  label?: string
  rowKey?: string
  provision?: number
}

export interface G5WriteoffRowLike {
  name?: string
  amount?: number
  reason?: string
  relatedParty?: boolean
}

export interface G5DerecogRowLike {
  item?: string
  transferMethod?: string
  amount?: number
  gainLoss?: number
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function txt(v: unknown): string {
  return String(v ?? '').trim()
}

/** 比率：分母为 0 时返回 null（不写 0，避免"0% 覆盖率"误读） */
function ratio(part: number, whole: number): number | null {
  if (!Number.isFinite(whole) || Math.abs(whole) < 1e-9) return null
  return Number(((part / whole) * 100).toFixed(4))
}

function rowTypeOf(kind: string | undefined): string {
  if (kind === 'subtotal') return 'subtotal'
  if (kind === 'total') return 'total'
  return 'data'
}

export function buildG5NatureRows(
  variant: G5DisclosureVariant,
  rows: readonly G5NatureRowLike[],
): Record<string, unknown>[] {
  const rateLabelKey = 'discount_rate_range'
  return rows.map((r) => {
    const endGross = num(r.end?.balance)
    const endProv = num(r.end?.provision)
    const priorGross = num(r.prior?.balance)
    const priorProv = num(r.prior?.provision)
    const kind = String(r.kind ?? '')
    const isTotal = kind === 'total' || kind === 'subtotal'
    return {
      label: txt(r.label),
      row_key: txt(r.rowKey) || undefined,
      end_gross: endGross,
      end_provision: endProv,
      end_net: Number((endGross - endProv).toFixed(2)),
      prior_gross: priorGross,
      prior_provision: priorProv,
      prior_net: Number((priorGross - priorProv).toFixed(2)),
      [rateLabelKey]: txt(r.endDiscountRate) || txt(r.priorDiscountRate),
      ...(isTotal ? { is_total: true } : {}),
      row_type: rowTypeOf(kind),
    }
  })
}

/** 坏账准备计提情况：比例以合计行账面余额为分母（与源模版口径一致） */
export function buildG5ProvisionRows(
  rows: readonly G5MethodRowLike[],
): Record<string, unknown>[] {
  const totalEnd = rows
    .filter((r) => String(r.kind ?? '') !== 'total')
    .reduce((s, r) => s + num(r.end?.balance), 0)
  const totalPrior = rows
    .filter((r) => String(r.kind ?? '') !== 'total')
    .reduce((s, r) => s + num(r.prior?.balance), 0)
  return rows.map((r) => {
    const eg = num(r.end?.balance)
    const ep = num(r.end?.provision)
    const pg = num(r.prior?.balance)
    const pp = num(r.prior?.provision)
    const kind = String(r.kind ?? '')
    return {
      label: txt(r.label),
      row_key: txt(r.rowKey) || undefined,
      end_gross_amount: eg,
      end_gross_pct: ratio(eg, totalEnd),
      end_provision_amount: ep,
      end_provision_rate: ratio(ep, eg),
      end_net: Number((eg - ep).toFixed(2)),
      prior_gross_amount: pg,
      prior_gross_pct: ratio(pg, totalPrior),
      prior_provision_amount: pp,
      prior_provision_rate: ratio(pp, pg),
      prior_net: Number((pg - pp).toFixed(2)),
      ...(kind === 'total' ? { is_total: true } : {}),
      row_type: rowTypeOf(kind),
    }
  })
}

export function buildG5IndividualRows(
  rows: readonly G5IndividualRowLike[],
  period: 'end' | 'prior',
): Record<string, unknown>[] {
  const gross = (r: G5IndividualRowLike) =>
    num(period === 'end' ? r.endBalance : r.priorBalance)
  const prov = (r: G5IndividualRowLike) =>
    num(period === 'end' ? r.endProvision : r.priorProvision)
  const reason = (r: G5IndividualRowLike) =>
    txt(period === 'end' ? r.endReason : r.priorReason)

  const data = rows
    .filter((r) => txt(r.name) || gross(r) !== 0 || prov(r) !== 0)
    .map((r) => ({
      label: txt(r.name),
      [`${period}_gross`]: gross(r),
      [`${period}_provision`]: prov(r),
      [`${period}_rate`]: ratio(prov(r), gross(r)),
      [`${period}_reason`]: reason(r),
      row_type: 'data',
    }))
  const sumGross = data.reduce((s, r) => s + num(r[`${period}_gross`]), 0)
  const sumProv = data.reduce((s, r) => s + num(r[`${period}_provision`]), 0)
  return [
    ...data,
    {
      label: G5_TOTAL_LABEL,
      [`${period}_gross`]: sumGross,
      [`${period}_provision`]: sumProv,
      [`${period}_rate`]: ratio(sumProv, sumGross),
      // 源模版合计行「计提理由」列示为「/」（不加总）
      [`${period}_reason`]: '/',
      is_total: true,
      row_type: 'total',
    },
  ]
}

export function buildG5PortfolioRows(
  agingRows: readonly G5AgingRowLike[],
): Record<string, unknown>[] {
  const bands = agingRows.filter((r) => String(r.kind ?? 'band') !== 'total')
  const data = bands.map((r) => ({
    label: txt(r.label),
    end_gross: num(r.endBalance),
    end_provision: num(r.endProvision),
    end_rate: ratio(num(r.endProvision), num(r.endBalance)),
    prior_gross: num(r.priorBalance),
    prior_provision: num(r.priorProvision),
    prior_rate: ratio(num(r.priorProvision), num(r.priorBalance)),
    row_type: 'data',
  }))
  const sum = (k: 'end_gross' | 'end_provision' | 'prior_gross' | 'prior_provision') =>
    data.reduce((s, r) => s + num(r[k]), 0)
  const eg = sum('end_gross')
  const ep = sum('end_provision')
  const pg = sum('prior_gross')
  const pp = sum('prior_provision')
  return [
    ...data,
    {
      label: G5_TOTAL_LABEL,
      end_gross: eg,
      end_provision: ep,
      end_rate: ratio(ep, eg),
      prior_gross: pg,
      prior_provision: pp,
      prior_rate: ratio(pp, pg),
      is_total: true,
      row_type: 'total',
    },
  ]
}

export function buildG5MovementRows(
  rows: readonly G5MovementRowLike[],
): Record<string, unknown>[] {
  return rows.map((r) => ({
    label: txt(r.label),
    row_key: txt(r.rowKey) || undefined,
    amount: num(r.provision),
    row_type: 'data',
  }))
}

export function buildG5WriteoffRows(
  rows: readonly G5WriteoffRowLike[],
): Record<string, unknown>[] {
  const total = rows.reduce((s, r) => s + num(r.amount), 0)
  return [
    {
      label: '实际核销的长期应收款',
      writeoff_amount: total,
      row_type: 'data',
    },
  ]
}

export function buildG5WriteoffDetailRows(
  rows: readonly G5WriteoffRowLike[],
): Record<string, unknown>[] {
  const data = rows
    .filter((r) => txt(r.name) || num(r.amount) !== 0)
    .map((r) => ({
      label: txt(r.name),
      nature: '',
      amount: num(r.amount),
      reason: txt(r.reason),
      procedure: '',
      related_party: r.relatedParty ? '是' : '否',
      row_type: 'data',
    }))
  return [
    ...data,
    {
      label: G5_TOTAL_LABEL,
      nature: '',
      amount: data.reduce((s, r) => s + num(r.amount), 0),
      reason: '',
      procedure: '',
      related_party: '',
      is_total: true,
      row_type: 'total',
    },
  ]
}

export function buildG5DerecogRows(
  rows: readonly G5DerecogRowLike[],
): Record<string, unknown>[] {
  const data = rows
    .filter((r) => txt(r.item) || num(r.amount) !== 0 || num(r.gainLoss) !== 0)
    .map((r) => ({
      label: txt(r.item),
      transfer_method: txt(r.transferMethod),
      derecognized_amount: num(r.amount),
      gain_or_loss: num(r.gainLoss),
      row_type: 'data',
    }))
  return [
    ...data,
    {
      label: G5_TOTAL_LABEL,
      transfer_method: '',
      derecognized_amount: data.reduce((s, r) => s + num(r.derecognized_amount), 0),
      // 源模版合计行「与终止确认相关的利得或损失」列示为「--」
      gain_or_loss: null,
      is_total: true,
      row_type: 'total',
    },
  ]
}

export function buildG5ContinuingRows(
  continuing: { assetEnd?: number; liabilityEnd?: number } | null | undefined,
): Record<string, unknown>[] {
  const asset = num(continuing?.assetEnd)
  const liability = num(continuing?.liabilityEnd)
  return [
    { label: '资产：', end_amount: null, row_type: 'data' },
    { label: '资产小计', end_amount: asset, is_total: true, row_type: 'subtotal' },
    { label: '负债：', end_amount: null, row_type: 'data' },
    { label: '负债小计', end_amount: liability, is_total: true, row_type: 'subtotal' },
  ]
}

// ─────────────────────────── 载荷装配 ───────────────────────────

export interface G5ListedSnapshot {
  natureRows: readonly G5NatureRowLike[]
  methodRows: readonly G5MethodRowLike[]
  individualDetails: readonly G5IndividualRowLike[]
  portfolios: readonly G5PortfolioLike[]
  movementRows: readonly G5MovementRowLike[]
  writeoffRows: readonly G5WriteoffRowLike[]
  unrealizedNote: string
  noteText: string
}

export interface G5SoeSnapshot {
  natureRows: readonly G5NatureRowLike[]
  derecogRows: readonly G5DerecogRowLike[]
  continuing: { assetEnd?: number; liabilityEnd?: number } | null | undefined
  provisionMethodNote: string
  noteText: string
}

export interface G5SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

function pushText(
  out: Array<Record<string, string>>,
  section: string,
  text: string,
): void {
  const t = txt(text)
  if (t) out.push({ section, text: t })
}

/** 组合表名清单（供孤儿清理与列定义使用；顺序 = 底稿组合顺序） */
export function g5PortfolioTableNames(
  portfolios: readonly G5PortfolioLike[],
): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const p of portfolios) {
    const name = g5PortfolioTableName(String(p.name ?? ''))
    if (seen.has(name)) continue
    seen.add(name)
    out.push(name)
  }
  return out
}

export function buildG5ListedSubTableData(
  snap: G5ListedSnapshot,
): Record<string, unknown> {
  const out: Record<string, unknown> = {
    [G5_LISTED_SUBTABLE.nature]: buildG5NatureRows('listed', snap.natureRows),
    [G5_LISTED_SUBTABLE.provision]: buildG5ProvisionRows(snap.methodRows),
    [G5_LISTED_SUBTABLE.individualEnd]: buildG5IndividualRows(snap.individualDetails, 'end'),
    [G5_LISTED_SUBTABLE.individualPrior]: buildG5IndividualRows(snap.individualDetails, 'prior'),
    [G5_LISTED_SUBTABLE.movement]: buildG5MovementRows(snap.movementRows),
    [G5_LISTED_SUBTABLE.writeoff]: buildG5WriteoffRows(snap.writeoffRows),
    [G5_LISTED_SUBTABLE.writeoffDetail]: buildG5WriteoffDetailRows(snap.writeoffRows),
  }
  for (const p of snap.portfolios) {
    out[g5PortfolioTableName(String(p.name ?? ''))] = buildG5PortfolioRows(p.agingRows ?? [])
  }
  const texts: Array<Record<string, string>> = []
  pushText(texts, 'listed-unrealized-finance-income', snap.unrealizedNote)
  pushText(texts, 'listed-disclosure-note', snap.noteText)
  if (texts.length) out._note_texts = texts
  return out
}

export function buildG5SoeSubTableData(snap: G5SoeSnapshot): Record<string, unknown> {
  const out: Record<string, unknown> = {
    [G5_SOE_SUBTABLE.nature]: buildG5NatureRows('soe', snap.natureRows),
    [G5_SOE_SUBTABLE.derecognition]: buildG5DerecogRows(snap.derecogRows),
    [G5_SOE_SUBTABLE.continuing]: buildG5ContinuingRows(snap.continuing),
  }
  const texts: Array<Record<string, string>> = []
  pushText(texts, 'soe-provision-method-note', snap.provisionMethodNote)
  pushText(texts, 'soe-disclosure-note', snap.noteText)
  if (texts.length) out._note_texts = texts
  return out
}

/** @returns null=该变体不适用 / 缺 wpId */
export function buildG5ListedSyncPayload(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: G5ListedSnapshot,
  removedTableKeys: readonly string[] = [],
): G5SyncFromWorkpaperPayload | null {
  if (!wpId || !isG5DisclosureApplicable('listed', applicableStandards)) return null
  const sub = buildG5ListedSubTableData(snap)
  if (removedTableKeys.length) sub._removed_table_keys = [...removedTableKeys]
  return {
    wp_id: wpId,
    sheet_name: G5_DISCLOSURE_SHEET_NAME.listed,
    section_id: G5_NOTE_SECTION.listed,
    current_standard: resolveG5CurrentStandard('listed', applicableStandards),
    sub_table_data: sub,
    columns: buildG5ListedColumns(g5PortfolioTableNames(snap.portfolios)),
  }
}

export function buildG5SoeSyncPayload(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: G5SoeSnapshot,
): G5SyncFromWorkpaperPayload | null {
  if (!wpId || !isG5DisclosureApplicable('soe', applicableStandards)) return null
  return {
    wp_id: wpId,
    sheet_name: G5_DISCLOSURE_SHEET_NAME.soe,
    section_id: G5_NOTE_SECTION.soe,
    current_standard: resolveG5CurrentStandard('soe', applicableStandards),
    sub_table_data: buildG5SoeSubTableData(snap),
    columns: buildG5SoeColumns(),
  }
}
