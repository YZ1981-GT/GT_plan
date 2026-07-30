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
 * 覆盖完整性：以致同源模板 sheet「附注披露信息(上市公司)」（A1:I181）为权威结构真源，
 * 上市固定表 13 张 = 账龄 / 分类披露双期 2 / 单项计提双期 2 / 坏账变动 / 重要转回 /
 * 核销金额 / 核销逐项 / 前五名 / 终止确认 / 继续涉入（组合分表按项目实际组合动态生成）；
 * 国企固定表 10 张（沿用 八、5 模板口径）。
 * spec: d2-ar-disclosure-template-alignment
 */
import type { ColumnDef } from './disclosureColumnDefs'
import {
  DISCLOSURE_TOTAL_LABEL,
  SOE_AGING_OVERRIDES,
  toDisclosureAgingLabel,
  toDisclosureStructLabel,
} from './disclosureAgingLabels'
import {
  buildRemovedTableKeys,
  dataTableNames,
  type TableNamespaceSpec,
} from './disclosureSyncedTables'

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
    derecognized: '因金融资产转移而终止确认的应收账款情况',
    continuedInvolvement: '转移应收账款且继续涉入形成的资产、负债',
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
    // 源模板 r129「（6）应收账款转移继续涉入形成的资产、负债的金额【如证券化、保理等】」；
    // 附注 八、5 把账龄表编为（1），故顺延为（7）（见 spec design D1）。
    continuedInvolvement: '（7）应收账款转移继续涉入形成的资产、负债的金额',
  },
} as const

/** 组合计提项目分表名前缀（模板：组合计提项目：应收中央企业客户 等）。 */
export const D2_PORTFOLIO_TABLE_PREFIX = '组合计提项目：'

/** 组合计提项目分表名（模板：组合计提项目：应收中央企业客户 等）。 */
export function portfolioTableName(portfolioName: string): string {
  return `${D2_PORTFOLIO_TABLE_PREFIX}${String(portfolioName || '').trim() || '未命名组合'}`
}

/** 国企分类披露续表后缀（期初数续表，键必须唯一 → 在 classEnd 后缀化）。 */
export const D2_SOE_PRIOR_SUFFIX = '（续：期初数）'

/**
 * 旧实现遗留的上市版表名（已被 `（续：上年年末余额）` 口径取代）。
 *
 * 定位：`buildRemovedTableKeys` 的 **legacyObsolete 静态种子** —— 首次启用（尚无
 * 「上次已同步表名」持久化）时仍要能清掉它们；这两个键永远不会出现在持久化清单里，
 * 故不可由动态 diff 替代（spec disclosure-columns-coverage-rollout R7.4）。
 */
export const D2_LISTED_OBSOLETE_TABLE_KEYS: readonly string[] = [
  '按坏账计提方法分类披露（上年年末金额）',
  '按单项计提坏账准备的应收账款（上年年末金额）',
]

/**
 * D2 在附注 §五、5 / §八、5 的**表名命名空间**（R7.5 基线播种用）。
 *
 * 用途：首次同步时按此谓词过滤附注**现存**表名来播种差集基线，让「基线建立之前
 * 就残留的孤儿表」（实测某项目残留 `组合计提项目：应收中央企业客户`）也能自愈。
 *
 * 🔴 严格谓词，宁漏不误杀：同一章节可能被别的底稿推送，误判会删掉别人的数据。
 * 只认 ① 本变体固定表名全集；② 组合分表前缀；③ 续表后缀；④ 历史遗留静态旧名。
 */
export const D2_TABLE_NAMESPACE = {
  listed: {
    known: [...Object.values(D2_TABLE_NAMES.listed), ...D2_LISTED_OBSOLETE_TABLE_KEYS],
    prefixes: [D2_PORTFOLIO_TABLE_PREFIX],
    suffixes: [] as readonly string[],
  },
  soe: {
    known: Object.values(D2_TABLE_NAMES.soe),
    prefixes: [D2_PORTFOLIO_TABLE_PREFIX],
    suffixes: [D2_SOE_PRIOR_SUFFIX],
  },
} as const satisfies Record<D2DisclosureVariant, TableNamespaceSpec>

