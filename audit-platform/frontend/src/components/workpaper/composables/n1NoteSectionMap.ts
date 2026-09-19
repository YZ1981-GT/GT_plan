/**
 * N1 递延所得税资产披露 ↔ 附注章节冻结映射与 sync payload 构建
 *
 * 权威来源
 * --------
 * - **列结构 / 行型 / 文本** = `backend/wp_templates/N/N1 递延所得税资产.xlsx` 的
 *   `附注披露信息（上市公司）`（A1:K54）与 `附注披露信息（国企）`（A1:IV74），
 *   逐行 + 合并单元格实测；结论固化在
 *   `.kiro/specs/n1-deferred-tax-disclosure-template-alignment/design.md` §1。
 * - **章节号** = `backend/data/note_template_variant_matrix.json`
 *   （`di_yan_suo_de_shui_zi_chan_he_di_yan_suo_de` → listed 五、30 / soe 八、31）
 * - **表名 / 行集合** = `note_template_listed.json` 五、30 / `note_template_soe.json` 八、31
 *   （由 `backend/scripts/fix/fix_note_deferred_tax_structure.py` 幂等维护）
 * - **sheet 名** = `workpaper_sheet_classification`（wp_code=N1）实测全角括号
 *
 * 🔴 表 1 是两级表头 5 列，且**两版子列序相反**（源模板 B11:E11）：
 * 上市「可抵扣/应纳税暂时性差异」在前，国企「递延所得税资产/负债」在前。
 * `columns` 的键序必须与之一致，否则同步后附注列错位。
 *
 * 🔴 国企有 **5 张表**（多一张源模板（2）B「递延所得税资产和递延所得税负债互抵明细」）。
 *
 * 🔴 共用章节所有权（spec n1-disclosure-note-linkage · Decision 1 · 方案 A）：
 * 五、30 / 八、31 由 **N1（递延所得税资产）与 N3（递延所得税负债）共用**，
 * 且表 1 / 表 2 在同一张表内混合资产段与负债段行；而 `sync_from_workpaper` 对
 * `sub_table_data` 是「按键浅合并、同名键整体覆盖」→ 若两边各推同名键必然互相冲掉。
 * 因此本章节全部子表的 owner 统一为 **N1**：N3 不得推送，只能发布跨底稿键
 * （如 `N1-4-total-deferred-tax-liability`）供 N1 取用。
 * 负债段 / 互抵金额取不到时值为 `null`（不填 0，0 会被误读为"已核实为零"）。
 */
import { defineColumns, type ColumnDef } from './disclosureColumnDefs'
import type { TableNamespaceSpec } from './disclosureSyncedTables'

export type N1DisclosureVariant = 'listed' | 'soe'

/** 附注章节号（权威矩阵 di_yan_suo_de_shui_zi_chan_he_di_yan_suo_de） */
export const N1_NOTE_SECTION = {
  listed: '五、30',
  soe: '八、31',
} as const satisfies Record<N1DisclosureVariant, string>

/** 底稿披露 sheet 真实 tab 名（供 `_last_sync_sheet` 反向定位） */
export const N1_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<N1DisclosureVariant, string>

/**
 * 子表键（逐字取自附注模板 `tables[].name`）。
 *
 * 国企多一个 `offsetDetail`（源模板（2）B）—— 上市源模板无此表，故 listed 不含该键。
 */
export const N1_SUB_TABLE_KEYS = {
  listed: {
    unoffset: '未经抵销的递延所得税资产和递延所得税负债',
    netOffset: '以抵销后净额列示的递延所得税资产或负债',
    unrecognized: '未确认递延所得税资产的可抵扣暂时性差异及可抵扣亏损明细',
    lossExpiry: '未确认递延所得税资产的可抵扣亏损将于以下年度到期',
  },
  soe: {
    unoffset: '未经抵销的递延所得税资产和递延所得税负债',
    netOffset: '以抵销后净额列示的递延所得税资产或负债',
    offsetDetail: '递延所得税资产和递延所得税负债互抵明细',
    unrecognized: '未确认递延所得税资产明细',
    lossExpiry: '未确认递延所得税资产的可抵扣亏损将于以下年度到期',
  },
} as const satisfies Record<N1DisclosureVariant, Record<string, string>>

