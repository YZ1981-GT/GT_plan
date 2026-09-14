/**
 * K4 其他流动负债 披露 ↔ 附注章节映射与 sync payload 构建
 *
 * 权威来源：note_template_variant_matrix.json qi_ta_liu_dong_fu_zhai
 *   listed: 五、44 / soe: 八、48 ／ account_code: 2245
 *
 * 列头口径实证见 spec `disclosure-columns-coverage-rollout`
 * design §批 2 列头清查 §2（上市）/ §3（国企）：
 *   · 3 张表在源模板中**全是单行表头**（表头行零跨列合并）→ 标签列一律 `flat: true`、0 处 `group`。
 *     不标 `flat` 时后端 `_infer_groups_from_headers` 会对 ≥4 列共享前缀的 headers 反猜父表头
 *     （债券续表 8 列首当其冲）。
 *   · label 逐字取自附注模版（`上市报表附注.md` L4593/L4614/L4623、`国企报表附注.md` L3665）
 *     + `note_template_{listed,soe}.json` 五、44 / 八、48 的 `tables[].name` / `headers[]`，
 *     并有校验预设 F44-1/2/3 背书（只有 2 个金额列 + 合计行，无第 3 数值列）。
 *   · 与源 xlsx 冲突处按「附注是交付物」以附注模版为准：
 *     上市 `期末数`/`上年年末数` → `期末余额`/`上年年末余额`；续表 `上年年末数` → `期初余额`。
 *   · 底稿 UI 的「形成原因/备注」「增减额」是审计列，附注无落点 → 不推（投影成附注形状）。
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type K4DisclosureVariant = 'listed' | 'soe'

export const K4_NOTE_SECTION = {
  listed: '五、44',
  soe: '八、48',
} as const satisfies Record<K4DisclosureVariant, string>

/**
 * 同步载荷 `sheet_name` = 源 xlsx 真实中文 tab 名（逐字，实测 `wb.sheetnames`）。
 * 两版均为全角括号；合成标识（`K4-note-listed`）会让附注「打开同步底稿」匹配不上。
 */
export const K4_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<K4DisclosureVariant, string>

/** 附注子表名，逐字 = `note_template_*.json` 五、44 / 八、48 的 `tables[].name` */
export const K4_SUBTABLE = {
  /** 两版共有（五、44 T0 / 八、48 T0） */
  summary: '其他流动负债',
  /** 上市 五、44 T1（条件表：有债券明细行才推） */
  bond: '短期应付债券',
  /**
   * 上市 五、44 T2（条件表）。模板原 name 是表头首格泄漏值 `债券名称`，
   * 已由 `fix_note_k_liability_structure.py` 正名为源 xlsx A24 的「短期应付债券（续）」。
   */
  bondCont: '短期应付债券（续）',
} as const

/**
 * 模板改名前的旧表名（表头首格泄漏）。同步时上报 `_removed_table_keys`，
 * 清理既有项目 `sub_table_data` 里的残留孤儿键。
 */
export const K4_LEGACY_OBSOLETE_TABLES: readonly string[] = ['债券名称']

// ─── 列定义 ──────────────────────────────────────────────────────────────────

/** 汇总表列头（项目 / 期末余额 / 上年年末余额|期初余额） */
function buildSummaryColumns(variant: K4DisclosureVariant): ColumnDef[] {
  return [
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'end_amount', label: '期末余额', format: 'amount' },
    { key: 'prior_amount', label: variant === 'listed' ? '上年年末余额' : '期初余额', format: 'amount' },
  ]
}

/** 上市 短期应付债券明细（源 A19:F19 单行 6 列 / 附注模版 L4614） */
function buildBondColumns(): ColumnDef[] {
  return [
    { key: 'label', label: '债券名称', is_label: true, flat: true },
    { key: 'face_value', label: '面值', format: 'amount' },
    { key: 'coupon_rate', label: '票面利率', format: 'percent' },
    { key: 'issue_date', label: '发行日期', format: 'text' },
    { key: 'term', label: '债券期限', format: 'text' },
    { key: 'issue_amount', label: '发行金额', format: 'amount' },
  ]
}

/** 上市 短期应付债券（续）（源 A25:H25 单行 8 列 / 附注模版 L4623） */
function buildBondContColumns(): ColumnDef[] {
  return [
    { key: 'label', label: '债券名称', is_label: true, flat: true },
    { key: 'begin_amount', label: '期初余额', format: 'amount' },
    { key: 'issued', label: '本期发行', format: 'amount' },
    { key: 'interest_accrued', label: '按面值计提利息', format: 'amount' },
    { key: 'premium_amort', label: '溢折价摊销', format: 'amount' },
    { key: 'repaid', label: '本期偿还', format: 'amount' },
    { key: 'end_amount', label: '期末余额', format: 'amount' },
    { key: 'defaulted', label: '是否违约', format: 'text' },
  ]
}

export interface K4ColumnsOptions {
  /** 债券明细是**条件推送**（过滤后无行则不进 `sub_table_data`）→ `columns` 必须成对 */
  includeBond?: boolean
  /** 债券续表同上 */
  includeBondCont?: boolean
}

function buildK4Columns(
  variant: K4DisclosureVariant,
  opts: K4ColumnsOptions,
): Record<string, ColumnDef[]> {
  const columns: Record<string, ColumnDef[]> = {
    [K4_SUBTABLE.summary]: buildSummaryColumns(variant),
  }
  if (variant === 'listed') {
    if (opts.includeBond) columns[K4_SUBTABLE.bond] = buildBondColumns()
    if (opts.includeBondCont) columns[K4_SUBTABLE.bondCont] = buildBondContColumns()
  }
  return columns
}