/**
 * 账龄标签披露口径的 per-section 覆盖（R6.3）。
 * 差异只在首档：源模板 + 附注模板实测——上市 五、5 用 `1年以内`（全模板 24 次），
 * 国企 八、5 用 `1年以内（含1年）`（全模板 13 次）。其余档位取共享表默认值。
 */
export const D2_AGING_LABEL_OVERRIDES = {
  listed: {},
  soe: SOE_AGING_OVERRIDES,
} as const satisfies Record<D2DisclosureVariant, Readonly<Record<string, string>>>

// ─── 列头元数据（逐字取自附注模板 headers）────────────────────────────────────
const AMT = 'amount' as const
const PCT = 'percent' as const
const TXT = 'text' as const

const AGING_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '账龄', is_label: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
  { key: 'prior_amount', label: '上年年末余额', format: AMT },
]
// 🔴 源模板单行表头的表一律标 `flat`（抑制后端 `_infer_groups_from_headers` 前缀推断）。
// 实测反例：核销表「核销金额 / 核销原因」被反猜出凭空的「核销」父表头。
const AGING_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '账龄', is_label: true, flat: true },
  { key: 'end_amount', label: '期末数', format: AMT },
  { key: 'prior_amount', label: '期初数', format: AMT },
]
// 分类披露：源模板 r22~r49 三级表头（期末余额/上年年末余额由表名承载，故此处两级）
// 类 别 | 账面余额{金额, 比例(%)} | 坏账准备{金额, 预期信用损失率(%)} | 账面价值
const CLASS_COLUMNS_LISTED_END: ColumnDef[] = [
  { key: 'label', label: '类 别', is_label: true },
  { key: 'book_amount', label: '金额', format: AMT, group: '账面余额' },
  { key: 'ratio', label: '比例(%)', format: PCT, group: '账面余额' },
  { key: 'provision', label: '金额', format: AMT, group: '坏账准备' },
  { key: 'loss_rate', label: '预期信用损失率(%)', format: PCT, group: '坏账准备' },
  { key: 'carrying_value', label: '账面价值', format: AMT },
]
const CLASS_COLUMNS_LISTED_PRIOR: ColumnDef[] = [
  { key: 'label', label: '类 别', is_label: true },
  { key: 'book_amount', label: '金额', format: AMT, group: '账面余额' },
  { key: 'ratio', label: '比例(%)', format: PCT, group: '账面余额' },
  { key: 'provision', label: '金额', format: AMT, group: '坏账准备' },
  { key: 'loss_rate', label: '预期信用损失率(%)', format: PCT, group: '坏账准备' },
  { key: 'carrying_value', label: '账面价值', format: AMT },
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
// 单项计提明细：源模板 r51~r63（双期各一张 5 列表，合计行「计提依据」为 /）
const INDIVIDUAL_COLUMNS_LISTED_END: ColumnDef[] = [
  { key: 'label', label: '名 称', is_label: true },
  { key: 'book_amount', label: '账面余额', format: AMT },
  { key: 'provision', label: '坏账准备', format: AMT },
  { key: 'loss_rate', label: '预期信用损失率（%）', format: PCT },
  { key: 'basis', label: '计提依据', format: TXT },
]
const INDIVIDUAL_COLUMNS_LISTED_PRIOR: ColumnDef[] = [
  { key: 'label', label: '名 称', is_label: true },
  { key: 'book_amount', label: '账面余额', format: AMT },
  { key: 'provision', label: '坏账准备', format: AMT },
  { key: 'loss_rate', label: '预期信用损失率（%）', format: PCT },
  { key: 'basis', label: '计提依据', format: TXT },
]
// 组合计提分表：源模板 r66~r114（账龄 + 双期各 3 列）
const PORTFOLIO_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '账龄', is_label: true },
  { key: 'end_amount', label: '应收账款', format: AMT, group: '期末余额' },
  { key: 'end_provision', label: '坏账准备', format: AMT, group: '期末余额' },
  { key: 'end_loss_rate', label: '预期信用损失率(%)', format: PCT, group: '期末余额' },
  { key: 'prior_amount', label: '应收账款', format: AMT, group: '上年年末余额' },
  { key: 'prior_provision', label: '坏账准备', format: AMT, group: '上年年末余额' },
  { key: 'prior_loss_rate', label: '预期信用损失率(%)', format: PCT, group: '上年年末余额' },
]
const INDIVIDUAL_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '债务人名称', is_label: true, flat: true },
  { key: 'end_amount', label: '账面余额', format: AMT },
  { key: 'provision', label: '坏账准备', format: AMT },
  { key: 'aging', label: '账龄', format: TXT },
  { key: 'loss_rate', label: '预期信用损失率（%）', format: PCT },
  { key: 'basis', label: '计提理由', format: TXT },
]
// 国企组合计提分表：源模板 r36~r79（账龄 + 双期各{应收账款, 比例（%）, 坏账准备}）
const PORTFOLIO_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '账 龄', is_label: true },
  { key: 'end_amount', label: '应收账款', format: AMT, group: '期末数' },
  { key: 'end_ratio', label: '比例（%）', format: PCT, group: '期末数' },
  { key: 'end_provision', label: '坏账准备', format: AMT, group: '期末数' },
  { key: 'prior_amount', label: '应收账款', format: AMT, group: '期初数' },
  { key: 'prior_ratio', label: '比例（%）', format: PCT, group: '期初数' },
  { key: 'prior_provision', label: '坏账准备', format: AMT, group: '期初数' },
]
// 采用余额百分比或其他组合方法：源模板 r82~r90（组合名称 + 双期各{账面余额, 计提比例（%）, 坏账准备}）
const OTHER_PORTFOLIO_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '组合名称', is_label: true },
  { key: 'end_amount', label: '账面余额', format: AMT, group: '期末数' },
  { key: 'end_rate', label: '计提比例（%）', format: PCT, group: '期末数' },
  { key: 'end_provision', label: '坏账准备', format: AMT, group: '期末数' },
  { key: 'prior_amount', label: '账面余额', format: AMT, group: '期初数' },
  { key: 'prior_rate', label: '计提比例（%）', format: PCT, group: '期初数' },
  { key: 'prior_provision', label: '坏账准备', format: AMT, group: '期初数' },
]
const MOVEMENT_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'amount', label: '坏账准备金额', format: AMT },
]
// 变动表：源模板 r94~r95（类 别 | 期初数 | 本期变动金额{计提, 收回或转回, 转销或核销} | 期末数）
const MOVEMENT_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '类 别', is_label: true },
  { key: 'prior_amount', label: '期初数', format: AMT },
  { key: 'provision_amount', label: '计提', format: AMT, group: '本期变动金额' },
  { key: 'reversal_amount', label: '收回或转回', format: AMT, group: '本期变动金额' },
  { key: 'writeoff_amount', label: '转销或核销', format: AMT, group: '本期变动金额' },
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
  { key: 'label', label: '债务人名称', is_label: true, flat: true },
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
  { key: 'label', label: '债务人名称', is_label: true, flat: true },
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
  { key: 'label', label: '债务人名称', is_label: true, flat: true },
  { key: 'ar_amount', label: '账面余额', format: AMT },
  { key: 'ratio', label: '占应收账款合计的比例（%）', format: PCT },
  { key: 'provision', label: '坏账准备', format: AMT },
]
const DERECOGNIZED_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '债务人名称', is_label: true, flat: true },
  { key: 'amount', label: '终止确认金额', format: AMT },
  { key: 'gain_loss', label: '与终止确认相关的利得或损失（损失以“-”填列）', format: AMT },
]
// (6) 因金融资产转移而终止确认：源模板 r162
const DERECOGNIZED_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '项  目', is_label: true },
  { key: 'transfer_method', label: '转移方式', format: TXT },
  { key: 'amount', label: '终止确认金额', format: AMT },
  { key: 'gain_loss', label: '与终止确认相关的利得或损失', format: AMT },
]
// 国企（7）继续涉入：源模板 r130「项 目 | 期末金额」，资产/负债分块 + 各自小计
const CONTINUED_INVOLVEMENT_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '项  目', is_label: true, flat: true },
  { key: 'amount', label: '期末金额', format: AMT },
]
// (7) 转移应收账款且继续涉入形成的资产、负债：源模板 r174
const CONTINUED_INVOLVEMENT_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项  目', is_label: true },
  { key: 'transfer_method', label: '资产转移方式', format: TXT },
  { key: 'asset_amount', label: '继续涉入形成的资产金额', format: AMT },
  { key: 'liability_amount', label: '继续涉入形成的负债金额', format: AMT },
]

