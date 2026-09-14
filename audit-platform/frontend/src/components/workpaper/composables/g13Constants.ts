/** G13 公允价值变动收益 — 审定表固定分组（与 xlsx 审定表G13-1 一致） */

export type G13AdjRowKind = 'main' | 'ofWhich' | 'derivative'

export interface G13AdjudicationDef {
  rowKey: string
  label: string
  /** main 计入合计；ofWhich「其中」备忘不计入合计；derivative 衍生工具单独计入合计 */
  kind: G13AdjRowKind
  indent: number
  /** 明细所属科目 → 自动汇总到本行（ofWhich 通常手工填列） */
  sourceAccounts: readonly string[]
  /** 视觉强调（xlsx 中衍生工具为红色） */
  emphasize?: boolean
}

/**
 * 与致同模板 G13-1 行序一致：
 * 交易性金融资产 / 其中指定 / 衍生金融资产 →
 * 交易性金融负债 / 其中指定 / 衍生金融负债 →
 * 其他非流动金融资产 / 其中指定 →
 * 投资性房地产 / 其他
 */
export const G13_ADJUDICATION_ITEMS: G13AdjudicationDef[] = [
  {
    rowKey: 'trading_assets',
    label: '交易性金融资产',
    kind: 'main',
    indent: 0,
    sourceAccounts: ['G1'],
  },
  {
    rowKey: 'designated_fv_assets',
    label: '其中：指定为以公允价值计量且其变动计入当期损益的金融资产',
    kind: 'ofWhich',
    indent: 1,
    sourceAccounts: [],
  },
  {
    rowKey: 'derivative_assets',
    label: '衍生金融资产',
    kind: 'derivative',
    indent: 1,
    sourceAccounts: ['G9'],
    emphasize: true,
  },
  {
    rowKey: 'trading_liabilities',
    label: '交易性金融负债',
    kind: 'main',
    indent: 0,
    sourceAccounts: ['G10'],
  },
  {
    rowKey: 'designated_fv_liabilities',
    label: '其中：指定为以公允价值计量且其变动计入当期损益的金融负债',
    kind: 'ofWhich',
    indent: 1,
    sourceAccounts: [],
  },
  {
    rowKey: 'derivative_liabilities',
    label: '衍生金融负债',
    kind: 'derivative',
    indent: 1,
    sourceAccounts: [],
    emphasize: true,
  },
  {
    rowKey: 'other_noncurrent',
    label: '其他非流动金融资产',
    kind: 'main',
    indent: 0,
    sourceAccounts: ['G8'],
  },
  {
    rowKey: 'designated_fv_other',
    label: '其中：指定为以公允价值计量且其变动计入当期损益的金融资产',
    kind: 'ofWhich',
    indent: 1,
    sourceAccounts: [],
  },
  {
    rowKey: 'investment_property',
    label: '以公允价值计量的投资性房地产',
    kind: 'main',
    indent: 0,
    sourceAccounts: ['H3'],
  },
  {
    rowKey: 'other',
    label: '其他',
    kind: 'main',
    indent: 0,
    sourceAccounts: [],
  },
]

/** 计入审定合计的行（排除「其中」备忘行，避免双重加计） */
export function isG13AdjRowInTotal(kind: G13AdjRowKind): boolean {
  return kind !== 'ofWhich'
}

export const G13_ADJ_BY_KEY = Object.fromEntries(
  G13_ADJUDICATION_ITEMS.map((d) => [d.rowKey, d]),
) as Record<string, G13AdjudicationDef>

export const G13_BELONG_ACCOUNTS = ['G1', 'G8', 'G9', 'G10', 'H3'] as const
export type G13BelongAccount = (typeof G13_BELONG_ACCOUNTS)[number] | ''

export const G13_BELONG_ACCOUNT_LABELS: Record<string, string> = {
  G1: 'G1 交易性金融资产',
  G8: 'G8 其他非流动金融资产',
  G9: 'G9 衍生金融工具',
  G10: 'G10 交易性金融负债',
  H3: 'H3 投资性房地产',
}

export const G13_SOURCE_INDEX_BY_BELONG: Record<string, string> = {
  G1: 'wp:G1-1',
  G8: 'wp:G8-1',
  G9: 'wp:G9-1',
  G10: 'wp:G10-1',
  H3: 'wp:H3-1',
}

export const G13_INSTRUMENT_TYPES = [
  '股票', '债券', '基金', '衍生工具', '投资性房地产', '指定FVTPL', '其他',
] as const

