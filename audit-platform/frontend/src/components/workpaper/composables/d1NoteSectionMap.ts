/**
 * D1 应收票据披露 ↔ 附注章节冻结映射与 sync payload 构建
 *
 * 权威来源：note_template_listed.json 五、4 / note_template_soe.json 八、4「应收票据」
 * （表名/列头逐字对照模板；行数据来自 D1 底稿「附注披露信息（上市公司）/（国企）」披露表）。
 *
 * 底稿 → 附注单向推送（sync_from_workpaper）：
 *  - sub_table_data 各子表 → 附注 table_data.sub_table_data（读时投影为 _tables 渲染）
 *  - sub_table_data._note_texts → 附注 text_content（文本框内容与披露表保持一致）
 *  - columns → _sub_table_columns（投影器据此产出扁平表头，附注模块渲染）
 *
 * 🔴 覆盖必须完整：note_sub_table_projector 对 `_source=workpaper` 的附注
 * **只渲染 sub_table_data 里推送过的子表**（不与模板 _tables 合并）。
 * 少推一张表 = 附注里少一张表，故此处逐张覆盖披露表的全部表格。
 *
 * 覆盖完整性（对照模板）：上市 五、4 共 14 张、国企 八、4 共 12 张，本文件全覆盖。
 * 与模板字面值的唯一偏差：模板列头里的 HTML 换行 `<br/>`（如「应收票据<br/>性质」）去掉，
 * 文字逐字保留；上市/国企措辞不同的列头（转回或收回表、核销逐项表）各按自身模板产出。
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type D1DisclosureVariant = 'listed' | 'soe'

export const D1_NOTE_SECTION = {
  listed: '五、4',
  soe: '八、4',
} as const satisfies Record<D1DisclosureVariant, string>

// 底稿披露 sheet 真实 tab 名（全角括号，见 workpaper_sheet_classification wp_code=D1）。
// 用真实 sheet 名而非合成标识，使附注「打开同步底稿」(_last_sync_sheet) 反向跳转能精确定位。
export const D1_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<D1DisclosureVariant, string>

export function resolveD1CurrentStandard(
  variant: D1DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
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

// ─── 表名（逐字取自附注模板 五、4 / 八、4）──────────────────────────────────
// 🔴 每个值必须与 note_template `tables[].name` 逐字一致，否则同步产出孤儿子表
//    （附注 TAB 永空 + 底稿数据丢失）。守卫：`__tests__/d1NoteSubtableContract.spec.ts`
const T = {
  listed: {
    main: '应收票据',
    pledged: '期末已质押的应收票据',
    endorsed: '期末已背书或贴现但尚未到期的应收票据',
    // 🔴 逐字取源模板 R31「（3）期末因出票人未履约而其转应收账款的票据」——**无「将」**；
    //    国企侧源模板 R74 是「而其转为应收账款」（多「为」），两版措辞本就不同。
    //    旧名（含「将」）见 D1_LEGACY_OBSOLETE_TABLES，同步时清孤儿子表。
    transfer: '期末因出票人未履约而其转应收账款的票据',
    classEnd: '按坏账计提方法分类（期末余额）',
    classPrior: '按坏账计提方法分类（续：上年年末余额）',
    individualEnd: '按单项计提坏账准备的应收票据（期末余额）',
    individualPrior: '按单项计提坏账准备的应收票据（续：上年年末余额）',
    portfolioBank: '组合计提项目：银行承兑汇票',
    portfolioCommercial: '组合计提项目：商业承兑汇票',
    movement: '本期计提、收回或转回的坏账准备情况',
    reversal: '本期转回或收回金额重要的坏账准备',
    writeOffAmount: '本期实际核销的应收票据情况',
    writeOffDetail: '重要的应收票据核销情况（逐项披露）',
  },
  soe: {
    main: '应收票据分类',
    pledged: '期末已质押的应收票据',
    endorsed: '期末已背书或贴现但尚未到期的应收票据',
    transfer: '期末因出票人未履约而其转为应收账款的票据',
    classEnd: '按坏账准备计提方法分类披露应收票据（期末数）',
    classPrior: '按坏账准备计提方法分类披露应收票据（续：期初数）',
    individualEnd: '按单项计提坏账准备的应收票据',
    portfolio: '按组合计提坏账准备的应收票据',
    movement: '本期计提、收回或转回的应收票据坏账准备情况',
    reversal: '本期转回或收回金额重要的应收票据坏账准备',
    writeOffAmount: '本期实际核销的应收票据',
    writeOffDetail: '重要的应收票据核销情况',
  },
} as const

/** 上市 五、4 子表名映射（`{语义键: 模板表名}`），供契约测试与调用方复用。 */
export const D1_LISTED_SUBTABLE = T.listed
/** 国企 八、4 子表名映射。 */
export const D1_SOE_SUBTABLE = T.soe