// ─── 快照行类型（组件层传入）─────────────────────────────────────────────────
export interface D2TwoPeriodRowLike {
  /** 账龄段 key（`within1`/`y1to2`/…）或结构行 key；用于账龄标签披露口径映射（R6） */
  key?: string
  label: string
  endAmount: number
  priorAmount: number
  isTotal?: boolean
}
/** 分类宽表行（源模板 6 列，双期各一张） */
export interface D2ClassWideRowLike {
  label: string
  bookAmount: number
  ratio: number
  provision: number
  lossRate: number
  carryingValue: number
  isTotal?: boolean
}
export interface D2IndividualRowLike {
  name: string
  endAmount: number
  priorAmount?: number
  /** 坏账准备（期末 / 上年年末） */
  provision?: number
  priorProvision?: number
  /** 预期信用损失率(%)（派生，期末 / 上年年末） */
  lossRate?: number
  priorLossRate?: number
  aging?: string
  basis?: string
}
/**
 * 组合分表行：
 * 上市 = 账龄 × 双期{应收账款, 坏账准备, 预期信用损失率}（源模板 r66~r67）
 * 国企 = 账龄 × 双期{应收账款, 比例（%）, 坏账准备}（源模板 r36~r38）
 */
export interface D2PortfolioRowLike extends D2TwoPeriodRowLike {
  provision?: number
  priorProvision?: number
  lossRate?: number
  priorLossRate?: number
  /** 国企：账龄占比(%)（本行应收账款 ÷ 组合本期合计） */
  ratio?: number
  priorRatio?: number
}
/** 国企「采用余额百分比或其他组合方法」行（组合名称 + 双期{账面余额, 计提比例（%）, 坏账准备}） */
export interface D2OtherPortfolioRowLike extends D2TwoPeriodRowLike {
  provision?: number
  priorProvision?: number
  /** 计提比例(%)（坏账准备 ÷ 账面余额） */
  rate?: number
  priorRate?: number
}
export interface D2PortfolioGroupLike { name: string; groupId?: string; rows: D2PortfolioRowLike[] }
export interface D2MovementLike { priorBalance: number; provision: number; reversal: number; writeOff: number; transfer: number; other: number; endBalance: number }
export interface D2MovementByCategoryLike { label: string; priorAmount: number; provisionAmount: number; reversalAmount: number; writeOffAmount: number; endAmount: number; isTotal?: boolean }
export interface D2ReversalRowLike { companyName: string; reversalReason?: string; recoveryMethod?: string; originalBasis?: string; cumulativeProvision?: number; amount: number }
export interface D2WriteOffRowLike { companyName: string; nature?: string; amount: number; reason?: string; procedure?: string; relatedParty?: string }
export interface D2Top5RowLike { companyName: string; arAmount: number; contractAssetAmount?: number; ratio: number; provision: number }
export interface D2DerecognizedRowLike { companyName: string; transferMethod?: string; amount: number; gainLoss: number }
/** (7) 转移应收账款且继续涉入形成的资产、负债 */
export interface D2ContinuedInvolvementRowLike {
  item: string
  transferMethod: string
  assetAmount: number
  liabilityAmount: number
}

