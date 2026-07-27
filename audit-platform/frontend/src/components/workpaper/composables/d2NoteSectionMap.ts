/**
 * D2 应收账款披露 ↔ 附注章节冻结映射与 sync payload 构建
 *
 * 权威来源：note_template_listed.json 五、5 / note_template_soe.json 八、5「应收账款」
 * （表名/列头逐字对照模板；行数据来自 D2 底稿「附注披露信息(上市公司)/(国企)」披露表）。
 *
 * 底稿 → 附注单向推送（sync_from_workpaper）：
 *  - sub_table_data 各子表 → 附注 table_data.sub_table_data（读时投影为 _tables 渲染）
 *  - sub_table_data._note_texts → 附注 text_content（文本框内容与披露表保持一致）
 *  - columns → _sub_table_columns（投影器据此产出扁平表头，附注模块渲染）
 *
 * 🔴 覆盖必须完整：note_sub_table_projector 对 `_source=workpaper` 的附注
 * **只渲染 sub_table_data 里推送过的子表**（不与模板 _tables 合并），故逐张覆盖。
 *
 * 🔴 与模板字面值的偏差（仅以下 4 处，全部为渲染必需，不新增/不删减任何表与数据列）：
 *  1. 模板里两张表字面名都叫「续：」（上年年末余额续表），而 sub_table_data 的键必须唯一
 *     → 续表键补全为「XXX（续：上年年末余额）」。
 *  2. 上市前五名表模板 name 字面是「单位名称」（模板把首列名当表名），真实标题在
 *     text_sections「### 按欠款方归集的应收账款和合同资产期末余额前五名单位情况」
 *     → 表名取该章节标题（更可读，避免附注里出现名为「单位名称」的表）。
 *  3. 模板列头里的 HTML 换行 `<br/>`（如「转回或收回<br/>金额」）去掉，文字逐字保留。
 *  4. 模板部分表 headers 省略了标签列（上市组合计提分表 headers 只有 2 个金额列、
 *     上市坏账变动表只有「坏账准备金额」），而行本身带 label（1年以内 / 期初余额…）
 *     → 标签列列头分别取「账龄」「项目」（与国企同类表模板列头一致），金额列逐字照抄。
 *
 * 覆盖完整性（对照模板）：上市 五、5 共 15 张 = 10 张固定 + 5 张示例组合分表；
 * 国企 八、5 共 11 张 = 9 张固定 + 2 张示例组合分表。本文件固定表 10 / 9 张全覆盖，
 * 组合分表按项目实际组合动态生成（模板里的组合名只是示例）。
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type D2DisclosureVariant = 'listed' | 'soe'

export const D2_NOTE_SECTION = {
  listed: '五、5',
  soe: '八、5',
} as const satisfies Record<D2DisclosureVariant, string>

// 底稿披露 sheet 真实 tab 名（半角括号，见 workpaper_sheet_classification wp_code=D2-*）。
export const D2_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息(上市公司)',
  soe: '附注披露信息(国企)',
} as const satisfies Record<D2DisclosureVariant, string>

export function resolveD2CurrentStandard(
  variant: D2DisclosureVariant,
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

// ─── 表名（逐字取自附注模板 五、5 / 八、5，续表键补全见文件头说明）────────────
export const D2_TABLE_NAMES = {
  listed: {
    aging: '按账龄披露',
    classEnd: '按坏账计提方法分类披露',
    classPrior: '按坏账计提方法分类披露（续：上年年末余额）',
    individualEnd: '按单项计提坏账准备的应收账款',
    individualPrior: '按单项计提坏账准备的应收账款（续：上年年末余额）',
    movement: '本期计提、收回或转回的坏账准备情况',
    reversal: '转回或收回金额重要的坏账准备',
    writeOffAmount: '本期实际核销的应收账款情况',
    writeOffDetail: '重要的应收账款核销情况（逐项披露）',
    top5: '按欠款方归集的应收账款和合同资产期末余额前五名单位情况',
  },
  soe: {
    aging: '（1）按账龄披露应收账款',
    classEnd: '（2）按坏账准备计提方法分类披露应收账款',
    individualEnd: '期末单项计提坏账准备的应收账款',
    otherPortfolio: '采用余额百分比或其他组合方法计提坏账准备的应收账款',
    movement: '（3）本期计提、收回或转回的坏账准备情况',
    reversal: '收回或转回的坏账准备',
    writeOffDetail: '（4）本期实际核销的应收账款',
    top5: '（5）按欠款方归集的期末余额前五名的应收账款',
    derecognized: '（6）由金融资产转移而终止确认的应收账款',
  },
} as const

/** 组合计提项目分表名（模板：组合计提项目：应收中央企业客户 等）。 */
export function portfolioTableName(portfolioName: string): string {
  return `组合计提项目：${String(portfolioName || '').trim() || '未命名组合'}`
}

