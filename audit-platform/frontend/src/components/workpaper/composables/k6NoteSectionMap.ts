/**
 * K6 持有待售资产和负债 披露 ↔ 附注章节映射与 sync payload 构建
 *
 * 权威来源：`note_template_variant_matrix.json` + 源 xlsx
 * `backend/wp_templates/K/K6 持有待售资产和负债.xlsx` 两个披露 sheet（openpyxl 实测）。
 *
 * 🔴 **章节结构两版不对称**（本循环最大的坑）：
 *   · 上市：`chi_you_dai_shou_zi_chan_he_chi_you_dai_sho` = **五、11 一节合并**
 *     （持有待售资产 + 持有待售负债 + 减值准备 + 非流动资产 + 处置组，共 5 表）
 *   · 国企：`chi_you_dai_shou_zi_chan` = **八、12（资产 4 表）**，
 *     `chi_you_dai_shou_fu_zhai` = **八、43（负债 1 表）** —— 拆成两个章节。
 *   → 国企侧同步必须发**两个 payload**（`sync_from_workpaper` 的定位键是
 *     `(project_id, year, note_section)`，一次只能写一节）。
 *   account_code: 1481
 *
 * 列结构（`disclosure-columns-coverage-rollout` 批 2 §6/§7 + 本 spec 批 3 复核）：
 *   · **主表两级表头**：源模板表头行有跨列合并 —— 上市 `A6:A7` + `B6:D6` + `E6:G6`；
 *     国企 `A9:A10` + `B9:D9` + `E9:G9`。声明 `group`（父表头）+ `label`（叶子列名），
 *     **不标 `flat`**；产出 `_column_groups = [{start:1,span:3},{start:4,span:3}]`。
 *   · **父表头两版不同**（上市「余额」/ 国企「数」）→ 按变体给串，禁抽共享常量。
 *   · 同名子列（`账面余额`/`减值准备`/`账面价值` 各出现两次）不去重、不加期别前缀
 *     （模板即如此，靠 `end_*`/`prior_*` 两组 key 区分；加前缀＝压平＋杜撰）。
 *   · 校验预设 F11-1/1a（报表 = 合计行期末/期初账面价值）、F11-4（账面余额 − 减值准备 =
 *     账面价值，期末/期初各独立）→ 三子列必须齐备，不能只推 2 列。
 *   · **减值准备表**「本期减少」下辖 `本期转回`/`本期出售`（源 `D32:E32` / `D22:E22` 合并）
 *     → 混合分组：其余列 rowspan=2 不给 `group`。
 *   · ⚠️ 上期（上年年末 / 期初）三子列**只有 `openingBalance` 一个录入来源**：
 *     `prior_book = openingBalance`；`prior_gross` / `prior_impairment` 无来源 →
 *     推 `null`（禁凭空造数；空值可见 = 提示审计师补录，比砍列保守）。
 *
 * 🔴 上市 `tables[1]` 曾**名（持有待售资产减值准备）与内容（持有待售负债行）整体错位一位**
 * （md 重建游标跳位），2026-07-31 已由 `fix_note_k_complex_structure.py` 正名；
 * 另外 5 张垃圾表名（`期末，持有待售资产的情况：` 段落泄漏、`子公司A`/`分公司B` 示例名、
 * `项  目` 表头首格泄漏）也已一并修正。
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type K6DisclosureVariant = 'listed' | 'soe'

export const K6_NOTE_SECTION = {
  listed: '五、11',
  soe: '八、12',
} as const satisfies Record<K6DisclosureVariant, string>

/** 国企持有待售**负债**是独立章节（上市侧合并在 五、11 内，无对应常量） */
export const K6_SOE_LIABILITY_NOTE_SECTION = '八、43'

/**
 * 同步载荷 `sheet_name` = 源 xlsx 真实中文 tab 名（逐字，实测 `wb.sheetnames`）。
 * ⚠️ 国企版是**前半角后全角**括号 `(国企）`，源模板即如此，不要"修正"。
 */
export const K6_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息(国企）',
} as const satisfies Record<K6DisclosureVariant, string>