/** 表名命名空间（R7.5 基线播种；本章节全部表名固定，无动态前缀/续表后缀） */
export const N1_TABLE_NAMESPACE: Record<N1DisclosureVariant, TableNamespaceSpec> = {
  listed: { known: Object.values(N1_SUB_TABLE_KEYS.listed) },
  soe: { known: Object.values(N1_SUB_TABLE_KEYS.soe) },
}

/**
 * 资产段 / 负债段分组标题行（逐字取自源模板 A12 / A22 与附注模板 rows）。
 *
 * 上市 A12 `递延所得税资产：` / A22 `递延所得税负债：`（均为整行合并单元格）；
 * 国企 A12 `一、递延所得税资产` / 表 2 A45 `二、递延所得税负债`。
 * 国企表 1 的负债段标题源模板写 `递延所得税负债：`，附注模板统一为 `二、递延所得税负债`
 * （表 1 与表 2 同构，便于两表对照）→ 以附注模板为准。
 */
export const N1_GROUP_LABELS = {
  listed: { asset: '递延所得税资产：', liability: '递延所得税负债：' },
  soe: { asset: '一、递延所得税资产', liability: '二、递延所得税负债' },
} as const satisfies Record<N1DisclosureVariant, { asset: string; liability: string }>

/** 小计 / 合计行字面（源模板写 `小  计`、`合  计`，附注模板为无空格形式） */
export const N1_SUBTOTAL_LABEL = '小计'
export const N1_TOTAL_LABEL = '合计'

export function resolveN1CurrentStandard(
  variant: N1DisclosureVariant,
  applicableStandards?: readonly string[] | null,
): string {
  const list = (applicableStandards || []).map((s) => String(s).toLowerCase())
  if (variant === 'listed') {
    if (list.some((s) => s === 'listed_consolidated' || (s.includes('listed') && s.includes('consol')))) {
      return 'listed_consolidated'
    }
    return 'listed_standalone'
  }
  if (list.some((s) => s === 'soe_consolidated' || (s.includes('soe') && s.includes('consol')))) {
    return 'soe_consolidated'
  }
  return 'soe_standalone'
}

// ─── 列头元数据（逐字取自附注模板 headers）─────────────────────────────────────

const AMT = 'amount' as const
const TXT = 'text' as const

export const N1_UNOFFSET_DIFF_LABEL = '可抵扣/应纳税暂时性差异'
export const N1_UNOFFSET_TAX_LABEL = '递延所得税资产/负债'

/** 表 1 期末 / 期初父表头（国企用「年初余额」） */
export const N1_UNOFFSET_GROUPS = {
  listed: { end: '期末余额', prior: '上年年末余额' },
  soe: { end: '期末余额', prior: '年初余额' },
} as const satisfies Record<N1DisclosureVariant, { end: string; prior: string }>

/**
 * 表 1 两级表头的子列序 —— 🔴 源模板两版相反（B11:E11 实测）。
 *
 * 返回 `[[键后缀, 列头], ...]`；同步 `columns` 与底稿 UI 列序都必须引用本函数，
 * 禁止各写一份（写死会让两版子列串味 → 附注列错位）。
 */
export function n1UnoffsetSubOrder(
  variant: N1DisclosureVariant,
): ReadonlyArray<readonly ['diff' | 'tax', string]> {
  return variant === 'listed'
    ? ([['diff', N1_UNOFFSET_DIFF_LABEL], ['tax', N1_UNOFFSET_TAX_LABEL]] as const)
    : ([['tax', N1_UNOFFSET_TAX_LABEL], ['diff', N1_UNOFFSET_DIFF_LABEL]] as const)
}

/** 表 1：项目 + 期末余额{2 子列} + {上年年末|年初}余额{2 子列}（两级表头） */
function unoffsetColumns(variant: N1DisclosureVariant): ColumnDef[] {
  const g = N1_UNOFFSET_GROUPS[variant]
  const order = n1UnoffsetSubOrder(variant)
  return defineColumns([
    { key: 'label', label: '项目', is_label: true },
    ...order.map(([k, label]) => ({ key: `end_${k}`, label, group: g.end, format: AMT })),
    ...order.map(([k, label]) => ({ key: `prior_${k}`, label, group: g.prior, format: AMT })),
  ])
}

/**
 * 表 2（抵销后净额列示）—— 🔴 两版列语义本质不同，不是换 label 就能套。
 *
 * - 上市（源模板 R34）：互抵金额 + 抵销后余额，各期末/期初一组
 * - 国企（源模板 R34）：互抵后的资产或负债 + 互抵后的可抵扣或应纳税暂时性差异
 */