export const G13_CROSS_VERIFY_OPTIONS = [
  { value: 'consistent', label: '一致' },
  { value: 'inconsistent', label: '不一致' },
  { value: 'pending', label: '待验证' },
] as const

export const G13_ACCOUNT_CODE = '6101'
/** 与 xlsx 编制说明一致：变动率超过 30% 须说明原因 */
export const G13_CHANGE_RATE_THRESHOLD = 0.3

/**
 * 明细所属科目 → 审定表 rowKey
 * 兼容旧 key：designated_fv → other_noncurrent；derivatives → derivative_assets
 */
export const G13_BELONG_TO_ADJ: Record<string, string> = {
  G1: 'trading_assets',
  G10: 'trading_liabilities',
  G8: 'other_noncurrent',
  G9: 'derivative_assets',
  H3: 'investment_property',
}

/** 指定类明细 → 「其中」备忘行（不计入合计，避免双重加计） */
export const G13_BELONG_TO_OFWHICH: Record<string, string> = {
  G1: 'designated_fv_assets',
  G10: 'designated_fv_liabilities',
  G8: 'designated_fv_other',
}

/** 旧版审定表 priorStore key → 新 key（读档迁移） */
export const G13_LEGACY_ADJ_KEY_MAP: Record<string, string> = {
  designated_fv: 'other_noncurrent',
  derivatives: 'derivative_assets',
}

/** 是否「指定为 FVTPL」类工具（驱动「其中」备忘行） */
export function isDesignatedInstrument(instrumentType?: string, remark?: string): boolean {
  const t = `${instrumentType ?? ''} ${remark ?? ''}`.trim()
  if (!t) return false
  if (/指定FVTPL|指定为.*公允价值|designated[_ ]?fv/i.test(t)) return true
  if (/指定/.test(t) && /公允|FVTPL|损益/i.test(t)) return true
  return /指定/.test(t) || /designated/i.test(t)
}

export function mapBelongToAdjRow(belongAccount: string, instrumentType?: string): string {
  const t = (instrumentType ?? '').trim()
  if (belongAccount === 'G9' && /负债/.test(t)) return 'derivative_liabilities'
  if (belongAccount === 'G10' && /衍生/.test(t)) return 'derivative_liabilities'
  return G13_BELONG_TO_ADJ[belongAccount] ?? 'other'
}

/** 指定类明细对应的「其中」rowKey；非指定返回 null */
export function mapBelongToOfWhichRow(belongAccount: string, instrumentType?: string, remark?: string): string | null {
  if (!isDesignatedInstrument(instrumentType, remark)) return null
  return G13_BELONG_TO_OFWHICH[belongAccount] ?? null
}

/**
 * 明细行是否属于分类骨架某一行（点击分类行筛选工具明细用）
 * - ofWhich：仅指定类且 belong 匹配
 * - main/derivative：mapBelongToAdjRow 命中（含指定子集，与主行口径一致）
 */
export function detailRowMatchesCategory(
  row: { belongAccount: string; instrumentType?: string; remark?: string },
  categoryRowKey: string,
): boolean {
  if (!categoryRowKey || categoryRowKey === 'total') return true
  if (categoryRowKey.startsWith('designated_')) {
    return mapBelongToOfWhichRow(row.belongAccount, row.instrumentType, row.remark) === categoryRowKey
  }
  return mapBelongToAdjRow(row.belongAccount, row.instrumentType) === categoryRowKey
}

/** 分类 rowKey → 默认所属科目（用于搜索提示） */
export function belongHintForCategory(rowKey: string): string {
  const ofWhich = Object.entries(G13_BELONG_TO_OFWHICH).find(([, v]) => v === rowKey)
  if (ofWhich) return ofWhich[0]
  const main = Object.entries(G13_BELONG_TO_ADJ).find(([, v]) => v === rowKey)
  if (main) return main[0]
  if (rowKey === 'derivative_liabilities') return 'G9/G10'
  if (rowKey === 'other') return '其他'
  return ''
}

/**
 * 附注披露行定义。
 * 上市模板红框提示「不存在的项目可以删除」：无发生额的行不进披露表/附注正文；
 * 「其中」挂靠 parentKey，主行不存在时子行一并省略。
 */
export interface G13DisclosureRowDef {
  rowKey: string
  label: string
  ofWhich: boolean
  /** 「其中」备忘行挂靠的主行 rowKey */
  parentKey?: string
}