/** K4 上市（五、44）子表列头，键 = `sub_table_data` 数据键 */
export function buildK4ListedColumns(opts: K4ColumnsOptions = {}): Record<string, ColumnDef[]> {
  return buildK4Columns('listed', opts)
}

/** K4 国企（八、48）子表列头，键 = `sub_table_data` 数据键 */
export function buildK4SoeColumns(opts: K4ColumnsOptions = {}): Record<string, ColumnDef[]> {
  return buildK4Columns('soe', opts)
}

// ─── Payload 构建 ─────────────────────────────────────────────────────────────

export interface K4DisclosureRow {
  project: string
  endAmount: number
  priorAmount: number
}

/** 上市 (二) 短期应付债券明细行（底稿 `BondRow`） */
export interface K4BondRow {
  name: string
  faceValue?: number
  couponRate?: number
  issueDate?: string
  term?: string
  issueAmount?: number
}

/** 上市 (三) 债券续表行（底稿 `BondContRow`；期末余额为底稿公式列，由调用方或此处推算） */
export interface K4BondContRow {
  name: string
  beginBalance?: number
  issued?: number
  interestAccrued?: number
  premiumAmort?: number
  repaid?: number
  defaulted?: string
}

export interface K4SyncPayloadExtras {
  bondRows?: readonly K4BondRow[]
  bondContRows?: readonly K4BondContRow[]
}

export interface K4SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

function resolveCurrentStandard(variant: K4DisclosureVariant): string {
  return variant === 'listed' ? 'listed_standalone' : 'soe_standalone'
}

function num(v: number | undefined | null): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0
}

export function buildK4SyncPayload(
  variant: K4DisclosureVariant,
  wpId: string,
  rows: readonly K4DisclosureRow[],
  narrativeText: string,
  extras: K4SyncPayloadExtras = {},
): K4SyncPayload {
  const tableRows = [
    ...rows.map(r => ({
      label: r.project || '',
      end_amount: num(r.endAmount),
      prior_amount: num(r.priorAmount),
    })),
    {
      label: '合计',
      end_amount: rows.reduce((s, r) => s + num(r.endAmount), 0),
      prior_amount: rows.reduce((s, r) => s + num(r.priorAmount), 0),
      is_total: true,
    },
  ]

  const sub: Record<string, unknown> = {}
  sub[K4_SUBTABLE.summary] = tableRows

  // 条件表：过滤后有行才进 sub_table_data（columns 走同一判据，保持成对）
  const bondRows = variant === 'listed'
    ? (extras.bondRows ?? []).filter(r => (r.name || '').trim() || num(r.issueAmount) || num(r.faceValue))
    : []
  const bondContRows = variant === 'listed'
    ? (extras.bondContRows ?? []).filter(r => (r.name || '').trim() || num(r.beginBalance) || num(r.issued))
    : []

  if (bondRows.length > 0) {
    sub[K4_SUBTABLE.bond] = bondRows.map(r => ({
      label: r.name || '',
      face_value: num(r.faceValue),
      coupon_rate: num(r.couponRate),
      issue_date: r.issueDate || '',
      term: r.term || '',
      issue_amount: num(r.issueAmount),
    }))
  }
  if (bondContRows.length > 0) {
    sub[K4_SUBTABLE.bondCont] = bondContRows.map(r => ({
      label: r.name || '',
      begin_amount: num(r.beginBalance),
      issued: num(r.issued),
      interest_accrued: num(r.interestAccrued),
      premium_amort: num(r.premiumAmort),
      repaid: num(r.repaid),
      // 底稿公式列：期初 + 本期发行 + 计提利息 + 溢折价摊销 − 本期偿还
      end_amount: num(r.beginBalance) + num(r.issued) + num(r.interestAccrued)
        + num(r.premiumAmort) - num(r.repaid),
      defaulted: r.defaulted || '',
    }))
  }

  const columnsOpts: K4ColumnsOptions = {
    includeBond: bondRows.length > 0,
    includeBondCont: bondContRows.length > 0,
  }
  const columns = variant === 'listed'
    ? buildK4ListedColumns(columnsOpts)
    : buildK4SoeColumns(columnsOpts)

  // 叙述正文必须挂在 sub_table_data 内：后端 `_extract_note_texts(sub_table_data)`
  // 只认这里；挂 payload 顶层会被请求体静默丢弃，且 update 分支会把 text_content 置 None。
  if (narrativeText.trim()) {
    sub._note_texts = [{
      section: 'note-other-current-liability',
      title: '其他流动负债说明',
      text: narrativeText.trim(),
    }]
  }

  // 模板改名后的旧表名清理（本次推送的键不进 removed，后端亦会跳过）
  if (variant === 'listed') {
    const pushed = new Set(Object.keys(sub))
    const removed = K4_LEGACY_OBSOLETE_TABLES.filter(n => !pushed.has(n))
    if (removed.length > 0) sub._removed_table_keys = removed
  }

  return {
    wp_id: wpId,
    sheet_name: K4_DISCLOSURE_SHEET_NAME[variant],
    section_id: K4_NOTE_SECTION[variant],
    current_standard: resolveCurrentStandard(variant),
    sub_table_data: sub,
    columns,
  }
}
