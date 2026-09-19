/**
 * G10 附注披露行定义 — 对齐 G10.xlsx / wp_render_schema/generated/G10.yaml
 * 生成参考：backend/wp_templates/G/G10 交易性金融负债.xlsx
 */

export interface G10DisclosureRowDef {
  rowKey: string
  label: string
  /** 父行：金额由子行汇总，只读 */
  isParent?: boolean
}

/** 上市 — 表1 变动表 rows 8-14（row 15 合计） */
export const G10_LISTED_MOVEMENT_ROWS: G10DisclosureRowDef[] = [
  { rowKey: 'mv_trading', label: '交易性金融负债', isParent: true },
  { rowKey: 'mv_trading_bond', label: '    其中：发行的交易性债券' },
  { rowKey: 'mv_derivative', label: '衍生金融负债' },
  { rowKey: 'mv_other', label: '其他' },
  {
    rowKey: 'mv_designated',
    label: '指定为以公允价值计量且其变动计入当期损益的金融负债',
    isParent: true,
  },
  { rowKey: 'mv_designated_bond', label: '    其中：债券' },
  { rowKey: 'mv_hybrid_tool', label: '    其中：混合工具' },
  { rowKey: 'mv_designated_other', label: '其他' },
]

/** 国企 — 表1 余额表 rows 8-13（row 14 合计） */
export const G10_SOE_BALANCE_ROWS: G10DisclosureRowDef[] = [
  { rowKey: 'soe_trading', label: '交易性金融负债', isParent: true },
  { rowKey: 'soe_trading_bond', label: '    其中：发行的交易性债券' },
  { rowKey: 'soe_derivative', label: '衍生金融负债' },
  { rowKey: 'soe_other', label: '其他' },
  {
    rowKey: 'soe_designated',
    label: '指定为以公允价值计量且其变动计入当期损益的金融负债',
    isParent: true,
  },
  { rowKey: 'soe_hybrid_tool', label: '    其中：混合工具' },
  { rowKey: 'soe_designated_other', label: '其他' },
]

/** 上市 — 表2 指定负债明细（期初/期末/理由）默认种子行 */
export const G10_LISTED_DESIGNATED_SEED_LABEL = '发行的普通债权'

/** 上市 — 表3 公允价值变动（信用风险拆分）默认种子行 */
export const G10_FV_CREDIT_SEED_LABEL = '发行的普通债权'

export const G10_DISCLOSURE_COL_LABELS = {
  listed: {
    movement: {
      item: '项  目',
      opening: '期初余额',
      increase: '本期增加',
      decrease: '本期减少',
      closing: '期末余额',
    },
    designated: {
      item: '项  目',
      opening: '期初余额',
      closing: '期末余额',
      reason: '指定的理由和依据',
    },
    fvCredit: (year: number | null) => ({
      item: '项  目',
      fvChange: year ? `${year}年公允价值变动额` : '本年公允价值变动额',
      creditCurrent: '因自身信用风险变动引起的公允价值本年变动额',
      creditCumulative: '因自身信用风险变动引起的公允价值累计变动额',
    }),
    derivative: {
      item: '项  目',
      current: '期末余额',
      prior: '上年年末余额',
    },
  },
  soe: {
    balance: {
      item: '项  目',
      current: '期末公允价值',
      prior: '期初公允价值',
    },
    fvCredit: (year: number | null) => ({
      item: '项  目',
      fvChange: year ? `${year}年公允价值变动额` : '本年公允价值变动额',
      creditCurrent: '因自身信用风险变动引起的公允价值本年变动额',
      creditCumulative: '因自身信用风险变动引起的公允价值累计变动额',
    }),
  },
} as const

export const G10_DISCLOSURE_TOTAL_LABEL = '合  计'

/** 到期支付差额披露句式（对齐 Excel 底稿红字提示） */
export function g10MaturityDiffPlaceholder(year: number | null): string {
  const y = year ?? new Date().getFullYear()
  return `截至${y}年12月31日止，指定为以公允价值计量且其变动计入当期损益的金融负债的账面价值与按合同到期应支付金额之间的差额为______。`
}

/** 披露分项 ↔ G10-1 book_fv 行后缀 */
export const G10_DISC_LINE_SUFFIXES = [
  'trading_bond',
  'derivative',
  'other_trading',
  'designated_bond',
  'hybrid_tool',
  'other_designated',
] as const

export type G10DiscLineSuffix = (typeof G10_DISC_LINE_SUFFIXES)[number]

export const G10_DISC_SUFFIX_TO_MOVEMENT_KEY: Record<G10DiscLineSuffix, string> = {
  trading_bond: 'mv_trading_bond',
  derivative: 'mv_derivative',
  other_trading: 'mv_other',
  designated_bond: 'mv_designated_bond',
  hybrid_tool: 'mv_hybrid_tool',
  other_designated: 'mv_designated_other',
}

export const G10_DISC_SUFFIX_TO_SOE_KEY: Record<G10DiscLineSuffix, string> = {
  trading_bond: 'soe_trading_bond',
  derivative: 'soe_derivative',
  other_trading: 'soe_other',
  designated_bond: 'soe_designated',
  hybrid_tool: 'soe_hybrid_tool',
  other_designated: 'soe_designated_other',
}