/** 附注披露行（上市，与 xlsx 附注披露信息（上市公司）行 8–17 一致） */
export const G13_DISCLOSURE_LISTED_ROWS: readonly G13DisclosureRowDef[] = [
  { rowKey: 'trading_assets', label: '交易性金融资产', ofWhich: false },
  {
    rowKey: 'designated_fv_assets',
    label: '    其中：指定为以公允价值计量且其变动计入当期损益的金融资产',
    ofWhich: true,
    parentKey: 'trading_assets',
  },
  { rowKey: 'derivatives', label: '衍生金融工具产生的公允价值变动收益', ofWhich: false },
  { rowKey: 'trading_liabilities', label: '交易性金融负债', ofWhich: false },
  {
    rowKey: 'designated_fv_liabilities',
    label: '    其中：指定为以公允价值计量且其变动计入当期损益的金融负债',
    ofWhich: true,
    parentKey: 'trading_liabilities',
  },
  { rowKey: 'other_noncurrent', label: '其他非流动金融资产', ofWhich: false },
  {
    rowKey: 'designated_fv_other',
    label: '    其中：指定为以公允价值计量且其变动计入当期损益的金融资产',
    ofWhich: true,
    parentKey: 'other_noncurrent',
  },
  { rowKey: 'investment_property', label: '按公允价值计量的投资性房地产', ofWhich: false },
  { rowKey: 'other', label: '其他', ofWhich: false },
]

/** 附注披露行（国企，与 xlsx 行 8–15 一致；无「其中」备忘行） */
export const G13_DISCLOSURE_SOE_ROWS: readonly G13DisclosureRowDef[] = [
  { rowKey: 'trading_assets', label: '交易性金融资产', ofWhich: false },
  { rowKey: 'derivative_assets', label: '衍生金融资产', ofWhich: false },
  { rowKey: 'other_noncurrent', label: '其他非流动金融资产', ofWhich: false },
  { rowKey: 'trading_liabilities', label: '交易性金融负债', ofWhich: false },
  { rowKey: 'derivative_liabilities', label: '衍生金融负债', ofWhich: false },
  { rowKey: 'investment_property', label: '按公允价值计量的投资性房地产', ofWhich: false },
  { rowKey: 'other', label: '其他', ofWhich: false },
]

/** 模板编制提示（不进入附注正文） */
export const G13_DISCLOSURE_TEMPLATE_HINT = '注：以下不存在的项目可以删除'

/** G13-2 所属科目 → 附注披露主行（上市/国企共用粗粒度同步） */
export const G13_DETAIL_TO_DISCLOSURE: Record<string, string> = {
  G1: 'trading_assets',
  G8: 'other_noncurrent',
  G9: 'derivatives',
  G10: 'trading_liabilities',
  H3: 'investment_property',
}

/** 审定表 rowKey → 上市附注 rowKey */
export const G13_ADJ_TO_DISCLOSURE_LISTED: Record<string, string> = {
  trading_assets: 'trading_assets',
  designated_fv_assets: 'designated_fv_assets',
  derivative_assets: 'derivatives',
  derivative_liabilities: 'derivatives',
  trading_liabilities: 'trading_liabilities',
  designated_fv_liabilities: 'designated_fv_liabilities',
  other_noncurrent: 'other_noncurrent',
  designated_fv_other: 'designated_fv_other',
  investment_property: 'investment_property',
  other: 'other',
}

export const G13_DISCLOSURE_FORMULA_MAP = [
  { field: '附注合计-本期', source: 'G13-1审定表', formula: 'SUM(main+derivative currentAudited) → EventBus 6101', account: '6101' },
  { field: '附注各行-本期', source: 'G13-2明细', formula: '按 belongAccount → G13_DETAIL_TO_DISCLOSURE 汇总', account: '6101' },
  { field: '附注合计-上期', source: 'G13-adj-prior', formula: 'priorAudited 各分类行（排除其中）', account: '6101' },
  { field: '变动额/变动率', source: '计算', formula: 'currentAmount - priorAmount', account: '-' },
  { field: '空行/附注同步', source: '过滤', formula: '本期且上期均≈0则隐藏；其中备忘有数才披露且不进合计 → sync 八、72/三、公允', account: '-' },
] as const

/** 编制范围说明（与 xlsx 页脚一致） */
export const G13_SCOPE_NOTE =
  '本科目核算交易性金融资产、交易性金融负债，以及采用公允价值模式计量的投资性房地产、衍生工具、套期业务中公允价值变动形成的应计入当期损益的利得或损失。'