/**
 * 历史表名（本循环曾推送过、现已改名/退役的键）。
 *
 * 附注 `sub_table_data` 以**表名为键**，改名后旧键会永久残留成孤儿子表
 * （模板已无该名 → 投影器不渲染，但库里一直躺着过时数据）。同步时随载荷发
 * `_removed_table_keys`，由后端删除。
 *
 * 🔴 只登记**确定由 D1 推送过**的表名（同章节可能被别的底稿推送，越权删会打断对方）。
 * 守卫：`__tests__/d1NoteSubtableContract.spec.ts`（旧名不得复活为当前表名）。
 */
export const D1_LEGACY_OBSOLETE_TABLES: Record<D1DisclosureVariant, readonly string[]> = {
  listed: ['期末因出票人未履约而将其转应收账款的票据'],
  soe: [],
}

/**
 * 主表（分类总表）表名。
 *
 * 「校对附注」必须按此名定位附注里的主表再取合计行 —— 遍历所有表取第一个非零数
 * 会抓到「期末已质押的应收票据」的合计并误报差异（2026-07-30 实测）。
 */
export const D1_MAIN_SUBTABLE = {
  listed: T.listed.main,
  soe: T.soe.main,
} as const satisfies Record<D1DisclosureVariant, string>

// ─── 列头元数据（逐字取自附注模板 headers + 源模板两级表头合并单元格）────────
//
// 🔴 表态铁律（与 `fix_note_d1_notes_receivable_structure.py` 同口径）：
//   **同表并列双期 → `group`；拆表双期 / 单期 → `flat`**。
//   期间已在表名里时（如「（期末余额）」「（续：期初数）」），单组跨全部数据列
//   不携带分组信息，且必须显式 `flat` 抑制后端 `_infer_groups_from_headers` 前缀推断。
// 🔴 `group` 禁止含 `/`：后端会走树形分支（`children`/`headerIdx`），
//   而前端 `DisclosureEditor.activeTableColumns` 只认扁平 `{group,start,span}` → 渲染崩。
const AMT = 'amount' as const
const PCT = 'percent' as const
const TXT = 'text' as const

// 期间父表头（逐字取自源模板合并单元格：上市 B7:D7/E7:G7、国企 B6:D6/E6:G6）
const G_END_LISTED = '期末余额'
const G_PRIOR_LISTED = '上年年末余额'
const G_END_SOE = '期末数'
const G_PRIOR_SOE = '期初数'
const G_GROSS = '账面余额'
const G_PROVISION = '坏账准备'
const G_MOVEMENT_SOE = '本期变动情况'

/**
 * 分类总表列头：票据种类 × 双期并列 × 账面余额 / 坏账准备 / 账面价值。
 *
 * 源模板把期间标签写了两遍（父表头「期末余额」下首个子列也叫「期末余额」，
 * 国企侧「期初数」下子列叫「年初余额」），子列名按预设 F4-3a
 * （账面余额 − 坏账准备 = 账面价值）取，消除冗余。
 */
function summaryColumns(groupEnd: string, groupPrior: string): ColumnDef[] {
  return [
    { key: 'label', label: '票据种类', is_label: true },
    { key: 'end_balance', label: '账面余额', format: AMT, group: groupEnd },
    { key: 'end_provision', label: '坏账准备', format: AMT, group: groupEnd },
    { key: 'end_book_value', label: '账面价值', format: AMT, group: groupEnd },
    { key: 'prior_balance', label: '账面余额', format: AMT, group: groupPrior },
    { key: 'prior_provision', label: '坏账准备', format: AMT, group: groupPrior },
    { key: 'prior_book_value', label: '账面价值', format: AMT, group: groupPrior },
  ]
}
const SUMMARY_COLUMNS_LISTED: ColumnDef[] = summaryColumns(G_END_LISTED, G_PRIOR_LISTED)
const SUMMARY_COLUMNS_SOE: ColumnDef[] = summaryColumns(G_END_SOE, G_PRIOR_SOE)

const PLEDGED_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '种类', is_label: true, flat: true },
  { key: 'pledged_amount', label: '期末已质押金额', format: AMT },
]
const ENDORSED_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '种类', is_label: true, flat: true },
  { key: 'derecognized', label: '期末终止确认金额', format: AMT },
  { key: 'not_derecognized', label: '期末未终止确认金额', format: AMT },
]
const TRANSFER_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '种类', is_label: true, flat: true },
  { key: 'transfer_amount', label: '期末转应收账款金额', format: AMT },
]
/** 上市按坏账计提方法分类：源模板 B38:F38 合并为期间父表头，子列 5 个。 */
function classColumnsListed(group: string): ColumnDef[] {
  return [
    { key: 'label', label: '类别', is_label: true },
    { key: 'balance', label: '金额', format: AMT, group },
    { key: 'ratio', label: '比例(%)', format: PCT, group },
    { key: 'provision', label: '坏账准备', format: AMT, group },
    { key: 'loss_rate', label: '预期信用损失率(%)', format: PCT, group },
    { key: 'book_value', label: '账面价值', format: AMT, group },
  ]
}
/**
 * 国企按坏账准备计提方法分类：源模板是三级
 * （期间 > 账面余额·坏账准备 > 金额·比例）。顶层期间已在表名里
 * （（期末数）/（续：期初数）），只保留下两级；「账面价值」是 rowspan
 * 独立列（源模板 F14「账面」/ F15「价值」纵向合并），不进任何父表头。
 */