function netOffsetColumns(variant: N1DisclosureVariant): ColumnDef[] {
  if (variant === 'listed') {
    return defineColumns([
      { key: 'label', label: '项目', is_label: true, flat: true },
      { key: 'offset_end', label: '递延所得税资产和负债期末互抵金额', format: AMT },
      { key: 'net_end', label: '抵销后递延所得税资产或负债期末余额', format: AMT },
      { key: 'offset_prior', label: '递延所得税资产和负债期初互抵金额', format: AMT },
      { key: 'net_prior', label: '抵销后递延所得税资产或负债期初余额', format: AMT },
    ])
  }
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'net_end', label: '报告期末互抵后的递延所得税资产或负债', format: AMT },
    { key: 'diff_end', label: '报告期末互抵后的可抵扣或应纳税暂时性差异', format: AMT },
    { key: 'net_prior', label: '报告年初互抵后的递延所得税资产或负债', format: AMT },
    { key: 'diff_prior', label: '报告年初互抵后的可抵扣或应纳税暂时性差异', format: AMT },
  ])
}

/** 表 3（国企）互抵明细：源模板（2）B，2 列 */
function offsetDetailColumns(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'amount', label: '本期互抵金额', format: AMT },
  ])
}

/** 未确认明细：项目 + 期末余额 + （上年年末 / 年初）余额 */
function unrecognizedColumns(variant: N1DisclosureVariant): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'end', label: '期末余额', format: AMT },
    { key: 'prior', label: variant === 'listed' ? '上年年末余额' : '年初余额', format: AMT },
  ])
}

/** 亏损到期：年份 + 期末 + （上年年末 / 年初）+ 备注 */
function lossExpiryColumns(variant: N1DisclosureVariant): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '年份', is_label: true, flat: true },
    { key: 'end', label: '期末余额', format: AMT },
    { key: 'prior', label: variant === 'listed' ? '上年年末余额' : '年初余额', format: AMT },
    { key: 'remark', label: '备注', format: TXT },
  ])
}

/** 全量列定义（供契约测试与 `disclosureColumnsCoverage` 守卫零参调用） */
export function buildN1ListedColumns(): Record<string, ColumnDef[]> {
  const K = N1_SUB_TABLE_KEYS.listed
  return {
    [K.unoffset]: unoffsetColumns('listed'),
    [K.netOffset]: netOffsetColumns('listed'),
    [K.unrecognized]: unrecognizedColumns('listed'),
    [K.lossExpiry]: lossExpiryColumns('listed'),
  }
}

export function buildN1SoeColumns(): Record<string, ColumnDef[]> {
  const K = N1_SUB_TABLE_KEYS.soe
  return {
    [K.unoffset]: unoffsetColumns('soe'),
    [K.netOffset]: netOffsetColumns('soe'),
    [K.offsetDetail]: offsetDetailColumns(),
    [K.unrecognized]: unrecognizedColumns('soe'),
    [K.lossExpiry]: lossExpiryColumns('soe'),
  }
}

/**
 * 变体分发。
 *
 * 🔴 **不能命名为 `buildN1Columns`**：`disclosureColumnsCoverage` 守卫会 sweep
 * 所有 `build*Columns` 导出并**用空入参调用**，带 variant 参数的 builder 会因此
 * 拿到 `undefined` 而产出错变体列头。参数化 builder 统一用 `n1ColumnsFor` 命名，
 * 对外只把零参的 `buildN1ListedColumns` / `buildN1SoeColumns` 暴露给守卫。
 */
export function n1ColumnsFor(variant: N1DisclosureVariant): Record<string, ColumnDef[]> {
  return variant === 'listed' ? buildN1ListedColumns() : buildN1SoeColumns()
}

// ─── Snapshot 类型（由披露组件组装）─────────────────────────────────────────

/** 可空金额：`null` 表示"未取到"（禁止用 0 冒充） */
export type NullableAmount = number | null

/** 表 1 明细行（4 个值列，键与 `unoffsetColumns` 一致） */
export interface N1UnoffsetItemRow {
  item: string
  /** 期末 可抵扣/应纳税暂时性差异 */
  endDiff: NullableAmount
  /** 期末 递延所得税资产/负债 */
  endTax: NullableAmount
  priorDiff: NullableAmount
  priorTax: NullableAmount
}