// ─── 列头元数据（逐字取自附注模板 headers）────────────────────────────────────
const AMT = 'amount' as const
const PCT = 'percent' as const
const TXT = 'text' as const

const AGING_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '账龄', is_label: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
  { key: 'prior_amount', label: '上年年末余额', format: AMT },
]
const AGING_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '账龄', is_label: true },
  { key: 'end_amount', label: '期末数', format: AMT },
  { key: 'prior_amount', label: '期初数', format: AMT },
]
const CLASS_COLUMNS_LISTED_END: ColumnDef[] = [
  { key: 'label', label: '类别', is_label: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
]
const CLASS_COLUMNS_LISTED_PRIOR: ColumnDef[] = [
  { key: 'label', label: '类别', is_label: true },
  { key: 'prior_amount', label: '上年年末余额', format: AMT },
]
const CLASS_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '类 别', is_label: true },
  { key: 'book_amount', label: '金额', format: AMT, group: '账面金额' },
  { key: 'ratio', label: '比例(%)', format: PCT, group: '账面金额' },
  { key: 'provision', label: '金额', format: AMT, group: '坏账准备' },
  { key: 'loss_rate', label: '预期信用损失率(%)', format: PCT, group: '坏账准备' },
  { key: 'carrying_value', label: '账面价值', format: AMT },
]
const CLASS_COLUMNS_SOE_PRIOR: ColumnDef[] = [
  { key: 'label', label: '类 别', is_label: true },
  { key: 'book_amount', label: '金额', format: AMT, group: '账面金额' },
  { key: 'ratio', label: '比例(%)', format: PCT, group: '账面金额' },
  { key: 'provision', label: '金额', format: AMT, group: '坏账准备' },
  { key: 'loss_rate', label: '预期信用损失率(%)', format: PCT, group: '坏账准备' },
  { key: 'carrying_value', label: '账面价值', format: AMT },
]
const INDIVIDUAL_COLUMNS_LISTED_END: ColumnDef[] = [
  { key: 'label', label: '名称', is_label: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
]
const INDIVIDUAL_COLUMNS_LISTED_PRIOR: ColumnDef[] = [
  { key: 'label', label: '名称', is_label: true },
  { key: 'prior_amount', label: '上年年末余额', format: AMT },
]
const INDIVIDUAL_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '债务人名称', is_label: true },
  { key: 'end_amount', label: '账面余额', format: AMT },
  { key: 'provision', label: '坏账准备', format: AMT },
  { key: 'aging', label: '账龄', format: TXT },
  { key: 'loss_rate', label: '预期信用损失率（%）', format: PCT },
  { key: 'basis', label: '计提理由', format: TXT },
]
const OTHER_PORTFOLIO_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '组合名称', is_label: true },
  { key: 'end_amount', label: '期末数', format: AMT },
  { key: 'prior_amount', label: '期初数', format: AMT },
]
const MOVEMENT_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'amount', label: '坏账准备金额', format: AMT },
]
const MOVEMENT_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '类 别', is_label: true },
  { key: 'prior_amount', label: '期初数', format: AMT },
  { key: 'provision_amount', label: '本期计提', format: AMT },
  { key: 'reversal_amount', label: '收回或转回', format: AMT },
  { key: 'writeoff_amount', label: '转销或核销', format: AMT },
  { key: 'end_amount', label: '期末数', format: AMT },
]
const REVERSAL_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '单位名称', is_label: true },
  { key: 'reversal_reason', label: '转回原因', format: TXT },
  { key: 'recovery_method', label: '收回方式', format: TXT },
  { key: 'original_basis', label: '原确定坏账准备的依据', format: TXT },
  { key: 'amount', label: '转回或收回金额', format: AMT },
]
const REVERSAL_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '债务人名称', is_label: true },
  { key: 'amount', label: '转回或收回金额', format: AMT },
  { key: 'cumulative_provision', label: '转回或收回前累计已计提坏账准备金额', format: AMT },
  { key: 'reason_method', label: '转回或收回原因、方式', format: TXT },
]
const WRITEOFF_AMOUNT_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'amount', label: '核销金额', format: AMT },
]
const WRITEOFF_DETAIL_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '单位名称', is_label: true },
  { key: 'nature', label: '应收账款性质', format: TXT },
  { key: 'amount', label: '核销金额', format: AMT },
  { key: 'reason', label: '核销原因', format: TXT },
  { key: 'procedure', label: '履行的核销程序', format: TXT },
  { key: 'related', label: '款项是否由关联交易产生', format: TXT },
]
const WRITEOFF_DETAIL_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '债务人名称', is_label: true },
  { key: 'nature', label: '应收账款性质', format: TXT },
  { key: 'amount', label: '核销金额', format: AMT },
  { key: 'reason', label: '核销原因', format: TXT },
  { key: 'procedure', label: '履行的核销程序', format: TXT },
  { key: 'related', label: '是否因关联交易产生', format: TXT },
]
const TOP5_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '单位名称', is_label: true },
  { key: 'ar_amount', label: '应收账款期末余额', format: AMT },
  { key: 'contract_asset_amount', label: '合同资产期末余额', format: AMT },
  { key: 'total_amount', label: '应收账款和合同资产期末余额', format: AMT },
  { key: 'ratio', label: '占应收账款和合同资产期末余额合计数的比例%', format: PCT },
  { key: 'provision', label: '应收账款坏账准备和合同资产减值准备期末余额', format: AMT },
]
const TOP5_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '债务人名称', is_label: true },
  { key: 'ar_amount', label: '账面余额', format: AMT },
  { key: 'ratio', label: '占应收账款合计的比例（%）', format: PCT },
  { key: 'provision', label: '坏账准备', format: AMT },
]
const DERECOGNIZED_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '债务人名称', is_label: true },
  { key: 'amount', label: '终止确认金额', format: AMT },
  { key: 'gain_loss', label: '与终止确认相关的利得或损失（损失以“-”填列）', format: AMT },
]