const CLASS_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '类别', is_label: true },
  { key: 'balance', label: '金额', format: AMT, group: G_GROSS },
  { key: 'ratio', label: '比例(%)', format: PCT, group: G_GROSS },
  { key: 'provision', label: '金额', format: AMT, group: G_PROVISION },
  { key: 'loss_rate', label: '预期信用损失率(%)', format: PCT, group: G_PROVISION },
  { key: 'book_value', label: '账面价值', format: AMT },
]
/** 单项计提明细（上市双期拆两张表、国企只期末）→ 单级表头。 */
function individualColumns(basisLabel: string): ColumnDef[] {
  return [
    { key: 'label', label: '名称', is_label: true, flat: true },
    { key: 'balance', label: '账面余额', format: AMT },
    { key: 'provision', label: '坏账准备', format: AMT },
    { key: 'loss_rate', label: '预期信用损失率(%)', format: PCT },
    { key: 'basis', label: basisLabel, format: TXT },
  ]
}
const INDIVIDUAL_COLUMNS_LISTED: ColumnDef[] = individualColumns('计提依据')
const INDIVIDUAL_COLUMNS_SOE: ColumnDef[] = individualColumns('计提理由')
/** 上市组合计提项目：一张表双期并列（源模板 B77:D77 / E77:G77 合并）。 */
const PORTFOLIO_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '名称', is_label: true },
  { key: 'end_balance', label: '应收票据', format: AMT, group: G_END_LISTED },
  { key: 'end_provision', label: '坏账准备', format: AMT, group: G_END_LISTED },
  { key: 'end_loss_rate', label: '预期信用损失率(%)', format: PCT, group: G_END_LISTED },
  { key: 'prior_balance', label: '应收票据', format: AMT, group: G_PRIOR_LISTED },
  { key: 'prior_provision', label: '坏账准备', format: AMT, group: G_PRIOR_LISTED },
  { key: 'prior_loss_rate', label: '预期信用损失率(%)', format: PCT, group: G_PRIOR_LISTED },
]
const PORTFOLIO_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '名称', is_label: true, flat: true },
  { key: 'balance', label: '账面余额', format: AMT },
  { key: 'provision', label: '坏账准备', format: AMT },
  { key: 'loss_rate', label: '预期信用损失率(%)', format: PCT },
]
const MOVEMENT_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: 'amount', label: '坏账准备金额', format: AMT },
]
/** 国企坏账准备变动：源模板 C46:F46 合并为「本期变动情况」，期初 / 期末为独立列。 */
const MOVEMENT_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '类别', is_label: true },
  { key: 'prior_balance', label: '期初数', format: AMT },
  { key: 'provision', label: '计提', format: AMT, group: G_MOVEMENT_SOE },
  { key: 'reversal', label: '收回或转回', format: AMT, group: G_MOVEMENT_SOE },
  { key: 'write_off', label: '核销', format: AMT, group: G_MOVEMENT_SOE },
  { key: 'other', label: '其他变动', format: AMT, group: G_MOVEMENT_SOE },
  { key: 'end_balance', label: '期末数', format: AMT },
]
/**
 * 重要转回或收回列头。上市 5 列、国企 4 列（模板 五、4[11] / 八、4[6] 结构本就不同，
 * 与披露表 D1TabDisclosure 两个变体的表头一一对应）。
 *
 * 国企「转回或收回前累计已计提坏账准备金额」在源模板里是**数值列**
 * （C59==SUM(C55:C58)），故 `format: amount` 并取 `cumulativeProvision` 数值字段。
 */
function reversalColumns(variant: D1DisclosureVariant): ColumnDef[] {
  if (variant === 'soe') {
    return [
      { key: 'label', label: '债务人名称', is_label: true, flat: true },
      { key: 'amount', label: '转回或收回金额', format: AMT },
      { key: 'cumulative_provision', label: '转回或收回前累计已计提坏账准备金额', format: AMT },
      { key: 'reason_method', label: '转回或收回原因、方式', format: TXT },
    ]
  }
  return [
    { key: 'label', label: '单位名称', is_label: true, flat: true },
    { key: 'reversal_reason', label: '转回原因', format: TXT },
    { key: 'recovery_method', label: '收回方式', format: TXT },
    { key: 'original_basis', label: '原确定坏账准备的依据', format: TXT },
    { key: 'amount', label: '转回或收回金额', format: AMT },
  ]
}
const WRITEOFF_AMOUNT_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: 'amount', label: '核销金额', format: AMT },
]
/**
 * 重要核销逐项披露列头（上市/国企措辞按各自模板逐字，字段键相同）。
 *
 * 上市源模板 B111 字面是「应收票据」，预设 F4-29 明确为「应收票据性质」→ 取预设。
 */