export interface D2DisclosureSnapshot {
  /** 账龄披露（含 1年以内小计/减：坏账准备/合计 等结构行，label 直接来自披露表） */
  agingRows: D2TwoPeriodRowLike[]
  /** 按坏账准备计提方法分类（单项/组合/其中：各组合/合计），窄口径仅供一致性核对 */
  classRows: D2TwoPeriodRowLike[]
  /** 6 列分类宽表（期末余额），上市版与国企版共用 */
  classWideEndRows: D2ClassWideRowLike[]
  /** 6 列分类宽表（上年年末余额 / 国企期初数） */
  classWidePriorRows: D2ClassWideRowLike[]
  /** 单项计提明细 */
  individualRows: D2IndividualRowLike[]
  /** 组合计提项目（每个组合一张分表） */
  portfolios: D2PortfolioGroupLike[]
  /** 国企：采用余额百分比或其他组合方法计提 */
  otherPortfolioRows?: D2OtherPortfolioRowLike[]
  /** 坏账准备变动（上市纵向 7 行口径） */
  movement: D2MovementLike
  /** 国企：按类别的坏账准备变动（期初/本期变动/期末） */
  movementByCategory?: D2MovementByCategoryLike[]
  reversalRows: D2ReversalRowLike[]
  writeOffAmount: number
  writeOffRows: D2WriteOffRowLike[]
  top5Rows: D2Top5RowLike[]
  /** (6) 因金融资产转移而终止确认的应收账款（上市 + 国企共用） */
  derecognizedRows?: D2DerecognizedRowLike[]
  /** (7) 转移应收账款且继续涉入形成的资产、负债（上市） */
  continuedInvolvementRows?: D2ContinuedInvolvementRowLike[]
  /** 各子节说明文本（文本框内容），与披露表保持一致后同步到附注 text_content */
  notes: Record<string, string>
  /**
   * 上次成功同步时推送过的数据子表名（底稿持久化，R7）。
   * 与本次推送做差集得到 `_removed_table_keys`，清掉改名/删除留下的孤儿 TAB。
   */
  previouslySyncedTables?: readonly string[]
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
/** 合计行判定：容忍模板字面的全角空格（`合 计`）与无空格形态（`合计`）。 */
const isTotalLabel = (label: string): boolean =>
  String(label ?? '').replace(/[\s\u3000]/g, '') === '合计'

/**
 * 🔴 `is_total` 必须用**映射前**的原始 label 判定：披露口径把 `合计` 映射为 `合 计`
 * （附注模板字面带全角空格），若用映射后的值判定则 `isTotalLabel` 永假 → 合计行失去标记。
 */
function twoPeriodRow(
  r: D2TwoPeriodRowLike,
  opts: { end?: boolean; prior?: boolean; label?: string } = { end: true, prior: true },
) {
  const out: Record<string, unknown> = { label: opts.label ?? str(r.label) }
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
  // R6 方案 A：账龄段/结构行 label 在此映射为披露口径（`1-2年`→`1至2年`、`合计`→`合 计`），
  // 底稿 UI 仍用项目账龄配置口径 —— 映射只发生在载荷构建时（Property 8）。
  const agingOverrides = D2_AGING_LABEL_OVERRIDES[variant]
  const discAgingLabel = (r: { key?: string; label: string }): string =>
    toDisclosureAgingLabel(r, agingOverrides)
  const agingRows = snapshot.agingRows.map((r) => twoPeriodRow(r, { label: discAgingLabel(r) }))
  if (isSoe) {
    put(D2_TABLE_NAMES.soe.aging, agingRows, AGING_COLUMNS_SOE)
  } else {
    put(D2_TABLE_NAMES.listed.aging, agingRows, AGING_COLUMNS_LISTED)
  }

  // ② 按坏账准备计提方法分类：双期各一张 6 列宽表（上市/国企同构，仅表名与列头用词不同）
  const classWide = (r: D2ClassWideRowLike) => ({
    label: toDisclosureStructLabel(str(r.label)),
    book_amount: num(r.bookAmount),
    ratio: num(r.ratio),
    provision: num(r.provision),
    loss_rate: num(r.lossRate),
    carrying_value: num(r.carryingValue),
    ...(r.isTotal || isTotalLabel(str(r.label)) ? { is_total: true } : {}),
  })
  const classEndRows = (snapshot.classWideEndRows ?? []).map(classWide)
  const classPriorRows = (snapshot.classWidePriorRows ?? []).map(classWide)
  if (isSoe) {
    put(D2_TABLE_NAMES.soe.classEnd, classEndRows, CLASS_COLUMNS_SOE)
    // 国企期初数表（表名「续：期初数」）
    put(`${D2_TABLE_NAMES.soe.classEnd}${D2_SOE_PRIOR_SUFFIX}`, classPriorRows, CLASS_COLUMNS_SOE_PRIOR)
  } else {
    put(D2_TABLE_NAMES.listed.classEnd, classEndRows, CLASS_COLUMNS_LISTED_END)
    put(D2_TABLE_NAMES.listed.classPrior, classPriorRows, CLASS_COLUMNS_LISTED_PRIOR)
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
          label: DISCLOSURE_TOTAL_LABEL,
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
    // 上市：双期各一张 5 列表（账面余额/坏账准备/预期信用损失率/计提依据），
    // 合计行「计提依据」为 `/`（源模板 E56/E63），损失率合计按合计口径重算。
    const sumBy = (pick: (r: D2IndividualRowLike) => number) => individuals.reduce((s, r) => s + num(pick(r)), 0)
    const rate = (prov: number, book: number) => (book !== 0 ? (prov / book) * 100 : 0)
    const endBook = sumBy((r) => r.endAmount)
    const endProv = sumBy((r) => r.provision ?? 0)
    const priorBook = sumBy((r) => r.priorAmount ?? 0)
    const priorProv = sumBy((r) => r.priorProvision ?? 0)
    put(
      D2_TABLE_NAMES.listed.individualEnd,
      [
        ...individuals.map((r) => ({
          label: str(r.name),
          book_amount: num(r.endAmount),
          provision: num(r.provision),
          loss_rate: num(r.lossRate),
          basis: str(r.basis),
        })),
        {
          label: DISCLOSURE_TOTAL_LABEL,
          book_amount: endBook,
          provision: endProv,
          loss_rate: rate(endProv, endBook),
          basis: '/',
          is_total: true,
        },
      ],
      INDIVIDUAL_COLUMNS_LISTED_END,
    )
    put(
      D2_TABLE_NAMES.listed.individualPrior,
      [
        ...individuals.map((r) => ({
          label: str(r.name),
          book_amount: num(r.priorAmount),
          provision: num(r.priorProvision),
          loss_rate: num(r.priorLossRate),
          basis: str(r.basis),
        })),
        {
          label: DISCLOSURE_TOTAL_LABEL,
          book_amount: priorBook,
          provision: priorProv,
          loss_rate: rate(priorProv, priorBook),
          basis: '/',
          is_total: true,
        },
      ],
      INDIVIDUAL_COLUMNS_LISTED_PRIOR,
    )
  }

  // ④ 组合计提项目（每组合一张分表，表名随组合名动态）
  // 上市：源模板 r66 双期{应收账款, 坏账准备, 预期信用损失率}
  // 国企：源模板 r36 双期{应收账款, 比例（%）, 坏账准备}
  const portfolioCols = isSoe ? PORTFOLIO_COLUMNS_SOE : PORTFOLIO_COLUMNS_LISTED
  const portfolioRow = (r: D2PortfolioRowLike) =>
    isSoe
      ? {
          label: discAgingLabel(r),
          end_amount: num(r.endAmount),
          end_ratio: num(r.ratio),
          end_provision: num(r.provision),
          prior_amount: num(r.priorAmount),
          prior_ratio: num(r.priorRatio),
          prior_provision: num(r.priorProvision),
          ...(r.isTotal || isTotalLabel(str(r.label)) ? { is_total: true } : {}),
        }
      : {
          label: discAgingLabel(r),
          end_amount: num(r.endAmount),
          end_provision: num(r.provision),
          end_loss_rate: num(r.lossRate),
          prior_amount: num(r.priorAmount),
          prior_provision: num(r.priorProvision),
          prior_loss_rate: num(r.priorLossRate),
          ...(r.isTotal || isTotalLabel(str(r.label)) ? { is_total: true } : {}),
        }
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
    put(name, (group.rows ?? []).map(portfolioRow), portfolioCols)
  }
  if (isSoe) {
    const other = snapshot.otherPortfolioRows ?? []
    const sumOther = (pick: (r: D2OtherPortfolioRowLike) => number | undefined) =>
      other.reduce((s, r) => s + num(pick(r)), 0)
    const rate = (prov: number, book: number) => (book !== 0 ? (prov / book) * 100 : 0)
    const endBook = sumOther((r) => r.endAmount)
    const endProv = sumOther((r) => r.provision)
    const priorBook = sumOther((r) => r.priorAmount)
    const priorProv = sumOther((r) => r.priorProvision)
    put(
      D2_TABLE_NAMES.soe.otherPortfolio,
      [
        ...other.map((r) => ({
          label: str(r.label),
          end_amount: num(r.endAmount),
          end_rate: num(r.rate),
          end_provision: num(r.provision),
          prior_amount: num(r.priorAmount),
          prior_rate: num(r.priorRate),
          prior_provision: num(r.priorProvision),
        })),
        {
          label: DISCLOSURE_TOTAL_LABEL,
          end_amount: endBook,
          end_rate: rate(endProv, endBook),
          end_provision: endProv,
          prior_amount: priorBook,
          prior_rate: rate(priorProv, priorBook),
          prior_provision: priorProv,
          is_total: true,
        },
      ],
      OTHER_PORTFOLIO_COLUMNS_SOE,
    )
  }