/** 表 1 段小计兜底（无明细行时用，取自 N1-4 测算表 / N3 发布键） */
export interface N1UnoffsetSubtotal {
  endDiff?: NullableAmount
  endTax?: NullableAmount
  priorDiff?: NullableAmount
  priorTax?: NullableAmount
}

/** 表 2（上市）2 行形态 */
export interface N1NetOffsetSnapshot {
  assetOffsetEnd?: NullableAmount
  assetNetEnd?: NullableAmount
  assetOffsetPrior?: NullableAmount
  assetNetPrior?: NullableAmount
  liabOffsetEnd?: NullableAmount
  liabNetEnd?: NullableAmount
  liabOffsetPrior?: NullableAmount
  liabNetPrior?: NullableAmount
}

/** 表 2（国企）逐项形态 */
export interface N1NetOffsetItemRow {
  item: string
  netEnd: NullableAmount
  diffEnd: NullableAmount
  netPrior: NullableAmount
  diffPrior: NullableAmount
}

export interface N1OffsetDetailRow {
  item: string
  amount: NullableAmount
}

export interface N1UnrecognizedRowLike {
  item: string
  amount: NullableAmount
  priorAmount?: NullableAmount
}

export interface N1LossExpiryRowLike {
  /** 到期年度（如 `"2027"` 或 `"2027年"`），构造时统一补「年」字 */
  expiryYear: string
  unrecovered: NullableAmount
  priorUnrecovered?: NullableAmount
  remark?: string
}

export interface N1DisclosureSnapshot {
  /** 表 1 资产段明细（不含分组标题 / 小计，由本模块生成） */
  assetRows: N1UnoffsetItemRow[]
  /** 表 1 负债段明细（业务上属 N3；无数据时留空 → 只出分组标题 + null 小计） */
  liabilityRows?: N1UnoffsetItemRow[]
  /** 负债段小计兜底（`liabilityRows` 为空时使用） */
  liabilitySubtotal?: N1UnoffsetSubtotal
  /** 表 2（上市 2 行形态） */
  netOffset?: N1NetOffsetSnapshot
  /** 表 2（国企逐项形态）资产段 */
  netOffsetAssetRows?: N1NetOffsetItemRow[]
  /** 表 2（国企逐项形态）负债段 */
  netOffsetLiabilityRows?: N1NetOffsetItemRow[]
  /** 表 3（国企）互抵明细 */
  offsetDetailRows?: N1OffsetDetailRow[]
  unrecognizedRows: N1UnrecognizedRowLike[]
  lossExpiryRows: N1LossExpiryRowLike[]
  /** 说明 / 结论文本（按子节，值为空串则不同步） */
  notes?: Record<string, string>
  /** 上次同步成功时推送的子表名（R7 孤儿清理差集基线） */
  previouslySyncedTables?: readonly string[]
  /**
   * 披露口径分支（源模板国企 R7）：`gross` 按（1）披露 / `net` 按（2）A+（2）B 披露。
   * 二者**互斥** —— 未选中分支的表不推送并进 `_removed_table_keys`。
   * 上市变体不使用本字段（上市（1）恒披露，（2）由 `netOffsetApplicable` 控制）。
   */
  offsetMode?: 'undecided' | 'gross' | 'net'
  /**
   * 上市表（2）是否适用（源模板 R33 标题括注「不适用的删除」）。
   * `false` → 不推送该表并进 `_removed_table_keys`；
   * `true` / `null` / 缺省 → 推送（未判断时不删交付物内容）。
   */
  netOffsetApplicable?: boolean | null
}

export interface N1SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  year: number
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

/**
 * 按披露分支判定「本次应推送哪些分支表」。
 *
 * 源模板规则：
 * - 国企 R7：不以抵销后净额列示 → 只披露（1）；以抵销后净额列示 → 只披露（2）A 与（2）B。
 * - 上市 R33：（1）恒披露；（2）标题括注「不适用的删除」→ 由适用性开关控制。
 *
 * 返回 `{pushed, removed}`，两者**恒无交集**且并集覆盖该变体全部分支表键
 * （Property 8，由 `n1NoteSectionMap.spec.ts` 锁死）。
 */
export function n1BranchTableKeys(variant: N1DisclosureVariant): string[] {
  // 上市：（1）恒披露，只有（2）受适用性开关控制
  if (variant === 'listed') return [N1_SUB_TABLE_KEYS.listed.netOffset]
  // 国企：（1）与（2）A/（2）B 互斥，三张表都是分支表
  const soe = N1_SUB_TABLE_KEYS.soe
  return [soe.unoffset, soe.netOffset, soe.offsetDetail]
}