function writeOffDetailColumns(variant: D1DisclosureVariant): ColumnDef[] {
  return [
    { key: 'label', label: '单位名称', is_label: true, flat: true },
    { key: 'note_type', label: variant === 'soe' ? '应收票据的性质' : '应收票据性质', format: TXT },
    { key: 'amount', label: '核销金额', format: AMT },
    { key: 'reason', label: '核销原因', format: TXT },
    { key: 'procedure', label: '履行的核销程序', format: TXT },
    { key: 'related', label: variant === 'soe' ? '是否由关联交易产生' : '款项是否由关联交易产生', format: TXT },
  ]
}

// ─── 快照行类型（组件层传入，字段与 useD1Disclosure 行接口对齐）───────────────
export interface D1SummaryRowLike { category: string; endBalance: number; endProvision: number; endBookValue: number; priorBalance: number; priorProvision: number; priorBookValue: number }
export interface D1PledgedRowLike { category: string; pledgedAmount: number }
export interface D1EndorsedRowLike { category: string; derecognizedAmount: number; notDerecognizedAmount: number }
export interface D1TransferRowLike { category: string; transferAmount: number }
export interface D1ClassRowLike { label: string; balance: number; ratio: number; provision: number; lossRate: number; bookValue: number }
export interface D1IndividualRowLike { name: string; balance: number; provision: number; lossRate: number; basis?: string }
export interface D1PortfolioRowLike { drawerTypeOrAging: string; balance: number; provision: number; lossRate: number }
export interface D1SoePortfolioRowLike { name: string; balance: number; provision: number; lossRate: number; isTotal?: boolean }
export interface D1MovementRowLike { label?: string; priorBalance: number; provision: number; reversal: number; writeOff: number; transfer: number; other: number; endBalance: number }
export interface D1ReversalRowLike {
  companyName: string
  reversalReason: string
  originalMethod: string
  reversalBasis: string
  amount: number
  /** 国企「转回或收回前累计已计提坏账准备金额」（源模板 C 列是 SUM 数值列） */
  cumulativeProvision?: number
}
export interface D1WriteOffDetailRowLike { companyName: string; noteType: string; amount: number; reason: string; procedure: string; relatedPartyFlag: string }

export interface D1DisclosureSnapshot {
  summaryRows: D1SummaryRowLike[]
  summaryTotal: D1SummaryRowLike
  pledgedRows: D1PledgedRowLike[]
  pledgedTotal: D1PledgedRowLike
  endorsedRows: D1EndorsedRowLike[]
  endorsedTotal: D1EndorsedRowLike
  transferRows: D1TransferRowLike[]
  transferTotal: D1TransferRowLike
  /** 按坏账计提方法分类（原始三行，作 classDisplay* 缺省时的回退） */
  classEndRows: D1ClassRowLike[]
  classPriorRows: D1ClassRowLike[]
  /** 披露表实际渲染的分类展开行（按单项/其中：/单项明细/按组合/银承/商承/合计），优先使用 */
  classDisplayEndRows?: D1ClassRowLike[]
  classDisplayPriorRows?: D1ClassRowLike[]
  /** 国企版分类三行（单项/组合/合计） */
  soeClassEndRows?: D1ClassRowLike[]
  soeClassPriorRows?: D1ClassRowLike[]
  /** 单项计提明细 */
  individualEndRows?: D1IndividualRowLike[]
  individualPriorRows?: D1IndividualRowLike[]
  /** 组合计提明细（上市版按票据种类 × 期末/上年末） */
  bankPortfolioEndRows?: D1PortfolioRowLike[]
  bankPortfolioPriorRows?: D1PortfolioRowLike[]
  commercialPortfolioEndRows?: D1PortfolioRowLike[]
  commercialPortfolioPriorRows?: D1PortfolioRowLike[]
  /** 国企版组合计提（小计+明细+合计，取自披露表 soeAgingRows） */
  soePortfolioRows?: D1SoePortfolioRowLike[]
  /** 坏账准备变动：上市版取合计行；国企版按类别多行 */
  movementTotal?: D1MovementRowLike
  soeMovementRows?: D1MovementRowLike[]
  /** 重要转回或收回的坏账准备 */
  reversalRows?: D1ReversalRowLike[]
  reversalTotal?: D1ReversalRowLike
  writeOffAmount: number
  writeOffDetailRows: D1WriteOffDetailRowLike[]
  /** 各子节说明文本（文本框内容），与披露表保持一致后同步到附注 text_content */
  notes: Record<string, string>
}