  // ⑤ 坏账准备变动
  if (isSoe) {
    put(
      D2_TABLE_NAMES.soe.movement,
      (snapshot.movementByCategory ?? []).map((r) => ({
        label: toDisclosureStructLabel(str(r.label)),
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
        // 源模板 r117 行名为「上年年末余额」
        { label: '上年年末余额', amount: num(m.priorBalance) },
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
          label: DISCLOSURE_TOTAL_LABEL,
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
          label: DISCLOSURE_TOTAL_LABEL,
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
        label: DISCLOSURE_TOTAL_LABEL,
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
          label: DISCLOSURE_TOTAL_LABEL,
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
          label: DISCLOSURE_TOTAL_LABEL,
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

  // ⑨ 因金融资产转移而终止确认（上市源模板 r160~r166 四列；国企沿用其模板三列）
  const der = snapshot.derecognizedRows ?? []
  const derTotal = {
    amount: der.reduce((s, r) => s + num(r.amount), 0),
    gain_loss: der.reduce((s, r) => s + num(r.gainLoss), 0),
  }
  if (isSoe) {
    put(
      D2_TABLE_NAMES.soe.derecognized,
      [
        ...der.map((r) => ({ label: str(r.companyName), amount: num(r.amount), gain_loss: num(r.gainLoss) })),
        { label: DISCLOSURE_TOTAL_LABEL, ...derTotal, is_total: true },
      ],
      DERECOGNIZED_COLUMNS_SOE,
    )

    // 国企（7）继续涉入：源模板 r130「项 目 | 期末金额」，资产 / 负债分块 + 各自小计
    const ciSoe = snapshot.continuedInvolvementRows ?? []
    const soeBlock = (title: string, pick: (r: D2ContinuedInvolvementRowLike) => number) => {
      const rows = ciSoe.map((r) => ({
        label: `${str(r.item) || '（未命名）'}${r.transferMethod ? `（${str(r.transferMethod)}）` : ''}`,
        amount: num(pick(r)),
      }))
      return [
        { label: title, amount: 0, is_section: true },
        ...rows,
        { label: `${title}小计`, amount: rows.reduce((s, r) => s + r.amount, 0), is_total: true },
      ]
    }
    put(
      D2_TABLE_NAMES.soe.continuedInvolvement,
      [
        ...soeBlock('继续涉入形成的资产', (r) => r.assetAmount),
        ...soeBlock('继续涉入形成的负债', (r) => r.liabilityAmount),
      ],
      CONTINUED_INVOLVEMENT_COLUMNS_SOE,
    )
  } else {
    put(
      D2_TABLE_NAMES.listed.derecognized,
      [
        ...der.map((r) => ({
          label: str(r.companyName),
          transfer_method: str(r.transferMethod),
          amount: num(r.amount),
          gain_loss: num(r.gainLoss),
        })),
        { label: DISCLOSURE_TOTAL_LABEL, transfer_method: '', ...derTotal, is_total: true },
      ],
      DERECOGNIZED_COLUMNS_LISTED,
    )
  }

  // ⑩ 转移应收账款且继续涉入形成的资产、负债
  //   上市（源模板 r172~r181）：4 列宽表（项目/转移方式/资产金额/负债金额）
  //   国企（源模板 r129~r136）：2 列（项 目/期末金额）+ 资产/负债分块与各自小计
  const ci = snapshot.continuedInvolvementRows ?? []
  const ciAssetTotal = ci.reduce((s, r) => s + num(r.assetAmount), 0)
  const ciLiabilityTotal = ci.reduce((s, r) => s + num(r.liabilityAmount), 0)
  if (isSoe) {
    put(
      D2_TABLE_NAMES.soe.continuedInvolvement,
      [
        { label: '资产：', amount: null, row_type: 'header_label' },
        ...ci.map((r) => ({ label: str(r.item), amount: num(r.assetAmount) })),
        { label: '资产小计', amount: ciAssetTotal, is_total: true },
        { label: '负债：', amount: null, row_type: 'header_label' },
        ...ci.map((r) => ({ label: str(r.item), amount: num(r.liabilityAmount) })),
        { label: '负债小计', amount: ciLiabilityTotal, is_total: true },
      ],
      CONTINUED_INVOLVEMENT_COLUMNS_SOE,
    )
  } else {
    put(
      D2_TABLE_NAMES.listed.continuedInvolvement,
      [
        ...ci.map((r) => ({
          label: str(r.item),
          transfer_method: str(r.transferMethod),
          asset_amount: num(r.assetAmount),
          liability_amount: num(r.liabilityAmount),
        })),
        {
          label: DISCLOSURE_TOTAL_LABEL,
          transfer_method: '',
          asset_amount: ciAssetTotal,
          liability_amount: ciLiabilityTotal,
          is_total: true,
        },
      ],
      CONTINUED_INVOLVEMENT_COLUMNS,
    )
  }

  // ⑪ 文本框内容
  sub._note_texts = buildD2NoteTexts(snapshot.notes)

  // ⑫ 孤儿表清理（R7）：待删除 = (上次已同步 ∪ 变体历史遗留静态种子) − 本次推送。
  //   两版统一上报——组合分表名是动态的（随审计师命名），静态清单覆盖不了改名/删除。
  //   后端 `_drop_removed_tables` 保证「本次推送的 key 绝不删」。
  const removed = buildRemovedTableKeys({
    previouslySynced: snapshot.previouslySyncedTables,
    legacyObsolete: isSoe ? [] : D2_LISTED_OBSOLETE_TABLE_KEYS,
    pushed: dataTableNames(sub),
  })
  if (removed.length > 0) sub._removed_table_keys = removed

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
  { key: 'top5Summary', title: '前五名汇总披露格式' },
  { key: 'derecognition', title: '因金融资产转移而终止确认说明' },
  { key: 'continuedInvolvement', title: '转移应收账款且继续涉入说明' },
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