/**
 * 主表名（按变体）—— 每个变体的 `tables[0]`。
 * 其余子表见 `K6_LISTED_SUBTABLE` / `K6_SOE_SUBTABLE` / `K6_SOE_LIABILITY_SUBTABLE`。
 */
export const K6_SUBTABLE = {
  listed: '持有待售资产和持有待售负债',
  soe: '持有待售资产',
} as const satisfies Record<K6DisclosureVariant, string>

/** 上市 §五、11 子表名，逐字 = `note_template_listed.json` `tables[].name` */
export const K6_LISTED_SUBTABLE = {
  /** 主表（表名即章节标题，md 重建产物，既有映射真源，不改名） */
  main: K6_SUBTABLE.listed,
  liability: '持有待售负债',
  impairment: '持有待售资产减值准备',
  nonCurrent: '持有待售的非流动资产',
  disposalGroup: '持有待售的处置组',
} as const

/** 国企 §八、12（资产）子表名 */
export const K6_SOE_SUBTABLE = {
  main: K6_SUBTABLE.soe,
  impairment: '持有待售资产减值准备',
  nonCurrent: '持有待售非流动资产',
  disposalGroup: '持有待售处置组中的资产',
} as const

/** 国企 §八、43（负债）子表名 */
export const K6_SOE_LIABILITY_SUBTABLE = {
  liability: '持有待售负债',
} as const

/**
 * 旧表名（md 重建的垃圾名 / 错位名）—— 载荷带 `_removed_table_keys` 清理，
 * 否则改名后既有项目的附注里会同时存在新旧两套表（旧表还带着上次推送的数据）。
 */
export const K6_LEGACY_OBSOLETE_TABLES = {
  listed: ['期末，持有待售资产的情况：', '子公司A', '分公司B', '项  目'],
  soe: ['持有待售资产（表4）'],
} as const

/** 两级表头的父表头串（**per-variant，禁共享常量**） */
const K6_COLUMN_GROUPS = {
  listed: { end: '期末余额', prior: '上年年末余额' },
  soe: { end: '期末数', prior: '期初数' },
} as const satisfies Record<K6DisclosureVariant, { end: string; prior: string }>

/** 「预计出售费用」（上市）vs「预计处置费用」（国企）—— 源模板用语不同，按变体取 */
const K6_DISPOSAL_FEE_LABEL = {
  listed: '预计出售费用',
  soe: '预计处置费用',
} as const satisfies Record<K6DisclosureVariant, string>

// ─── 列定义 ──────────────────────────────────────────────────────────────────

/** 主表列头（7 列 / 2 个 group，两行表头 → 不标 `flat`） */
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

/**
 * 减值准备变动表列头（6 列，混合分组）。
 * 源 xlsx 上市 `A32:F42` / 国企 `A22:F32`：`本期减少` 下辖 `本期转回` / `本期出售`。
 */
function buildImpairmentColumns(variant: K6DisclosureVariant): ColumnDef[] {
  return [
    { key: 'label', label: '项目', is_label: true },
    {
      key: 'prior_amount',
      label: variant === 'listed' ? '上年年末数' : '期初数',
      format: 'amount',
    },
    { key: 'increase', label: '本期增加', format: 'amount' },
    { key: 'reverse', label: '本期转回', group: '本期减少', format: 'amount' },
    { key: 'disposal', label: '本期出售', group: '本期减少', format: 'amount' },
    { key: 'end_amount', label: '期末数', format: 'amount' },
  ]
}

/** 持有待售资产/负债的公允价值 5 列表（非流动资产 / 处置组 / 负债共用，单级 → 标 `flat`） */
function buildFairValueColumns(variant: K6DisclosureVariant): ColumnDef[] {
  return [
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'end_book', label: '期末账面价值', format: 'amount' },
    { key: 'end_fair_value', label: '期末公允价值', format: 'amount' },
    { key: 'disposal_fee', label: K6_DISPOSAL_FEE_LABEL[variant], format: 'amount' },
    { key: 'timetable', label: '时间安排', format: 'text' },
  ]
}

/** 上市持有待售负债表（3 列，单级） */
function buildListedLiabilityColumns(): ColumnDef[] {
  return [
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'end_amount', label: '期末余额', format: 'amount' },
    { key: 'prior_amount', label: '上年年末余额', format: 'amount' },
  ]
}