export interface D1SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)
const str = (v: unknown): string => String(v ?? '')
/**
 * 比率列内部存分数（0.01），披露表 UI 用 fmtPct 乘 100 展示；
 * 附注列头是「比例(%)/预期信用损失率(%)」，故同步时统一换算为百分数，
 * 保证附注显示口径与披露表一致（不出现 0.01 挂在 % 表头下）。
 */
const pct = (v: unknown): number => num(v) * 100
/**
 * 由**合计金额**现算比率并换算为百分数（源模板 `IFERROR(C82/B82,0)` 语义）。
 *
 * 用于合计行：比率不可加，必须用合计分子 ÷ 合计分母重算；分母为 0 返回 0。
 */
const ratePercent = (part: unknown, whole: unknown): number => {
  const w = num(whole)
  if (w === 0) return 0
  return (num(part) / w) * 100
}
const ZERO_MOVEMENT: D1MovementRowLike = {
  priorBalance: 0, provision: 0, reversal: 0, writeOff: 0, transfer: 0, other: 0, endBalance: 0,
}

/** 合并期末/上年末组合明细（按名称对齐，缺失侧为 0）。 */
function mergePortfolio(
  endRows: D1PortfolioRowLike[] | undefined,
  priorRows: D1PortfolioRowLike[] | undefined,
): Array<Record<string, unknown>> {
  const end = endRows ?? []
  const prior = priorRows ?? []
  const names: string[] = []
  const pick = (r: D1PortfolioRowLike) => str(r.drawerTypeOrAging)
  for (const r of [...end, ...prior]) {
    const n = pick(r)
    if (!names.includes(n)) names.push(n)
  }
  const rows = names.map((n) => {
    const e = end.find((r) => pick(r) === n)
    const p = prior.find((r) => pick(r) === n)
    return {
      label: n,
      end_balance: num(e?.balance),
      end_provision: num(e?.provision),
      end_loss_rate: pct(e?.lossRate),
      prior_balance: num(p?.balance),
      prior_provision: num(p?.provision),
      prior_loss_rate: pct(p?.lossRate),
    }
  })
  const sum = (k: 'end_balance' | 'end_provision' | 'prior_balance' | 'prior_provision') =>
    rows.reduce((s, r) => s + num(r[k]), 0)
  const endBalanceSum = sum('end_balance')
  const endProvisionSum = sum('end_provision')
  const priorBalanceSum = sum('prior_balance')
  const priorProvisionSum = sum('prior_provision')
  rows.push({
    label: '合计',
    end_balance: endBalanceSum,
    end_provision: endProvisionSum,
    // 🔴 合计行损失率必须**按合计金额现算**（源模板 D82/G82/D89/G89 = 合计坏账 ÷ 合计余额）：
    //    改造前硬编码 0 → 附注组合表合计行的预期信用损失率恒显示 0.00%；
    //    也不能把各行损失率相加（比率不可加）。
    end_loss_rate: ratePercent(endProvisionSum, endBalanceSum),
    prior_balance: priorBalanceSum,
    prior_provision: priorProvisionSum,
    prior_loss_rate: ratePercent(priorProvisionSum, priorBalanceSum),
    is_total: true,
  } as Record<string, unknown>)
  return rows
}

/** 单项计提明细 → 行（附合计）。 */
function individualTable(rows: D1IndividualRowLike[] | undefined): Array<Record<string, unknown>> {
  const list = rows ?? []
  const out: Array<Record<string, unknown>> = list.map((r) => ({
    label: str(r.name),
    balance: num(r.balance),
    provision: num(r.provision),
    loss_rate: pct(r.lossRate),
    basis: str(r.basis),
  }))
  const balanceSum = list.reduce((s, r) => s + num(r.balance), 0)
  const provisionSum = list.reduce((s, r) => s + num(r.provision), 0)
  out.push({
    label: '合计',
    balance: balanceSum,
    provision: provisionSum,
    // 源模板 D68=IFERROR(C68/B68,0) / D74 —— 单项计提表合计行的损失率是有公式的，
    // 改造前硬编码 0（附注恒显示 0.00%）。
    loss_rate: ratePercent(provisionSum, balanceSum),
    basis: '',
    is_total: true,
  })
  return out
}

/**
 * 重要转回或收回 → 行（附合计）。
 * 国企列结构与上市不同（见 reversalColumns）：披露表国企版把
 * `cumulativeProvision` 绑在「转回或收回前累计已计提坏账准备金额」（源模板 C59==SUM
 * → 数值列，进合计行）、`reversalReason` 绑在「转回或收回原因、方式」，
 * 故按变体产出对应字段键，不硬套上市结构。
 */
