/** G10-1 审定表行定义 — 对齐源模板「审定表G10-1」24 数据行 × 3 分组 */

export interface G10AdjudicationLineDef {
  rowKey: string
  label: string
  group?: string
}

export const G10_LIABILITY_LINE_SUFFIXES = [
  'trading_liability',
  'trading_bond',
  'derivative_liability',
  'other',
  'designated_fvtpl',
  'designated_bond',
  'hybrid_tool',
  'other_designated',
] as const

export type G10LiabilityLineSuffix = (typeof G10_LIABILITY_LINE_SUFFIXES)[number]

const LIABILITY_LINE_TEMPLATES: ReadonlyArray<{ suffix: G10LiabilityLineSuffix; label: string }> = [
  { suffix: 'trading_liability', label: '交易性金融负债' },
  { suffix: 'trading_bond', label: '其中：发行的交易性债券' },
  { suffix: 'derivative_liability', label: '衍生金融负债' },
  { suffix: 'other', label: '其他' },
  { suffix: 'designated_fvtpl', label: '指定为以公允价值计量且其变动计入当期损益的金融负债' },
  { suffix: 'designated_bond', label: '其中：债券' },
  { suffix: 'hybrid_tool', label: '混合工具' },
  { suffix: 'other_designated', label: '其他' },
]

function buildGroupRows(group: G10AdjudicationLineDef['group'], prefix: string): G10AdjudicationLineDef[] {
  return LIABILITY_LINE_TEMPLATES.map((t) => ({
    rowKey: `${prefix}_${t.suffix}`,
    label: t.label,
    group,
  }))
}

/** 24 行：源 xlsx (一)初始金额 / (二)累计公允价值变动 / (三)账面余额（公允价值）各 8 行 */
export const G10_ADJUDICATION_ITEMS: G10AdjudicationLineDef[] = [
  ...buildGroupRows('initial', 'init'),
  ...buildGroupRows('fv_accum', 'fv'),
  ...buildGroupRows('book_fv', 'book'),
]

export const G10_GROUP_LABELS: Record<string, string> = {
  initial: '(一)初始金额',
  fv_accum: '(二)累计公允价值变动',
  book_fv: '(三)账面余额（公允价值）',
}

/** 各分组小计行标签（对齐 Excel G10-1 行 16 / 26 / 36） */
export const G10_GROUP_SUBTOTAL_LABELS: Record<string, string> = {
  initial: '初始成本小计',
  fv_accum: '公允价值变动小计',
  book_fv: '账面余额（公允价值）合计',
}