export function resolveN1BranchTables(
  variant: N1DisclosureVariant,
  snapshot: Pick<N1DisclosureSnapshot, 'offsetMode' | 'netOffsetApplicable'>,
): { pushed: string[]; removed: string[] } {
  if (variant === 'listed') {
    const key = N1_SUB_TABLE_KEYS.listed.netOffset
    // 只有**明确判定不适用**（false）才清除；未判断（null/undefined）仍推送
    return snapshot.netOffsetApplicable === false
      ? { pushed: [], removed: [key] }
      : { pushed: [key], removed: [] }
  }
  const soe = N1_SUB_TABLE_KEYS.soe
  if (snapshot.offsetMode === 'net') {
    return { pushed: [soe.netOffset, soe.offsetDetail], removed: [soe.unoffset] }
  }
  if (snapshot.offsetMode === 'gross') {
    return { pushed: [soe.unoffset], removed: [soe.netOffset, soe.offsetDetail] }
  }
  // undecided：三张分支表全推、不删任何表（零回归）
  return { pushed: [soe.unoffset, soe.netOffset, soe.offsetDetail], removed: [] }
}

// ─── helpers ─────────────────────────────────────────────────────────────────

const nz = (v: unknown): NullableAmount =>
  typeof v === 'number' && Number.isFinite(v) ? v : null

/** 可空求和：全为 null 时返回 null（不塌成 0） */
function sumNullable(vals: readonly NullableAmount[]): NullableAmount {
  let has = false
  let total = 0
  for (const v of vals) {
    if (v === null || v === undefined) continue
    has = true
    total += v
  }
  return has ? Math.round(total * 100) / 100 : null
}

/**
 * 行型判定必须先去空白：源模板写的是 `小  计` / `合  计`（中间带空格），
 * `startsWith('小计')` 会漏判 → 小计行被当普通数据行推给附注，丢 `is_total`。
 */
export function normalizeN1RowLabel(label: unknown): string {
  return String(label ?? '').replace(/\s+/g, '')
}

export function isN1TotalLabel(label: unknown): boolean {
  const s = normalizeN1RowLabel(label)
  return s.startsWith('小计') || s.startsWith('合计')
}

const NOTE_TITLES: Record<string, string> = {
  rollback: '一年后预期转回情况说明',
  conclusion: '披露说明与结论',
  sufficiency: '确认充足性判断说明',
  offset: '抵销与分列口径说明',
  unrecognized: '未确认递延所得税资产说明',
}

const NOTE_ORDER = ['rollback', 'offset', 'sufficiency', 'unrecognized', 'conclusion']

/** 各子节说明 → `_note_texts`（仅非空；全空则调用方不写该键） */
export function buildN1NoteTexts(
  notes?: Record<string, string>,
): Array<{ section: string; title: string; text: string }> {
  if (!notes) return []
  const keys = [
    ...NOTE_ORDER.filter((k) => k in notes),
    ...Object.keys(notes).filter((k) => !NOTE_ORDER.includes(k)),
  ]
  const out: Array<{ section: string; title: string; text: string }> = []
  for (const k of keys) {
    const text = String(notes[k] ?? '').trim()
    if (!text) continue
    out.push({ section: `n1-disclosure-${k}`, title: NOTE_TITLES[k] || k, text })
  }
  return out
}

// ─── 行构造 ──────────────────────────────────────────────────────────────────

type Row = Record<string, unknown>

/**
 * 分组标题行（资产段 / 负债段）。
 *
 * 不带 `row_type` —— 投影器（前后端一致）只保留 `label` / `values` / `is_total`，
 * 额外字段会被丢弃；分组语义由"全列 null"承载，与附注模板 seed 行一致。
 */
function unoffsetGroupRow(label: string): Row {
  return { label, end_diff: null, end_tax: null, prior_diff: null, prior_tax: null }
}

function unoffsetDataRow(r: N1UnoffsetItemRow): Row {
  return {
    label: String(r.item ?? ''),
    end_diff: nz(r.endDiff),
    end_tax: nz(r.endTax),
    prior_diff: nz(r.priorDiff),
    prior_tax: nz(r.priorTax),
  }
}