function reversalTable(
  variant: D1DisclosureVariant,
  rows: D1ReversalRowLike[] | undefined,
  total: D1ReversalRowLike | undefined,
): Array<Record<string, unknown>> {
  const list = rows ?? []
  const sumAmount = total ? num(total.amount) : list.reduce((s, r) => s + num(r.amount), 0)
  if (variant === 'soe') {
    const out: Array<Record<string, unknown>> = list.map((r) => ({
      label: str(r.companyName),
      amount: num(r.amount),
      cumulative_provision: num(r.cumulativeProvision),
      reason_method: str(r.reversalReason),
    }))
    out.push({
      label: '合计',
      amount: sumAmount,
      cumulative_provision: list.reduce((s, r) => s + num(r.cumulativeProvision), 0),
      reason_method: '',
      is_total: true,
    })
    return out
  }
  const out: Array<Record<string, unknown>> = list.map((r) => ({
    label: str(r.companyName),
    reversal_reason: str(r.reversalReason),
    recovery_method: str(r.originalMethod),
    original_basis: str(r.reversalBasis),
    amount: num(r.amount),
  }))
  out.push({
    label: '合计',
    reversal_reason: '',
    recovery_method: '',
    original_basis: '',
    amount: sumAmount,
    is_total: true,
  })
  return out
}

/**
 * 某变体全部子表的列头元数据（`{模板表名: ColumnDef[]}`）。
 *
 * `buildD1SyncPayload` 的 `columns` 直接取自本函数（**单一真源**，
 * 避免载荷与契约测试各写一套导致漂移）。契约测试用零参
 * `buildD1ListedColumns()` / `buildD1SoeColumns()` 消费。
 */
function d1ColumnsFor(variant: D1DisclosureVariant): Record<string, ColumnDef[]> {
  const isSoe = variant === 'soe'
  const names = isSoe ? T.soe : T.listed
  const out: Record<string, ColumnDef[]> = {
    [names.main]: isSoe ? SUMMARY_COLUMNS_SOE : SUMMARY_COLUMNS_LISTED,
    [names.classEnd]: isSoe ? CLASS_COLUMNS_SOE : classColumnsListed(G_END_LISTED),
    [names.classPrior]: isSoe ? CLASS_COLUMNS_SOE : classColumnsListed(G_PRIOR_LISTED),
    [names.individualEnd]: isSoe ? INDIVIDUAL_COLUMNS_SOE : INDIVIDUAL_COLUMNS_LISTED,
    [names.movement]: isSoe ? MOVEMENT_COLUMNS_SOE : MOVEMENT_COLUMNS_LISTED,
    [names.reversal]: reversalColumns(variant),
    [names.pledged]: PLEDGED_COLUMNS,
    [names.endorsed]: ENDORSED_COLUMNS,
    [names.transfer]: TRANSFER_COLUMNS,
    [names.writeOffAmount]: WRITEOFF_AMOUNT_COLUMNS,
    [names.writeOffDetail]: writeOffDetailColumns(variant),
  }
  if (isSoe) {
    out[T.soe.portfolio] = PORTFOLIO_COLUMNS_SOE
  } else {
    out[T.listed.individualPrior] = INDIVIDUAL_COLUMNS_LISTED
    out[T.listed.portfolioBank] = PORTFOLIO_COLUMNS_LISTED
    out[T.listed.portfolioCommercial] = PORTFOLIO_COLUMNS_LISTED
  }
  return out
}

/** 上市 五、4 全部子表列头（零参，供契约测试 sweep）。 */
export function buildD1ListedColumns(): Record<string, ColumnDef[]> {
  return d1ColumnsFor('listed')
}
/** 国企 八、4 全部子表列头（零参，供契约测试 sweep）。 */
export function buildD1SoeColumns(): Record<string, ColumnDef[]> {
  return d1ColumnsFor('soe')
}

/**
 * 构建 D1 → 附注 sync-from-workpaper 载荷。
 * 覆盖披露表全部表格（上市 14 张 / 国企 12 张，与附注模板表名逐字一致）+ 全部子节说明文本。
 */
