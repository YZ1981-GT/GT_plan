/**
 * K6 持有待售资产 披露 ↔ 附注章节映射与 sync payload 构建
 *
 * 权威来源：note_template_variant_matrix.json
 *   listed: `chi_you_dai_shou_zi_chan_he_chi_you_dai_sho` = 五、11
 *   soe:    `chi_you_dai_shou_zi_chan`                    = 八、12
 *   account_code: 1481
 *
 * 列头口径实证见 spec `disclosure-columns-coverage-rollout`
 * design §批 2 列头清查 §6（上市）/ §7（国企）：
 *   · 🔴 本批**唯一两行表头**：源模板表头行有跨列合并
 *     上市 `A6:A7` + `B6:D6`（期末余额）+ `E6:G6`（上年年末余额）；
 *     国企 `A9:A10` + `B9:D9`（期末数）+ `E9:G9`（期初数）。
 *     → 声明 `group`（父表头）+ `label`（子列名），**不标 `flat`**。
 *     产出 `_column_groups = [{group,start:1,span:3},{group,start:4,span:3}]`。
 *   · **父表头两版不同**（上市「余额」/ 国企「数」）→ 必须按变体给串，禁抽共享常量。
 *   · 同名子列（`账面余额`/`减值准备`/`账面价值` 各出现两次）不去重、不加期别前缀
 *     （模板即如此，靠 `end_*`/`prior_*` 两组 key 区分；加前缀＝压平＋杜撰）。
 *   · 校验预设 F11-1/1a（报表 = 合计行期末/期初账面价值）、F11-4（账面余额 − 减值准备 =
 *     账面价值，期末/期初各独立）→ 三子列必须齐备，不能只推 2 列。
 *   · ⚠️ 上年年末（期初）三子列**只有 `openingBalance` 一个录入来源**：
 *     `prior_book = openingBalance`；`prior_gross` / `prior_impairment` 无来源 →
 *     推 `null`（决策 A1：禁凭空造数；空值可见 = 提示审计师补录，比砍列保守）。
 *     遗留登记「底稿缺上年年末账面余额/减值准备录入列」，属底稿改版另立 spec。
 *   · ⚠️ 上市「持有待售负债」表**不推**（决策 B1）：`note_template_listed.json` 五、11 的
 *     `tables[]` name↔rows 整体错位一位，按 `tables[1].name`（`持有待售资产减值准备`）
 *     推负债数据会把负债塞进减值准备表。国企「持有待售负债」是独立章节 八、43，
 *     需章节路由改造（另立 spec）。
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type K6DisclosureVariant = 'listed' | 'soe'

export const K6_NOTE_SECTION = {
  listed: '五、11',
  soe: '八、12',
} as const satisfies Record<K6DisclosureVariant, string>

/**
 * 同步载荷 `sheet_name` = 源 xlsx 真实中文 tab 名（逐字，实测 `wb.sheetnames`）。
 * ⚠️ 国企版是**前半角后全角**括号 `(国企）`，源模板即如此，不要"修正"。
 */
export const K6_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息(国企）',
} as const satisfies Record<K6DisclosureVariant, string>

/** 附注子表名，逐字 = `note_template_*.json` 五、11 `tables[0].name` / 八、12 `tables[0].name` */
export const K6_SUBTABLE = {
  listed: '持有待售资产和持有待售负债',
  soe: '持有待售资产',
} as const satisfies Record<K6DisclosureVariant, string>

/** 两级表头的父表头串（**per-variant，禁共享常量**） */
const K6_COLUMN_GROUPS = {
  listed: { end: '期末余额', prior: '上年年末余额' },
  soe: { end: '期末数', prior: '期初数' },
} as const satisfies Record<K6DisclosureVariant, { end: string; prior: string }>

// ─── 列定义 ──────────────────────────────────────────────────────────────────