function unoffsetSubtotalRow(
  rows: readonly N1UnoffsetItemRow[],
  fallback?: N1UnoffsetSubtotal,
): Row {
  const pick = (
    field: keyof N1UnoffsetItemRow & ('endDiff' | 'endTax' | 'priorDiff' | 'priorTax'),
  ): NullableAmount =>
    rows.length ? sumNullable(rows.map((r) => nz(r[field]))) : nz(fallback?.[field])
  return {
    label: N1_SUBTOTAL_LABEL,
    end_diff: pick('endDiff'),
    end_tax: pick('endTax'),
    prior_diff: pick('priorDiff'),
    prior_tax: pick('priorTax'),
    is_total: true,
  }
}

function netOffsetGroupRow(label: string): Row {
  return { label, net_end: null, diff_end: null, net_prior: null, diff_prior: null }
}

function netOffsetDataRow(r: N1NetOffsetItemRow): Row {
  return {
    label: String(r.item ?? ''),
    net_end: nz(r.netEnd),
    diff_end: nz(r.diffEnd),
    net_prior: nz(r.netPrior),
    diff_prior: nz(r.diffPrior),
  }
}

function netOffsetSubtotalRow(rows: readonly N1NetOffsetItemRow[]): Row {
  return {
    label: N1_SUBTOTAL_LABEL,
    net_end: sumNullable(rows.map((r) => nz(r.netEnd))),
    diff_end: sumNullable(rows.map((r) => nz(r.diffEnd))),
    net_prior: sumNullable(rows.map((r) => nz(r.netPrior))),
    diff_prior: sumNullable(rows.map((r) => nz(r.diffPrior))),
    is_total: true,
  }
}

// ─── payload 构造（纯函数）───────────────────────────────────────────────────

/**
 * 构造 N1 披露表 → 附注 sync 请求体。
 *
 * 覆盖该章节全部子表（listed 4 张 / soe 5 张，owner=N1）；
 * `sub_table_data` 与 `columns` 的键集合恒相同（投影器按键名匹配，键不一致则附注端渲染不出列头）。
 */