export function buildD1SyncPayload(
  variant: D1DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snapshot: D1DisclosureSnapshot,
): D1SyncPayload {
  const isSoe = variant === 'soe'
  const names = isSoe ? T.soe : T.listed
  const colsMap = d1ColumnsFor(variant)
  const subTableData: Record<string, unknown> = {}
  const columns: Record<string, ColumnDef[]> = {}
  /** 列头统一取自 `d1ColumnsFor`（单一真源）；`cols` 入参仅作断言用途保留。 */
  const put = (name: string, rows: unknown, cols?: ColumnDef[]) => {
    subTableData[name] = rows
    columns[name] = colsMap[name] ?? cols ?? []
  }

  // ① 主表（票据种类分类）
  const summaryRow = (r: D1SummaryRowLike, isTotal = false) => ({
    label: str(r.category),
    end_balance: num(r.endBalance),
    end_provision: num(r.endProvision),
    end_book_value: num(r.endBookValue),
    prior_balance: num(r.priorBalance),
    prior_provision: num(r.priorProvision),
    prior_book_value: num(r.priorBookValue),
    ...(isTotal ? { is_total: true } : {}),
  })
  put(
    names.main,
    [...snapshot.summaryRows.map((r) => summaryRow(r)), summaryRow(snapshot.summaryTotal, true)],
    isSoe ? SUMMARY_COLUMNS_SOE : SUMMARY_COLUMNS_LISTED,
  )

  // ② 按坏账计提方法分类（期末 / 上年年末·期初）
  const classRow = (r: D1ClassRowLike) => ({
    label: str(r.label),
    balance: num(r.balance),
    ratio: pct(r.ratio),
    provision: num(r.provision),
    loss_rate: pct(r.lossRate),
    book_value: num(r.bookValue),
    ...(r.label === '合计' ? { is_total: true } : {}),
  })
  const classEnd = isSoe
    ? (snapshot.soeClassEndRows ?? snapshot.classEndRows)
    : (snapshot.classDisplayEndRows ?? snapshot.classEndRows)
  const classPrior = isSoe
    ? (snapshot.soeClassPriorRows ?? snapshot.classPriorRows)
    : (snapshot.classDisplayPriorRows ?? snapshot.classPriorRows)
  // 上市分类表拆两张、期间父表头各自不同（源模板 B38:F38 / B51:F51）；
  // 国企两张表同构（期间在表名里，父表头是 账面余额 / 坏账准备）。
  put(
    names.classEnd,
    classEnd.map(classRow),
    isSoe ? CLASS_COLUMNS_SOE : classColumnsListed(G_END_LISTED),
  )
  put(
    names.classPrior,
    classPrior.map(classRow),
    isSoe ? CLASS_COLUMNS_SOE : classColumnsListed(G_PRIOR_LISTED),
  )

  // ③ 单项计提明细
  put(
    names.individualEnd,
    individualTable(snapshot.individualEndRows),
    isSoe ? INDIVIDUAL_COLUMNS_SOE : INDIVIDUAL_COLUMNS_LISTED,
  )
  if (!isSoe) {
    put(T.listed.individualPrior, individualTable(snapshot.individualPriorRows), INDIVIDUAL_COLUMNS_LISTED)
  }

  // ④ 组合计提明细
  if (isSoe) {
    // 🔴 `loss_rate` 必须 `pct()`（×100）：披露表 `soeAgingRows` 的 `lossRate` 由
    //    `ratioOf` 产出**分数**（0.0575），而附注列头是「预期信用损失率(%)」且同版
    //    分类表已按 `pct()` 推送 —— 改造前这里漏乘 100，附注该表显示 0.06 而不是 5.75，
    //    与源模板国企侧 `D36/D39/D42 = C/B*100` 也不一致。
    const rows = (snapshot.soePortfolioRows ?? []).map((r) => ({
      label: str(r.name),
      balance: num(r.balance),
      provision: num(r.provision),
      loss_rate: pct(r.lossRate),
      ...(r.isTotal || r.name === '合计' ? { is_total: true } : {}),
    }))
    put(T.soe.portfolio, rows, PORTFOLIO_COLUMNS_SOE)
  } else {
    put(
      T.listed.portfolioBank,
      mergePortfolio(snapshot.bankPortfolioEndRows, snapshot.bankPortfolioPriorRows),
      PORTFOLIO_COLUMNS_LISTED,
    )
    put(
      T.listed.portfolioCommercial,
      mergePortfolio(snapshot.commercialPortfolioEndRows, snapshot.commercialPortfolioPriorRows),
      PORTFOLIO_COLUMNS_LISTED,
    )
  }

  // ⑤ 坏账准备变动
  if (isSoe) {
    const rows = (snapshot.soeMovementRows ?? []).map((r) => ({
      label: str(r.label),
      prior_balance: num(r.priorBalance),
      provision: num(r.provision),
      reversal: num(r.reversal),
      write_off: num(r.writeOff),
      other: num(r.other) + num(r.transfer),
      end_balance: num(r.endBalance),
      ...(r.label === '合计' ? { is_total: true } : {}),
    }))
    put(T.soe.movement, rows, MOVEMENT_COLUMNS_SOE)
  } else {
    const m = snapshot.movementTotal ?? ZERO_MOVEMENT
    put(
      T.listed.movement,
      [
        { label: '上年年末数', amount: num(m.priorBalance) },
        { label: '本期计提', amount: num(m.provision) },
        { label: '本期收回或转回', amount: num(m.reversal) },
        { label: '本期核销', amount: num(m.writeOff) },
        { label: '本期转销', amount: num(m.transfer) },
        { label: '其他', amount: num(m.other) },
        { label: '期末数', amount: num(m.endBalance), is_total: true },
      ],
      MOVEMENT_COLUMNS_LISTED,
    )
  }
  put(
    names.reversal,
    reversalTable(variant, snapshot.reversalRows, snapshot.reversalTotal),
    reversalColumns(variant),
  )

  // ⑥ 质押 / 背书贴现 / 转应收账款
  put(
    names.pledged,
    [
      ...snapshot.pledgedRows.map((r) => ({ label: str(r.category), pledged_amount: num(r.pledgedAmount) })),
      { label: snapshot.pledgedTotal.category || '合计', pledged_amount: num(snapshot.pledgedTotal.pledgedAmount), is_total: true },
    ],
    PLEDGED_COLUMNS,
  )
  put(
    names.endorsed,
    [
      ...snapshot.endorsedRows.map((r) => ({
        label: str(r.category),
        derecognized: num(r.derecognizedAmount),
        not_derecognized: num(r.notDerecognizedAmount),
      })),
      {
        label: snapshot.endorsedTotal.category || '合计',
        derecognized: num(snapshot.endorsedTotal.derecognizedAmount),
        not_derecognized: num(snapshot.endorsedTotal.notDerecognizedAmount),
        is_total: true,
      },
    ],
    ENDORSED_COLUMNS,
  )
  put(
    names.transfer,
    [
      ...snapshot.transferRows.map((r) => ({ label: str(r.category), transfer_amount: num(r.transferAmount) })),
      { label: snapshot.transferTotal.category || '合计', transfer_amount: num(snapshot.transferTotal.transferAmount), is_total: true },
    ],
    TRANSFER_COLUMNS,
  )

  // ⑦ 核销（金额表 + 逐项披露明细，对应模板两张独立表）
  put(
    names.writeOffAmount,
    [{ label: '实际核销的应收票据', amount: num(snapshot.writeOffAmount) }],
    WRITEOFF_AMOUNT_COLUMNS,
  )
  put(
    names.writeOffDetail,
    [
      ...snapshot.writeOffDetailRows.map((r) => ({
        label: str(r.companyName),
        note_type: str(r.noteType),
        amount: num(r.amount),
        reason: str(r.reason),
        procedure: str(r.procedure),
        related: str(r.relatedPartyFlag),
      })),
      {
        label: '合计',
        note_type: '',
        amount: snapshot.writeOffDetailRows.reduce((s, r) => s + num(r.amount), 0),
        reason: '',
        procedure: '',
        related: '',
        is_total: true,
      },
    ],
    writeOffDetailColumns(variant),
  )

  // ⑧ 文本框内容
  subTableData._note_texts = buildNoteTexts(snapshot.notes)

  // ⑨ 孤儿子表清理：改名/退役的历史表名交后端删除。
  //    与本次推送键求差集 —— 若某历史名又成了当前表名（改回去），绝不能删掉刚推的表。
  const pushed = new Set(Object.keys(subTableData))
  const removed = D1_LEGACY_OBSOLETE_TABLES[variant].filter((k) => !pushed.has(k))
  if (removed.length) subTableData._removed_table_keys = removed

  return {
    wp_id: wpId,
    sheet_name: D1_DISCLOSURE_SHEET_NAME[variant],
    section_id: D1_NOTE_SECTION[variant],
    current_standard: resolveD1CurrentStandard(variant, applicableStandards),
    sub_table_data: subTableData,
    columns,
  }
}