/** K6 上市（五、11）子表列头，键 = `sub_table_data` 数据键 */
export function buildK6ListedColumns(): Record<string, ColumnDef[]> {
  const T = K6_LISTED_SUBTABLE
  return {
    [T.main]: buildHeldForSaleColumns('listed'),
    [T.liability]: buildListedLiabilityColumns(),
    [T.impairment]: buildImpairmentColumns('listed'),
    [T.nonCurrent]: buildFairValueColumns('listed'),
    [T.disposalGroup]: buildFairValueColumns('listed'),
  }
}

/** K6 国企（八、12 资产）子表列头 */
export function buildK6SoeColumns(): Record<string, ColumnDef[]> {
  const T = K6_SOE_SUBTABLE
  return {
    [T.main]: buildHeldForSaleColumns('soe'),
    [T.impairment]: buildImpairmentColumns('soe'),
    [T.nonCurrent]: buildFairValueColumns('soe'),
    [T.disposalGroup]: buildFairValueColumns('soe'),
  }
}

/** K6 国企（八、43 负债）子表列头 */
export function buildK6SoeLiabilityColumns(): Record<string, ColumnDef[]> {
  return { [K6_SOE_LIABILITY_SUBTABLE.liability]: buildFairValueColumns('soe') }
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

/** 减值准备变动行（源模板：期末 = 期初 + 本期增加 − 本期转回 − 本期出售） */
export interface K6ImpairmentRow {
  project: string
  priorAmount: number
  increase: number
  reverse: number
  disposal: number
}

/** 公允价值明细行（持有待售非流动资产 / 处置组 / 负债共用） */
export interface K6FairValueRow {
  project: string
  endBook: number
  endFairValue: number
  disposalFee: number
  timetable?: string
}

/** 一次同步的完整底稿快照（各区块有行才推，避免空表覆盖模板骨架） */
export interface K6DisclosureSnapshot {
  /** 主表（持有待售资产分类） */
  assets: readonly K6DisclosureRow[]
  /** 减值准备变动 */
  impairment?: readonly K6ImpairmentRow[]
  /** 持有待售非流动资产（公允价值口径） */
  nonCurrent?: readonly K6FairValueRow[]
  /** 持有待售处置组（资产 + 负债明细） */
  disposalGroup?: readonly K6FairValueRow[]
  /** 持有待售负债 */
  liabilities?: readonly K6FairValueRow[]
  /** 上市侧负债表是「期末余额 / 上年年末余额」两列口径 */
  listedLiabilities?: readonly { project: string; endAmount: number; priorAmount: number }[]
  narrativeText?: string
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

/** F11-4 反解：账面余额 = 账面价值 + 减值准备 */
function mainTableRows(rows: readonly K6DisclosureRow[]): Array<Record<string, unknown>> {
  const values = (r: K6DisclosureRow): Array<number | null> => [
    num(r.bookValue) + num(r.impairment),
    num(r.impairment),
    num(r.bookValue),
    null,
    null,
    num(r.openingBalance),
  ]
  const sum = (pick: (r: K6DisclosureRow) => number): number =>
    rows.reduce((s, r) => s + num(pick(r)), 0)
  return [
    ...rows.map(r => ({ label: r.project || '', values: values(r) })),
    {
      label: '合计',
      values: [
        sum(r => num(r.bookValue) + num(r.impairment)),
        sum(r => r.impairment),
        sum(r => r.bookValue),
        null,
        null,
        sum(r => r.openingBalance),
      ] as Array<number | null>,
      is_total: true,
    },
  ]
}

function hasFairValueData(r: K6FairValueRow): boolean {
  return Boolean(
    (r.project || '').trim() || num(r.endBook) || num(r.endFairValue) || num(r.disposalFee)
    || (r.timetable || '').trim(),
  )
}

function fairValueRows(rows: readonly K6FairValueRow[]): Array<Record<string, unknown>> {
  const sum = (pick: (r: K6FairValueRow) => number): number =>
    rows.reduce((s, r) => s + num(pick(r)), 0)
  return [
    ...rows.map(r => ({
      label: r.project || '',
      end_book: num(r.endBook),
      end_fair_value: num(r.endFairValue),
      disposal_fee: num(r.disposalFee),
      timetable: r.timetable || '',
    })),
    {
      label: '合计',
      end_book: sum(r => r.endBook),
      end_fair_value: sum(r => r.endFairValue),
      disposal_fee: sum(r => r.disposalFee),
      timetable: '',
      is_total: true,
    },
  ]
}

function hasImpairmentData(r: K6ImpairmentRow): boolean {
  return Boolean(
    (r.project || '').trim() || num(r.priorAmount) || num(r.increase)
    || num(r.reverse) || num(r.disposal),
  )
}

/** 减值准备表期末 = 期初 + 本期增加 − 本期转回 − 本期出售（派生列，不接受入参） */
export function impairmentEndAmount(r: K6ImpairmentRow): number {
  return num(r.priorAmount) + num(r.increase) - num(r.reverse) - num(r.disposal)
}

function impairmentRows(rows: readonly K6ImpairmentRow[]): Array<Record<string, unknown>> {
  const sum = (pick: (r: K6ImpairmentRow) => number): number =>
    rows.reduce((s, r) => s + num(pick(r)), 0)
  return [
    ...rows.map(r => ({
      label: r.project || '',
      prior_amount: num(r.priorAmount),
      increase: num(r.increase),
      reverse: num(r.reverse),
      disposal: num(r.disposal),
      end_amount: impairmentEndAmount(r),
    })),
    {
      label: '合计',
      prior_amount: sum(r => r.priorAmount),
      increase: sum(r => r.increase),
      reverse: sum(r => r.reverse),
      disposal: sum(r => r.disposal),
      end_amount: sum(impairmentEndAmount),
      is_total: true,
    },
  ]
}

function noteTexts(narrativeText: string | undefined): Array<Record<string, string>> | undefined {
  const text = (narrativeText || '').trim()
  if (!text) return undefined
  return [{ section: 'note-held-for-sale', title: '持有待售资产说明', text }]
}

/**
 * 构建 §五、11（上市）/ §八、12（国企资产）载荷。
 *
 * 各条件区块**有行才推**：`_source=workpaper` 下投影器只渲染推来的表、不与模板合并，
 * 推一张只有合计 0 的表会把模板骨架整表覆盖，比不推更糟。
 * 本载荷**拥有**这些表（底稿有录入区块）→ 无行时进 `_removed_table_keys`，
 * 否则用户填过再删空，附注会永久残留过时明细。
 */
export function buildK6SyncPayload(
  variant: K6DisclosureVariant,
  wpId: string,
  snapshot: K6DisclosureSnapshot | readonly K6DisclosureRow[],
  narrativeText?: string,
): K6SyncPayload {
  // 兼容旧签名 `(variant, wpId, rows, narrativeText)`
  const snap: K6DisclosureSnapshot = Array.isArray(snapshot)
    ? { assets: snapshot as readonly K6DisclosureRow[], narrativeText }
    : { ...(snapshot as K6DisclosureSnapshot), narrativeText: (snapshot as K6DisclosureSnapshot).narrativeText ?? narrativeText }

  const T = variant === 'listed' ? K6_LISTED_SUBTABLE : K6_SOE_SUBTABLE
  const allColumns = variant === 'listed' ? buildK6ListedColumns() : buildK6SoeColumns()

  const sub: Record<string, unknown> = {}
  const columns: Record<string, ColumnDef[]> = {}
  const removed: string[] = [...K6_LEGACY_OBSOLETE_TABLES[variant]]

  const put = (name: string, rows: Array<Record<string, unknown>> | null): void => {
    if (rows && rows.length > 0) {
      sub[name] = rows
      columns[name] = allColumns[name]
    } else {
      removed.push(name)
    }
  }

  // 主表恒推（底稿主表一定有分类行；空数组时也推合计行以保证附注有骨架）
  sub[T.main] = mainTableRows(snap.assets ?? [])
  columns[T.main] = allColumns[T.main]

  const impairment = (snap.impairment ?? []).filter(hasImpairmentData)
  put(T.impairment, impairment.length ? impairmentRows(impairment) : null)

  const nonCurrent = (snap.nonCurrent ?? []).filter(hasFairValueData)
  put(T.nonCurrent, nonCurrent.length ? fairValueRows(nonCurrent) : null)

  const disposal = (snap.disposalGroup ?? []).filter(hasFairValueData)
  put(T.disposalGroup, disposal.length ? fairValueRows(disposal) : null)

  if (variant === 'listed') {
    const liab = (snap.listedLiabilities ?? []).filter(
      r => (r.project || '').trim() || num(r.endAmount) || num(r.priorAmount),
    )
    put(
      K6_LISTED_SUBTABLE.liability,
      liab.length
        ? [
          ...liab.map(r => ({
            label: r.project || '',
            end_amount: num(r.endAmount),
            prior_amount: num(r.priorAmount),
          })),
          {
            label: '合计',
            end_amount: liab.reduce((s, r) => s + num(r.endAmount), 0),
            prior_amount: liab.reduce((s, r) => s + num(r.priorAmount), 0),
            is_total: true,
          },
        ]
        : null,
    )
  }

  const texts = noteTexts(snap.narrativeText)
  if (texts) sub._note_texts = texts
  // 不把本次推送的键放进 removed（否则刚推就被删）
  const pushed = new Set(Object.keys(sub))
  const removedKeys = [...new Set(removed)].filter(k => !pushed.has(k))
  if (removedKeys.length) sub._removed_table_keys = removedKeys

  return {
    wp_id: wpId,
    sheet_name: K6_DISCLOSURE_SHEET_NAME[variant],
    section_id: K6_NOTE_SECTION[variant],
    current_standard: resolveCurrentStandard(variant),
    sub_table_data: sub,
    columns,
  }
}

/**
 * 构建 §八、43（国企持有待售负债）载荷 —— **独立章节，必须单独 POST 一次**。
 *
 * `sync_from_workpaper` 的定位键是 `(project_id, year, note_section)`，
 * 一个 payload 只能写一节；国企负债不在 八、12 内。上市侧负债并入 五、11，
 * 不走本函数（见 `buildK6SyncPayload` 的 `listedLiabilities`）。
 *
 * 🔴 空行时必须发**清理载荷**（`_removed_table_keys`），不能直接不发请求
 * （2026-07-31 浏览器实测踩中）：用户填过再清空后，附注 §八、43 会**永久残留上次推送的
 * 过时负债明细**（子表仍在、`last_sync_at` 不前移）。
 *
 * 曾试过「只在该区块被改动过时才清理」（`wasTouched` 启发式），但宿主会重建
 * `allResponses` 并重挂 Tab，实测出现「同一次会话里 add 能识别、delete 识别不到」的
 * 不确定行为 → **改为无条件发送**（`clearWhenEmpty` 默认 true）。
 * 代价：从未有持有待售负债的项目，§八、43 会显示「无数据」而不是模板的空白骨架 ——
 * §八、43 只承载 K6 这一张表，如实显示「无数据」可接受，且重新生成附注即恢复骨架。
 * `clearWhenEmpty: false` 保留给「明确不想动该节」的调用方（当前无消费方，但契约已覆盖）。
 */
export function buildK6SoeLiabilityPayload(
  wpId: string,
  liabilities: readonly K6FairValueRow[],
  narrativeText?: string,
  opts: { clearWhenEmpty?: boolean } = {},
): K6SyncPayload | null {
  const { clearWhenEmpty = true } = opts
  const rows = liabilities.filter(hasFairValueData)
  const name = K6_SOE_LIABILITY_SUBTABLE.liability
  const sub: Record<string, unknown> = {}
  if (rows.length > 0) {
    sub[name] = fairValueRows(rows)
  } else if (clearWhenEmpty) {
    sub._removed_table_keys = [name]
  } else {
    return null
  }
  const texts = noteTexts(narrativeText)
  if (texts) sub._note_texts = texts
  return {
    wp_id: wpId,
    sheet_name: K6_DISCLOSURE_SHEET_NAME.soe,
    section_id: K6_SOE_LIABILITY_NOTE_SECTION,
    current_standard: resolveCurrentStandard('soe'),
    sub_table_data: sub,
    columns: rows.length > 0 ? buildK6SoeLiabilityColumns() : {},
  }
}