// ─── 快照行类型（组件层传入）─────────────────────────────────────────────────
export interface D2TwoPeriodRowLike { label: string; endAmount: number; priorAmount: number; isTotal?: boolean }
export interface D2IndividualRowLike { name: string; endAmount: number; priorAmount?: number; provision?: number; aging?: string; lossRate?: number; basis?: string }
export interface D2PortfolioGroupLike { name: string; groupId?: string; rows: D2TwoPeriodRowLike[] }
export interface D2MovementLike { priorBalance: number; provision: number; reversal: number; writeOff: number; transfer: number; other: number; endBalance: number }
export interface D2MovementByCategoryLike { label: string; priorAmount: number; provisionAmount: number; reversalAmount: number; writeOffAmount: number; endAmount: number; isTotal?: boolean }
export interface D2ReversalRowLike { companyName: string; reversalReason?: string; recoveryMethod?: string; originalBasis?: string; cumulativeProvision?: number; amount: number }
export interface D2WriteOffRowLike { companyName: string; nature?: string; amount: number; reason?: string; procedure?: string; relatedParty?: string }
export interface D2Top5RowLike { companyName: string; arAmount: number; contractAssetAmount?: number; ratio: number; provision: number }
export interface D2DerecognizedRowLike { companyName: string; amount: number; gainLoss: number }

