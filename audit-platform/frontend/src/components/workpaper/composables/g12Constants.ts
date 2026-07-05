/** G12 净敞口套期收益 — 常量 */
export interface G12AdjudicationDef {
  rowKey: string
  label: string
}

export const G12_ADJUDICATION_ITEMS: G12AdjudicationDef[] = [
  { rowKey: 'net_hedge', label: '净敞口套期收益/损失' },
  { rowKey: 'instrument_fv', label: '套期工具公允价值变动' },
  { rowKey: 'item_fv', label: '被套期项目公允价值变动' },
  { rowKey: 'ineffectiveness', label: '套期无效部分' },
  { rowKey: 'other', label: '其他' },
]

export const G12_ACCOUNT_CODE = '6103'
export const G12_CHANGE_RATE_THRESHOLD = 0.2
export const G12_VIRTUAL_SCROLL_THRESHOLD = 50

export const G12_HEDGE_TYPES = [
  { value: 'fair_value', label: '公允价值套期' },
  { value: 'cash_flow', label: '现金流量套期' },
  { value: 'net_investment', label: '境外经营净投资套期' },
] as const

export const G12_EFFECTIVENESS_OPTIONS = [
  { value: 'effective', label: '有效' },
  { value: 'ineffective', label: '无效' },
  { value: 'partially_effective', label: '部分有效' },
  { value: 'pending', label: '待评估' },
] as const

export const G12_INSTRUMENT_TYPES = [
  { value: 'irs', label: '利率互换' },
  { value: 'forward', label: '远期合约' },
  { value: 'option', label: '期权' },
  { value: 'future', label: '期货' },
  { value: 'other', label: '其他' },
] as const

export const G12_ITEM_TYPES = [
  { value: 'fixed_loan', label: '固定利率贷款' },
  { value: 'inventory', label: '存货' },
  { value: 'firm_commitment', label: '确定承诺' },
  { value: 'forecast_transaction', label: '预期交易' },
  { value: 'other', label: '其他' },
] as const

export const G12_FV_LEVELS = [
  { value: 'Level1', label: 'Level 1' },
  { value: 'Level2', label: 'Level 2' },
  { value: 'Level3', label: 'Level 3' },
] as const

export const G12_TEST_METHODS = [
  { value: 'regression', label: '回归分析' },
  { value: 'dollar_offset', label: '美元抵销' },
  { value: 'hypothetical_derivative', label: '假设衍生工具' },
] as const

export const G12_RISK_LEVELS = [
  { value: 'high', label: '高' },
  { value: 'medium', label: '中' },
  { value: 'low', label: '低' },
] as const

export const G12_COMPLIANCE_OPTIONS = [
  { value: 'compliant', label: '合规' },
  { value: 'non_compliant', label: '不合规' },
  { value: 'not_applicable', label: '不适用' },
] as const

/** 附注披露行（上市 12 行 × 5 列） */
export const G12_DISCLOSURE_LISTED_ROWS = [
  { rowKey: 'net_hedge', label: '净敞口套期收益（损失）' },
  { rowKey: 'fv_hedge_pl', label: '其中：公允价值套期计入损益' },
  { rowKey: 'cf_hedge_pl', label: '其中：现金流量套期计入损益' },
  { rowKey: 'ni_hedge_pl', label: '其中：净投资套期计入损益' },
  { rowKey: 'instrument_fv', label: '套期工具公允价值变动' },
  { rowKey: 'item_fv', label: '被套期项目公允价值变动' },
  { rowKey: 'ineffectiveness', label: '套期无效部分' },
  { rowKey: 'cf_reserve', label: '现金流量套期储备变动' },
  { rowKey: 'ni_translation', label: '境外经营净投资折算差额' },
  { rowKey: 'fair_value_level', label: '套期工具公允价值层次披露' },
  { rowKey: 'risk_exposure', label: '被套期风险敞口' },
  { rowKey: 'other', label: '其他' },
] as const

/** 附注披露行（国企 11 行） */
export const G12_DISCLOSURE_SOE_ROWS = G12_DISCLOSURE_LISTED_ROWS.filter(
  (r) => r.rowKey !== 'fair_value_level',
)

export const G12_IMPORT_EXPORT_SHEETS = ['G12-2', 'G12-3', 'G12-4', 'G12-6'] as const

export const G12_DISCLOSURE_FORMULA_MAP = [
  { field: '附注合计-本期', source: 'G12-1审定表', formula: 'SUM(currentAudited) → substantive:adjudicated EventBus', account: '6103' },
  { field: '附注各行-本期', source: 'G12-1/G12-2', formula: '按 rowKey 映射套期明细汇总', account: '6103' },
  { field: '附注合计-上期', source: 'G12-adj-prior', formula: 'priorAudited 各业务行', account: '6103' },
  { field: '变动额/变动率', source: '计算', formula: 'currentAmount - priorAmount; rate=prior≠0', account: '-' },
] as const
