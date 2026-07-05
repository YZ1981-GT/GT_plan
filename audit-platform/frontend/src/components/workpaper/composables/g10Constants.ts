/** G10 交易性金融负债 — 审定表行定义与常量 */
export interface G10LineDef {
  rowKey: string
  label: string
  group?: string
}

export const G10_ACCOUNT_CODE = '2101'
export const G10_CHANGE_RATE_THRESHOLD = 0.2
export const G10_VIRTUAL_SCROLL_THRESHOLD = 50

export const G10_LIABILITY_TYPE_OPTIONS = [
  '交易性债券',
  '卖出回购',
  '衍生金融负债',
  '融券负债',
  '结构化产品',
  '其他',
] as const

export const G10_FV_LEVEL_OPTIONS = ['Level1', 'Level2', 'Level3'] as const

import { G10_ADJUDICATION_ITEMS, G10_GROUP_LABELS } from './g10AdjudicationItems'

export { G10_ADJUDICATION_ITEMS, G10_GROUP_LABELS }

export const G10_COMPLIANCE_OPTIONS = [
  { value: 'compliant', label: '合规' },
  { value: 'non_compliant', label: '不合规' },
  { value: 'not_applicable', label: '不适用' },
] as const

export const G10_RISK_LEVEL_OPTIONS = [
  { value: 'high', label: '高' },
  { value: 'medium', label: '中' },
  { value: 'low', label: '低' },
] as const

export const G10_VALUATION_METHOD_OPTIONS = [
  '市场法', '收益法', '成本法', '期权定价模型', '其他',
] as const

/** 附注披露（上市）审定 24 行 + 明细 22 行 = 46 行（+合计=47） */
const _LISTED_SUB_ROWS: G10LineDef[] = [
  { rowKey: 'listed_sub_1', label: '    其中：指定为FVTPL的债券负债' },
  { rowKey: 'listed_sub_2', label: '    其中：卖出回购负债' },
  { rowKey: 'listed_sub_3', label: '    其中：融券负债' },
  { rowKey: 'listed_sub_4', label: '    其中：远期金融负债' },
  { rowKey: 'listed_sub_5', label: '    其中：期权金融负债' },
  { rowKey: 'listed_sub_6', label: '    其中：互换金融负债' },
  { rowKey: 'listed_sub_7', label: '    其中：期货金融负债' },
  { rowKey: 'listed_sub_8', label: '    其中：结构化产品负债' },
  { rowKey: 'listed_sub_9', label: '    其中：嵌入衍生拆分负债' },
  { rowKey: 'listed_sub_10', label: '    其中：Level1公允价值负债' },
  { rowKey: 'listed_sub_11', label: '    其中：Level2公允价值负债' },
  { rowKey: 'listed_sub_12', label: '    其中：Level3公允价值负债' },
  { rowKey: 'listed_sub_13', label: '减：公允价值变动（以"-"填列）' },
  { rowKey: 'listed_sub_14', label: '    其中：计入当期损益的公允价值变动' },
  { rowKey: 'listed_sub_15', label: '    其中：利息费用' },
  { rowKey: 'listed_sub_16', label: '    其中：到期/提前清偿' },
  { rowKey: 'listed_sub_17', label: '    其中：新发行/新确认' },
  { rowKey: 'listed_sub_18', label: '    其中：转入第三层次' },
  { rowKey: 'listed_sub_19', label: '    其中：转出第三层次' },
  { rowKey: 'listed_sub_20', label: '    其中：关联方交易性金融负债' },
  { rowKey: 'listed_sub_21', label: '    其中：境外发行负债' },
  { rowKey: 'listed_sub_22', label: '    其中：其他交易性金融负债' },
]

export const G10_DISCLOSURE_LISTED_ROWS: G10LineDef[] = [
  ...G10_ADJUDICATION_ITEMS,
  ..._LISTED_SUB_ROWS,
]

/** 附注披露（国企）审定 24 行 + 明细 59 行 = 83 行（+合计=84，虚拟滚动） */
const _SOE_EXTRA_ROWS: G10LineDef[] = Array.from({ length: 59 }, (_, i) => ({
  rowKey: `soe_sub_${i + 1}`,
  label: [
    '    其中：指定FVTPL金融负债', '    其中：衍生金融负债', '    其中：卖出回购',
    '    其中：融券负债', '    其中：结构化产品', '    其中：Level1层次',
    '    其中：Level2层次', '    其中：Level3层次', '    其中：公允价值变动',
    '    其中：利息费用', '    其中：到期终止', '    其中：新发行确认',
    '    其中：关联方负债', '    其中：境外负债', '    其中：嵌入衍生',
    '减：重分类至其他负债', '    其中：信用风险敞口', '    其中：流动性风险',
    '    其中：名义金额披露', '    其中：敏感性分析',
  ][i % 20] + (i >= 20 ? `（${Math.floor(i / 20) + 1}）` : ''),
}))

export const G10_DISCLOSURE_SOE_ROWS: G10LineDef[] = [
  ...G10_ADJUDICATION_ITEMS,
  ..._SOE_EXTRA_ROWS,
]

export const G10_DISCLOSURE_FORMULA_MAP = [
  { field: '附注合计-本期', source: 'G10-1审定表', formula: 'SUM(closingAdjusted) → substantive:adjudicated EventBus', account: '2101' },
  { field: '附注各行-本期', source: 'G10-2明细', formula: '按 liabilityType 汇总 closingAdjusted', account: '2101' },
  { field: '附注合计-上期', source: 'G10-adj-prior', formula: 'openingAdjusted 各业务行', account: '2101' },
  { field: '变动额/变动率', source: '计算', formula: 'currentAmount - priorAmount; rate=prior≠0', account: '-' },
] as const