export interface D2DisclosureSnapshot {
  /** 账龄披露（含 1年以内小计/减：坏账准备/合计 等结构行，label 直接来自披露表） */
  agingRows: D2TwoPeriodRowLike[]
  /** 按坏账准备计提方法分类（单项/组合/其中：各组合/合计） */
  classRows: D2TwoPeriodRowLike[]
  /** 国企版 6 列分类宽表（期末数） */
  soeClassEndRows?: Array<{ label: string; bookAmount: number; ratio: number; provision: number; lossRate: number; carryingValue: number; isTotal?: boolean }>
  /** 国企版 6 列分类宽表（期初数） */
  soeClassPriorRows?: Array<{ label: string; bookAmount: number; ratio: number; provision: number; lossRate: number; carryingValue: number; isTotal?: boolean }>
  /** 单项计提明细 */
  individualRows: D2IndividualRowLike[]
  /** 组合计提项目（每个组合一张分表） */
  portfolios: D2PortfolioGroupLike[]
  /** 国企：采用余额百分比或其他组合方法计提 */
  otherPortfolioRows?: D2TwoPeriodRowLike[]
  /** 坏账准备变动（上市纵向 7 行口径） */
  movement: D2MovementLike
  /** 国企：按类别的坏账准备变动（期初/本期变动/期末） */
  movementByCategory?: D2MovementByCategoryLike[]
  reversalRows: D2ReversalRowLike[]
  writeOffAmount: number
  writeOffRows: D2WriteOffRowLike[]
  top5Rows: D2Top5RowLike[]
  /** 国企：由金融资产转移而终止确认的应收账款 */
  derecognizedRows?: D2DerecognizedRowLike[]
  /** 各子节说明文本（文本框内容），与披露表保持一致后同步到附注 text_content */
  notes: Record<string, string>
}

export interface D2SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)
const str = (v: unknown): string => String(v ?? '')
const isTotalLabel = (label: string): boolean => label === '合计'

function twoPeriodRow(r: D2TwoPeriodRowLike, opts: { end?: boolean; prior?: boolean } = { end: true, prior: true }) {
  const out: Record<string, unknown> = { label: str(r.label) }
  if (opts.end !== false) out.end_amount = num(r.endAmount)
  if (opts.prior !== false) out.prior_amount = num(r.priorAmount)
  if (r.isTotal || isTotalLabel(str(r.label))) out.is_total = true
  return out
}

/**
 * 构建 D2 → 附注 sync-from-workpaper 载荷。
 * 上市：五、5（10 张固定表 + N 张组合计提分表）；国企：八、5（9 张固定表 + N 张组合分表）。
 */
