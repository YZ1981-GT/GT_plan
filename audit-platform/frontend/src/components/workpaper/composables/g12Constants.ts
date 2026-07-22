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

/** G12-5 风险净敞口 — 常用币种 */
export const G12_NET_EXPOSURE_CURRENCIES = [
  { value: 'USD', label: '美元 USD' },
  { value: 'EUR', label: '欧元 EUR' },
  { value: 'GBP', label: '英镑 GBP' },
  { value: 'JPY', label: '日元 JPY' },
  { value: 'HKD', label: '港币 HKD' },
  { value: 'CNY', label: '人民币 CNY' },
] as const

/** G12-5 支持性证据类型（CAS24 净敞口套期常见证据） */
export const G12_NET_EXPOSURE_EVIDENCE_TYPES = [
  { value: 'sales_budget', label: '销售/采购预算' },
  { value: 'order_contract', label: '订单/合同' },
  { value: 'hedge_designation', label: '套期指定文件' },
  { value: 'board_approval', label: '董事会/管理层决议' },
  { value: 'valuation_doc', label: '公允价值估值资料' },
  { value: 'bank_confirm', label: '银行确认/对账单' },
  { value: 'other', label: '其他' },
] as const

export type G12NetExposureEvidenceType =
  typeof G12_NET_EXPOSURE_EVIDENCE_TYPES[number]['value']

export const G12_CURRENCY_UNIT_LABELS: Record<string, string> = {
  USD: '美元',
  EUR: '欧元',
  GBP: '英镑',
  JPY: '日元',
  HKD: '港币',
  CNY: '人民币',
}

/** 附注披露行（上市 — 对齐 Excel / note_template_listed.json） */
export const G12_DISCLOSURE_LISTED_ROWS = [
  { rowKey: 'net_hedge', label: '净敞口套期收益' },
] as const

/** 附注披露行（国企 — 对齐 Excel / note_template_soe.json） */
export const G12_DISCLOSURE_SOE_ROWS = [
  {
    rowKey: 'hedged_fv_to_pl',
    label: '净敞口套期下被套期项目累计公允价值变动转入当期损益的金额',
  },
  {
    rowKey: 'cf_reserve_to_pl',
    label: '净敞口套期下现金流量套期储备转入当期损益的金额',
  },
] as const

/** 旧版附注 rowKey → 新版映射（加载历史数据时合并） */
export const G12_DISCLOSURE_LEGACY_KEY_MAP: Record<string, string> = {
  item_fv: 'hedged_fv_to_pl',
  cf_reserve: 'cf_reserve_to_pl',
  cf_hedge_pl: 'cf_reserve_to_pl',
}

/** 审计说明区 — 主要变动原因必填阈值（Excel 模板 30%） */
export const G12_AUDIT_NOTE_REASON_THRESHOLD = 0.3

/**
 * G12 主闭环编制顺序（审定→附注）
 * 配套程序/测试：G12A、G12-4/5/6 可并行穿插，但不替代本闭环。
 */
export const G12_CORE_WORKFLOW_STEPS = [
  'G12-2 明细',
  'G12-3 调整',
  'G12-1 从TB取数',
  '核对差异',
  '填审计说明',
  '发布审定数',
  '附注从G12-1同步',
  '勾稽绿条',
  '编写附注说明',
] as const

export const G12_CORE_WORKFLOW_HINT =
  '① 填 G12-2 明细 → G12-3 调整；② G12-1 点「从 TB 取数」→ 核对差异 → 填审计说明 → 发布审定数；③ 附注页点「从 G12-1 同步」→ 确认勾稽条为绿色 → 编写附注说明。'

/** @deprecated 请使用 useG12ImportExport 中的同名常量（含 G12-5） */
export { G12_IMPORT_EXPORT_SHEETS } from './useG12ImportExport'

export const G12_DISCLOSURE_FORMULA_MAP = [
  { field: '附注合计-本期', source: 'G12-1审定表', formula: 'SUM(currentAudited) → substantive:adjudicated EventBus', account: '6103' },
  { field: '附注各行-本期', source: 'G12-1/G12-2', formula: '按 rowKey 映射套期明细汇总', account: '6103' },
  { field: '附注合计-上期', source: 'G12-adj-prior', formula: 'priorAudited 各业务行', account: '6103' },
  { field: '变动额/变动率', source: '计算', formula: 'currentAmount - priorAmount; rate=prior≠0', account: '-' },
] as const
