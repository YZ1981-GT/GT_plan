/** G13 公允价值变动收益 — 审定表固定分组（与 xlsx G13-1 一致） */
export interface G13AdjudicationDef {
  rowKey: string
  label: string
  sourceAccounts: readonly string[]
}

export const G13_ADJUDICATION_ITEMS: G13AdjudicationDef[] = [
  { rowKey: 'trading_assets', label: '交易性金融资产公允价值变动', sourceAccounts: ['G1'] },
  { rowKey: 'trading_liabilities', label: '交易性金融负债公允价值变动', sourceAccounts: ['G10'] },
  { rowKey: 'designated_fv', label: '指定以公允价值计量的金融资产变动', sourceAccounts: ['G8'] },
  { rowKey: 'derivatives', label: '衍生金融工具公允价值变动', sourceAccounts: ['G9'] },
  { rowKey: 'other', label: '其他', sourceAccounts: [] },
]

export const G13_BELONG_ACCOUNTS = ['G1', 'G8', 'G9', 'G10'] as const
export type G13BelongAccount = (typeof G13_BELONG_ACCOUNTS)[number] | ''

export const G13_BELONG_ACCOUNT_LABELS: Record<string, string> = {
  G1: 'G1 交易性金融资产',
  G8: 'G8 指定FV计量金融资产',
  G9: 'G9 衍生金融工具',
  G10: 'G10 交易性金融负债',
}

export const G13_SOURCE_INDEX_BY_BELONG: Record<string, string> = {
  G1: 'wp:G1-1',
  G8: 'wp:G8-1',
  G9: 'wp:G9-1',
  G10: 'wp:G10-1',
}

export const G13_INSTRUMENT_TYPES = [
  '股票', '债券', '基金', '衍生工具', '其他',
] as const

export const G13_CROSS_VERIFY_OPTIONS = [
  { value: 'consistent', label: '一致' },
  { value: 'inconsistent', label: '不一致' },
  { value: 'pending', label: '待验证' },
] as const

export const G13_ACCOUNT_CODE = '6101'
export const G13_CHANGE_RATE_THRESHOLD = 0.2

/** 明细所属科目 → 审定表 rowKey */
export const G13_BELONG_TO_ADJ: Record<string, string> = {
  G1: 'trading_assets',
  G10: 'trading_liabilities',
  G8: 'designated_fv',
  G9: 'derivatives',
}

export function mapBelongToAdjRow(belongAccount: string): string {
  return G13_BELONG_TO_ADJ[belongAccount] ?? 'other'
}

/** 附注披露行（上市，与 xlsx 附注披露信息（上市公司）行 8–17 一致） */
export const G13_DISCLOSURE_LISTED_ROWS = [
  { rowKey: 'trading_assets', label: '交易性金融资产' },
  { rowKey: 'designated_fv_assets', label: '    其中：指定为以公允价值计量且其变动计入当期损益的金融资产' },
  { rowKey: 'derivatives', label: '衍生金融工具产生的公允价值变动收益' },
  { rowKey: 'trading_liabilities', label: '交易性金融负债' },
  { rowKey: 'designated_fv_liabilities', label: '    其中：指定为以公允价值计量且其变动计入当期损益的金融负债' },
  { rowKey: 'other_noncurrent', label: '其他非流动金融资产' },
  { rowKey: 'designated_fv_other', label: '    其中：指定为以公允价值计量且其变动计入当期损益的金融资产' },
  { rowKey: 'investment_property', label: '按公允价值计量的投资性房地产' },
  { rowKey: 'other', label: '其他' },
] as const

/** 附注披露行（国企，与 xlsx 行 8–15 一致） */
export const G13_DISCLOSURE_SOE_ROWS = [
  { rowKey: 'trading_assets', label: '交易性金融资产' },
  { rowKey: 'derivative_assets', label: '衍生金融资产' },
  { rowKey: 'other_noncurrent', label: '其他非流动金融资产' },
  { rowKey: 'trading_liabilities', label: '交易性金融负债' },
  { rowKey: 'derivative_liabilities', label: '衍生金融负债' },
  { rowKey: 'investment_property', label: '按公允价值计量的投资性房地产' },
  { rowKey: 'other', label: '其他' },
] as const

/** G13-2 所属科目 → 附注披露主行（上市/国企共用粗粒度同步） */
export const G13_DETAIL_TO_DISCLOSURE: Record<string, string> = {
  G1: 'trading_assets',
  G8: 'other_noncurrent',
  G9: 'derivatives',
  G10: 'trading_liabilities',
}

export const G13_DISCLOSURE_FORMULA_MAP = [
  { field: '附注合计-本期', source: 'G13-1审定表', formula: 'SUM(currentAudited) → EventBus 6101', account: '6101' },
  { field: '附注各行-本期', source: 'G13-2明细', formula: '按 belongAccount → G13_DETAIL_TO_DISCLOSURE 汇总', account: '6101' },
  { field: '附注合计-上期', source: 'G13-adj-prior', formula: 'priorAudited 各分类行', account: '6101' },
  { field: '变动额/变动率', source: '计算', formula: 'currentAmount - priorAmount', account: '-' },
] as const