/** 持有待售资产情况表列头（7 列 / 2 个 group，两行表头 → 不标 `flat`） */
function buildHeldForSaleColumns(variant: K6DisclosureVariant): ColumnDef[] {
  const g = K6_COLUMN_GROUPS[variant]
  return [
    { key: 'label', label: '项目', is_label: true },
    { key: 'end_gross', label: '账面余额', group: g.end, format: 'amount' },
    { key: 'end_impairment', label: '减值准备', group: g.end, format: 'amount' },
    { key: 'end_book', label: '账面价值', group: g.end, format: 'amount' },
    { key: 'prior_gross', label: '账面余额', group: g.prior, format: 'amount' },
    { key: 'prior_impairment', label: '减值准备', group: g.prior, format: 'amount' },
    { key: 'prior_book', label: '账面价值', group: g.prior, format: 'amount' },
  ]
}

function buildK6Columns(variant: K6DisclosureVariant): Record<string, ColumnDef[]> {
  return { [K6_SUBTABLE[variant]]: buildHeldForSaleColumns(variant) }
}

/** K6 上市（五、11）子表列头，键 = `sub_table_data` 数据键 */
export function buildK6ListedColumns(): Record<string, ColumnDef[]> {
  return buildK6Columns('listed')
}

/** K6 国企（八、12）子表列头，键 = `sub_table_data` 数据键 */
export function buildK6SoeColumns(): Record<string, ColumnDef[]> {
  return buildK6Columns('soe')
}

// ─── Payload 构建 ─────────────────────────────────────────────────────────────

export interface K6DisclosureRow {
  /** 资产类别（底稿 `assetTable[].category` / `assetSummary[].category`） */
  project: string
  /**
   * 期末账面价值。
   * 上市底稿 = `bookValue`（原值 − 折旧 − 减值）；
   * 国企底稿取 `bookValue`（与 `impairment` 同源，满足 F11-4 勾稽），不取 `closingBalance`。
   */
  bookValue: number
  /** 期末减值准备 */
  impairment: number
  /** 期初/上年年末账面价值（底稿唯一的上期录入项） */
  openingBalance: number
}

export interface K6SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

function resolveCurrentStandard(variant: K6DisclosureVariant): string {
  return variant === 'listed' ? 'listed_standalone' : 'soe_standalone'
}

function num(v: number | undefined | null): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0
}

export function buildK6SyncPayload(
  variant: K6DisclosureVariant,
  wpId: string,
  rows: readonly K6DisclosureRow[],
  narrativeText: string,
): K6SyncPayload {
  // values 与 buildHeldForSaleColumns() 的 6 个非标签列同序：
  //   期末[账面余额, 减值准备, 账面价值] / 上期[账面余额, 减值准备, 账面价值]
  // 上期账面余额/减值准备无录入来源 → null（禁造数），两版列集一致。
  const dataRows = rows.map(r => ({
    label: r.project || '',
    values: [
      num(r.bookValue) + num(r.impairment), // end_gross（F11-4 反解：账面价值 + 减值准备）
      num(r.impairment),
      num(r.bookValue),
      null,
      null,
      num(r.openingBalance),
    ] as Array<number | null>,
  }))

  const tableRows = [
    ...dataRows,
    {
      label: '合计',
      values: [
        rows.reduce((s, r) => s + num(r.bookValue) + num(r.impairment), 0),
        rows.reduce((s, r) => s + num(r.impairment), 0),
        rows.reduce((s, r) => s + num(r.bookValue), 0),
        null,
        null,
        rows.reduce((s, r) => s + num(r.openingBalance), 0),
      ] as Array<number | null>,
      is_total: true,
    },
  ]

  const sub: Record<string, unknown> = {}
  sub[K6_SUBTABLE[variant]] = tableRows

  // 叙述正文必须挂 sub_table_data 内（后端 `_extract_note_texts(sub_table_data)` 只认这里）
  if (narrativeText.trim()) {
    sub._note_texts = [{
      section: 'note-held-for-sale',
      title: '持有待售资产说明',
      text: narrativeText.trim(),
    }]
  }

  const columns = variant === 'listed' ? buildK6ListedColumns() : buildK6SoeColumns()

  return {
    wp_id: wpId,
    sheet_name: K6_DISCLOSURE_SHEET_NAME[variant],
    section_id: K6_NOTE_SECTION[variant],
    current_standard: resolveCurrentStandard(variant),
    sub_table_data: sub,
    columns,
  }
}
