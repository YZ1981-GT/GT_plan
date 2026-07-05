/** H10 资产处置损益 — 常量（与 xlsx H10 资产处置损益.xlsx 一致） */
import { H10_ADJUDICATION_ITEMS, type H10AdjudicationLineDef } from './h10AdjudicationItems'

export { H10_ADJUDICATION_ITEMS, type H10AdjudicationLineDef }

export const H10_ACCOUNT_CODE = '6115'
export const H10_CHANGE_RATE_THRESHOLD = 0.2

/** H10-3 调整分录回写目标行 */
export const H10_ADJ_WRITEBACK_ROW_KEY = 'fixed_asset_disposal'

/** 明细表来源底稿下拉 */
export const SOURCE_WP_OPTIONS = [
  { value: 'H1', label: 'H1 固定资产', indexHint: 'H1-8' },
  { value: 'H2', label: 'H2 投资性房地产', indexHint: 'H2-9' },
  { value: 'H3', label: 'H3 在建工程', indexHint: 'H3-5' },
  { value: 'H5', label: 'H5 油气资产', indexHint: 'H5-8' },
  { value: 'H6', label: 'H6 固定资产清理', indexHint: 'H6-2' },
  { value: 'H7', label: 'H7 生产性生物资产', indexHint: 'H7-7' },
  { value: 'H8', label: 'H8 无形资产', indexHint: 'H8-12' },
  { value: 'OTHER', label: '其他', indexHint: '' },
] as const

export type H10SourceWp = (typeof SOURCE_WP_OPTIONS)[number]['value']

/** 附注披露（上市）— xlsx 附注披露信息（上市公司）行 9–16 */
export const H10_DISCLOSURE_LISTED_ROWS: H10AdjudicationLineDef[] = [
  ...H10_ADJUDICATION_ITEMS,
  { rowKey: 'listed_sub_dr', label: '其中：债务重组中因处置非流动资产产生的利得（损失以"-"填列）' },
  { rowKey: 'listed_sub_nm', label: '其中：非货币性资产交换产生的利得（损失以"-"填列）' },
]

/** 附注披露（国企）— xlsx 附注披露信息（国有企业）行 9–15 */
export const H10_DISCLOSURE_SOE_ROWS: H10AdjudicationLineDef[] = [
  ...H10_ADJUDICATION_ITEMS,
  { rowKey: 'soe_sub_dr', label: '其中：债务重组中因处置非流动资产产生的损益' },
]

export const H10_COMPLIANCE_OPTIONS = [
  { value: 'compliant', label: '合规' },
  { value: 'non_compliant', label: '不合规' },
  { value: 'not_applicable', label: '不适用' },
] as const

export type H10ImportableSheet = 'H10-2' | 'H10-3'

export const H10_IMPORTABLE_SHEETS: { code: H10ImportableSheet; label: string }[] = [
  { code: 'H10-2', label: 'H10-2 明细表' },
  { code: 'H10-3', label: 'H10-3 调整分录' },
]

export const H10_API_PREFIX = 'h10'