/**
 * 子节说明标题（附注 `text_content` 的小节名）。
 *
 * 🔴 必须与披露表 `NOTE_SECTION_KEYS` 键集**一一对应**：少一个键 = 该段说明
 * 同步不到附注（`buildNoteTexts` 按 `NOTE_TEXT_ORDER` 遍历，缺键即静默丢失）。
 */
const NOTE_TITLES: Record<string, string> = {
  top: '应收票据说明',
  pledged: '已质押应收票据说明',
  endorsed: '已背书或贴现应收票据说明',
  transfer: '因出票人未履约转应收账款说明',
  badDebtClass: '坏账准备计提说明',
  badDebtMovement: '坏账准备变动说明',
  writeOff: '应收票据核销说明',
}

/** 说明小节输出顺序（与源模板小节顺序一致）；导出供守卫比对披露表键集。 */
export const D1_NOTE_TEXT_ORDER = [
  'top', 'pledged', 'endorsed', 'transfer', 'badDebtClass', 'badDebtMovement', 'writeOff',
] as const

/** 各子节说明 → _note_texts（仅非空），保证附注 text_content 与披露表文本框一致。 */
export function buildNoteTexts(notes: Record<string, string>): Array<{ section: string; title: string; text: string }> {
  const order = D1_NOTE_TEXT_ORDER
  const out: Array<{ section: string; title: string; text: string }> = []
  for (const key of order) {
    const text = String(notes?.[key] ?? '').trim()
    if (text) out.push({ section: `note-${key}`, title: NOTE_TITLES[key] ?? key, text })
  }
  return out
}