export function buildN1SyncPayload(
  variant: N1DisclosureVariant,
  snapshot: N1DisclosureSnapshot,
  ctx: { wpId: string; year: number; applicableStandards?: readonly string[] | null },
): N1SyncPayload {
  const G = N1_GROUP_LABELS[variant]
  const allColumns = n1ColumnsFor(variant)
  const subTableData: Record<string, unknown> = {}
  const branch = resolveN1BranchTables(variant, snapshot)
  const skipped = new Set(branch.removed)

  // ① 表 1 未经抵销：资产段（标题 + 明细 + 小计）+ 负债段（标题 + 明细 + 小计）
  //    国企在「以抵销后净额列示」口径下不披露本表（源模板 R7），故按分支跳过。
  const assetRows = snapshot.assetRows || []
  const liabRows = snapshot.liabilityRows || []
  const unoffsetKey = N1_SUB_TABLE_KEYS[variant].unoffset
  if (!skipped.has(unoffsetKey)) {
    subTableData[unoffsetKey] = [
      unoffsetGroupRow(G.asset),
      ...assetRows.map(unoffsetDataRow),
      unoffsetSubtotalRow(assetRows),
      unoffsetGroupRow(G.liability),
      ...liabRows.map(unoffsetDataRow),
      unoffsetSubtotalRow(liabRows, snapshot.liabilitySubtotal),
    ]
  }

  // ② 表 2 抵销后净额列示（上市受 R33 适用性开关控制 / 国企受 R7 分支控制）
  if (variant === 'listed') {
    const key = N1_SUB_TABLE_KEYS.listed.netOffset
    if (!skipped.has(key)) {
      const off = snapshot.netOffset || {}
      subTableData[key] = [
        {
          label: '递延所得税资产',
          offset_end: nz(off.assetOffsetEnd), net_end: nz(off.assetNetEnd),
          offset_prior: nz(off.assetOffsetPrior), net_prior: nz(off.assetNetPrior),
        },
        {
          label: '递延所得税负债',
          offset_end: nz(off.liabOffsetEnd), net_end: nz(off.liabNetEnd),
          offset_prior: nz(off.liabOffsetPrior), net_prior: nz(off.liabNetPrior),
        },
      ]
    }
  } else {
    const netKey = N1_SUB_TABLE_KEYS.soe.netOffset
    if (!skipped.has(netKey)) {
      const na = snapshot.netOffsetAssetRows || []
      const nl = snapshot.netOffsetLiabilityRows || []
      subTableData[netKey] = [
        netOffsetGroupRow(G.asset),
        ...na.map(netOffsetDataRow),
        netOffsetSubtotalRow(na),
        netOffsetGroupRow(G.liability),
        ...nl.map(netOffsetDataRow),
        netOffsetSubtotalRow(nl),
      ]
    }

    // ③ 表 3 互抵明细（国企独有；源模板（2）B，纯动态行区域）
    const detailKey = N1_SUB_TABLE_KEYS.soe.offsetDetail
    if (!skipped.has(detailKey)) {
      subTableData[detailKey] = (snapshot.offsetDetailRows || []).map((r) => ({
        label: String(r.item ?? ''),
        amount: nz(r.amount),
      }))
    }
  }

  // ④ 未确认递延所得税资产明细（纯资产侧）
  const unrec = snapshot.unrecognizedRows || []
  subTableData[N1_SUB_TABLE_KEYS[variant].unrecognized] = [
    ...unrec.map((r) => ({
      label: String(r.item ?? ''),
      end: nz(r.amount),
      prior: nz(r.priorAmount),
    })),
    {
      label: N1_TOTAL_LABEL,
      end: sumNullable(unrec.map((r) => nz(r.amount))),
      prior: sumNullable(unrec.map((r) => nz(r.priorAmount))),
      is_total: true,
    },
  ]

  // ⑤ 可抵扣亏损到期（按到期年度聚合）
  const lossRows = snapshot.lossExpiryRows || []
  const byYear = new Map<string, { end: NullableAmount[]; prior: NullableAmount[]; remarks: string[] }>()
  for (const r of lossRows) {
    const y = String(r.expiryYear ?? '').trim()
    if (!y || y === '—') continue
    const key = /年$/.test(y) ? y : `${y}年`
    const slot = byYear.get(key) || { end: [], prior: [], remarks: [] }
    slot.end.push(nz(r.unrecovered))
    slot.prior.push(nz(r.priorUnrecovered))
    const rm = String(r.remark ?? '').trim()
    if (rm) slot.remarks.push(rm)
    byYear.set(key, slot)
  }
  const expiryRows = [...byYear.entries()]
    .sort((a, b) => a[0].localeCompare(b[0], 'zh-CN'))
    .map(([year, slot]) => ({
      label: year,
      end: sumNullable(slot.end),
      prior: sumNullable(slot.prior),
      remark: slot.remarks.join('；'),
    }))
  subTableData[N1_SUB_TABLE_KEYS[variant].lossExpiry] = [
    ...expiryRows,
    {
      label: N1_TOTAL_LABEL,
      end: sumNullable(expiryRows.map((r) => r.end)),
      prior: sumNullable(expiryRows.map((r) => r.prior)),
      remark: '',
      is_total: true,
    },
  ]

  // ⑥ 说明文本（空则不写 `_note_texts`，避免覆盖附注既有正文）
  const texts = buildN1NoteTexts(snapshot.notes)
  if (texts.length > 0) subTableData._note_texts = texts

  // ⑦ 分支孤儿清理：未选中分支的表必须显式删除，否则用户切换口径后
  //    附注永久残留另一分支的过时数据（平台实证：有录入区块的条件表必须进 removed）。
  //    只删**上次由本底稿推过**的表 —— 从未推过就不属本载荷所有，不越权删。
  const previously = new Set(snapshot.previouslySyncedTables || [])
  const removedKeys = branch.removed.filter((k) => previously.has(k))
  if (removedKeys.length > 0) subTableData._removed_table_keys = removedKeys

  // `columns` 键集与 `sub_table_data` 保持一致（投影器按键名匹配列头）
  const pushedKeys = Object.keys(subTableData).filter((k) => !k.startsWith('_'))
  const columns: Record<string, ColumnDef[]> = {}
  for (const k of pushedKeys) {
    if (allColumns[k]) columns[k] = allColumns[k]
  }

  return {
    wp_id: ctx.wpId,
    sheet_name: N1_DISCLOSURE_SHEET_NAME[variant],
    section_id: N1_NOTE_SECTION[variant],
    current_standard: resolveN1CurrentStandard(variant, ctx.applicableStandards),
    year: ctx.year,
    sub_table_data: subTableData,
    columns,
  }
}

export default buildN1SyncPayload