export function buildD2SyncPayload(
  variant: D2DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snapshot: D2DisclosureSnapshot,
): D2SyncPayload {
  const isSoe = variant === 'soe'
  const sub: Record<string, unknown> = {}
  const columns: Record<string, ColumnDef[]> = {}
  const put = (name: string, rows: unknown, cols: ColumnDef[]) => {
    sub[name] = rows
    columns[name] = cols
  }

  // ① 按账龄披露
  if (isSoe) {
    put(D2_TABLE_NAMES.soe.aging, snapshot.agingRows.map((r) => twoPeriodRow(r)), AGING_COLUMNS_SOE)
  } else {
    put(D2_TABLE_NAMES.listed.aging, snapshot.agingRows.map((r) => twoPeriodRow(r)), AGING_COLUMNS_LISTED)
  }

  // ② 按坏账准备计提方法分类（上市拆期末/上年年末两表；国企期末/期初各一张 6 列宽表）
  if (isSoe) {
    // 国企 6 列宽表
    const soeEnd = snapshot.soeClassEndRows ?? []
    const soePrior = snapshot.soeClassPriorRows ?? []
    put(
      D2_TABLE_NAMES.soe.classEnd,
      soeEnd.map((r) => ({
        label: str(r.label),
        book_amount: num(r.bookAmount),
        ratio: num(r.ratio),
        provision: num(r.provision),
        loss_rate: num(r.lossRate),
        carrying_value: num(r.carryingValue),
        ...(r.isTotal ? { is_total: true } : {}),
      })),
      CLASS_COLUMNS_SOE,
    )
    // 国企期初数表（表名「续：期初数」）
    put(
      `${D2_TABLE_NAMES.soe.classEnd}（续：期初数）`,
      soePrior.map((r) => ({
        label: str(r.label),
        book_amount: num(r.bookAmount),
        ratio: num(r.ratio),
        provision: num(r.provision),
        loss_rate: num(r.lossRate),
        carrying_value: num(r.carryingValue),
        ...(r.isTotal ? { is_total: true } : {}),
      })),
      CLASS_COLUMNS_SOE_PRIOR,
    )
  } else {
    put(
      D2_TABLE_NAMES.listed.classEnd,
      snapshot.classRows.map((r) => twoPeriodRow(r, { end: true, prior: false })),
      CLASS_COLUMNS_LISTED_END,
    )
    put(
      D2_TABLE_NAMES.listed.classPrior,
      snapshot.classRows.map((r) => twoPeriodRow(r, { end: false, prior: true })),
      CLASS_COLUMNS_LISTED_PRIOR,
    )
  }

  // ③ 单项计提明细
  const individuals = snapshot.individualRows ?? []
  if (isSoe) {
    put(
      D2_TABLE_NAMES.soe.individualEnd,
      [
        ...individuals.map((r) => ({
          label: str(r.name),
          end_amount: num(r.endAmount),
          provision: num(r.provision),
          aging: str(r.aging),
          loss_rate: num(r.lossRate),
          basis: str(r.basis),
        })),
        {
          label: '合计',
          end_amount: individuals.reduce((s, r) => s + num(r.endAmount), 0),
          provision: individuals.reduce((s, r) => s + num(r.provision), 0),
          aging: '',
          loss_rate: 0,
          basis: '',
          is_total: true,
        },
      ],
      INDIVIDUAL_COLUMNS_SOE,
    )
  } else {
    put(
      D2_TABLE_NAMES.listed.individualEnd,
      [
        ...individuals.map((r) => ({ label: str(r.name), end_amount: num(r.endAmount) })),
        { label: '合计', end_amount: individuals.reduce((s, r) => s + num(r.endAmount), 0), is_total: true },
      ],
      INDIVIDUAL_COLUMNS_LISTED_END,
    )
    put(
      D2_TABLE_NAMES.listed.individualPrior,
      [
        ...individuals.map((r) => ({ label: str(r.name), prior_amount: num(r.priorAmount) })),
        { label: '合计', prior_amount: individuals.reduce((s, r) => s + num(r.priorAmount), 0), is_total: true },
      ],
      INDIVIDUAL_COLUMNS_LISTED_PRIOR,
    )
  }

  // ④ 组合计提项目（每组合一张分表，表名随组合名动态）
  const agingCols = isSoe ? AGING_COLUMNS_SOE : AGING_COLUMNS_LISTED
  for (const group of snapshot.portfolios ?? []) {
    let name = portfolioTableName(group.name)
    if (name in sub) {
      // 同名组合：用 groupId 后缀区分，避免后一个组合被静默丢弃（数据不完整比重名更糟）
      const suffix = String(group.groupId || '').trim()
      const fallback = suffix ? `${name}（${suffix.slice(-6)}）` : ''
      if (fallback && !(fallback in sub)) {
        name = fallback
      } else {
        let i = 2
        while (`${name}（${i}）` in sub) i += 1
        name = `${name}（${i}）`
      }
    }
    put(name, (group.rows ?? []).map((r) => twoPeriodRow(r)), agingCols)
  }
  if (isSoe) {
    put(
      D2_TABLE_NAMES.soe.otherPortfolio,
      (snapshot.otherPortfolioRows ?? []).map((r) => twoPeriodRow(r)),
      OTHER_PORTFOLIO_COLUMNS_SOE,
    )
  }

  // ⑤ 坏账准备变动
  if (isSoe) {
    put(
      D2_TABLE_NAMES.soe.movement,
      (snapshot.movementByCategory ?? []).map((r) => ({
        label: str(r.label),
        prior_amount: num(r.priorAmount),
        provision_amount: num(r.provisionAmount),
        reversal_amount: num(r.reversalAmount),
        writeoff_amount: num(r.writeOffAmount),
        end_amount: num(r.endAmount),
        ...(r.isTotal || isTotalLabel(str(r.label)) ? { is_total: true } : {}),
      })),
      MOVEMENT_COLUMNS_SOE,
    )
  } else {
    const m = snapshot.movement
    put(
      D2_TABLE_NAMES.listed.movement,
      [
        { label: '期初余额', amount: num(m.priorBalance) },
        { label: '本期计提', amount: num(m.provision) },
        { label: '本期收回或转回', amount: num(m.reversal) },
        { label: '本期核销', amount: num(m.writeOff) },
        { label: '本期转销', amount: num(m.transfer) },
        { label: '其他', amount: num(m.other) },
        { label: '期末余额', amount: num(m.endBalance), is_total: true },
      ],
      MOVEMENT_COLUMNS_LISTED,
    )
  }

  // ⑥ 转回或收回金额重要的坏账准备
  const reversals = snapshot.reversalRows ?? []
  if (isSoe) {
    put(
      D2_TABLE_NAMES.soe.reversal,
      [
        ...reversals.map((r) => ({
          label: str(r.companyName),
          amount: num(r.amount),
          cumulative_provision: num(r.cumulativeProvision),
          reason_method: [str(r.reversalReason), str(r.recoveryMethod)].filter(Boolean).join('；'),
        })),
        {
          label: '合计',
          amount: reversals.reduce((s, r) => s + num(r.amount), 0),
          cumulative_provision: reversals.reduce((s, r) => s + num(r.cumulativeProvision), 0),
          reason_method: '',
          is_total: true,
        },
      ],
      REVERSAL_COLUMNS_SOE,
    )
  } else {
    put(
      D2_TABLE_NAMES.listed.reversal,
      [
        ...reversals.map((r) => ({
          label: str(r.companyName),
          reversal_reason: str(r.reversalReason),
          recovery_method: str(r.recoveryMethod),
          original_basis: str(r.originalBasis),
          amount: num(r.amount),
        })),
        {
          label: '合计',
          reversal_reason: '',
          recovery_method: '',
          original_basis: '',
          amount: reversals.reduce((s, r) => s + num(r.amount), 0),
          is_total: true,
        },
      ],
      REVERSAL_COLUMNS_LISTED,
    )
  }

  // ⑦ 核销（上市另有「本期实际核销的应收账款情况」金额表）
  const writeOffs = snapshot.writeOffRows ?? []
  if (!isSoe) {
    put(
      D2_TABLE_NAMES.listed.writeOffAmount,
      [{ label: '实际核销的应收账款', amount: num(snapshot.writeOffAmount) }],
      WRITEOFF_AMOUNT_COLUMNS,
    )
  }
  put(
    isSoe ? D2_TABLE_NAMES.soe.writeOffDetail : D2_TABLE_NAMES.listed.writeOffDetail,
    [
      ...writeOffs.map((r) => ({
        label: str(r.companyName),
        nature: str(r.nature),
        amount: num(r.amount),
        reason: str(r.reason),
        procedure: str(r.procedure),
        related: str(r.relatedParty),
      })),
      {
        label: '合计',
        nature: '',
        amount: writeOffs.reduce((s, r) => s + num(r.amount), 0),
        reason: '',
        procedure: '',
        related: '',
        is_total: true,
      },
    ],
    isSoe ? WRITEOFF_DETAIL_COLUMNS_SOE : WRITEOFF_DETAIL_COLUMNS_LISTED,
  )

  // ⑧ 前五名
  const top5 = snapshot.top5Rows ?? []
  if (isSoe) {
    put(
      D2_TABLE_NAMES.soe.top5,
      [
        ...top5.map((r) => ({
          label: str(r.companyName),
          ar_amount: num(r.arAmount),
          ratio: num(r.ratio),
          provision: num(r.provision),
        })),
        {
          label: '合计',
          ar_amount: top5.reduce((s, r) => s + num(r.arAmount), 0),
          ratio: top5.reduce((s, r) => s + num(r.ratio), 0),
          provision: top5.reduce((s, r) => s + num(r.provision), 0),
          is_total: true,
        },
      ],
      TOP5_COLUMNS_SOE,
    )
  } else {
    const total = (r: D2Top5RowLike) => num(r.arAmount) + num(r.contractAssetAmount)
    put(
      D2_TABLE_NAMES.listed.top5,
      [
        ...top5.map((r) => ({
          label: str(r.companyName),
          ar_amount: num(r.arAmount),
          contract_asset_amount: num(r.contractAssetAmount),
          total_amount: total(r),
          ratio: num(r.ratio),
          provision: num(r.provision),
        })),
        {
          label: '合计',
          ar_amount: top5.reduce((s, r) => s + num(r.arAmount), 0),
          contract_asset_amount: top5.reduce((s, r) => s + num(r.contractAssetAmount), 0),
          total_amount: top5.reduce((s, r) => s + total(r), 0),
          ratio: top5.reduce((s, r) => s + num(r.ratio), 0),
          provision: top5.reduce((s, r) => s + num(r.provision), 0),
          is_total: true,
        },
      ],
      TOP5_COLUMNS_LISTED,
    )
  }

  // ⑨ 国企：由金融资产转移而终止确认
  if (isSoe) {
    const der = snapshot.derecognizedRows ?? []
    put(
      D2_TABLE_NAMES.soe.derecognized,
      [
        ...der.map((r) => ({ label: str(r.companyName), amount: num(r.amount), gain_loss: num(r.gainLoss) })),
        {
          label: '合计',
          amount: der.reduce((s, r) => s + num(r.amount), 0),
          gain_loss: der.reduce((s, r) => s + num(r.gainLoss), 0),
          is_total: true,
        },
      ],
      DERECOGNIZED_COLUMNS_SOE,
    )
  }

  // ⑩ 文本框内容
  sub._note_texts = buildD2NoteTexts(snapshot.notes)

  return {
    wp_id: wpId,
    sheet_name: D2_DISCLOSURE_SHEET_NAME[variant],
    section_id: D2_NOTE_SECTION[variant],
    current_standard: resolveD2CurrentStandard(variant, applicableStandards),
    sub_table_data: sub,
    columns,
  }
}

/** 说明文本子节顺序与标题（与披露表文本框一一对应）。 */
export const D2_NOTE_TEXT_SECTIONS: Array<{ key: string; title: string }> = [
  { key: 'aging', title: '按账龄披露说明' },
  { key: 'badDebtClass', title: '按坏账准备计提方法分类说明' },
  { key: 'individual', title: '按单项计提坏账准备说明' },
  { key: 'portfolio', title: '按组合计提坏账准备说明' },
  { key: 'movement', title: '坏账准备变动说明' },
  { key: 'writeOff', title: '应收账款核销说明' },
  { key: 'top5', title: '前五名欠款方说明' },
]

/** 各子节说明 → _note_texts（仅非空），保证附注 text_content 与披露表文本框一致。 */
export function buildD2NoteTexts(notes: Record<string, string>): Array<{ section: string; title: string; text: string }> {
  const out: Array<{ section: string; title: string; text: string }> = []
  for (const { key, title } of D2_NOTE_TEXT_SECTIONS) {
    const text = String(notes?.[key] ?? '').trim()
    if (text) out.push({ section: `note-${key}`, title, text })
  }
  return out
}
