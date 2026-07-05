/** G8 其他权益工具投资 — 常量与种子行 */
import { G8_ADJUDICATION_ITEMS, G8_GROUP_LABEL } from './g8AdjudicationItems'
import {
  G8_DISCLOSURE_LISTED_SCHEMA,
  G8_DISCLOSURE_SOE_SCHEMA,
} from './g8SchemaRows'

export { G8_ADJUDICATION_ITEMS, G8_GROUP_LABEL }
export type { G8AdjudicationLineDef } from './g8AdjudicationItems'
export type { G8DisclosureRowDef, G8DisclosureSection } from './g8SchemaRows'

export const G8_ACCOUNT_CODE = '1503'

/** G8-3 调整分录回写目标行（公允价值组首行） */
export const G8_ADJ_WRITEBACK_ROW_KEY = 'fv_1'
export const G8_CHANGE_RATE_THRESHOLD = 0.2
export const G8_VIRTUAL_SCROLL_THRESHOLD = 50

export const G8_FV_LEVEL_OPTIONS = ['Level1', 'Level2', 'Level3'] as const
export const G8_VALUATION_METHOD_OPTIONS = ['市场法', '收益法', '资产基础法', '其他'] as const

export const G8_COMPLIANCE_OPTIONS = [
  { value: 'compliant', label: '合规' },
  { value: 'non_compliant', label: '不合规' },
  { value: 'not_applicable', label: '不适用' },
] as const

export type G8ImportableSheet = 'G8-2' | 'G8-3' | 'G8-4' | 'G8-6'

export const G8_IMPORTABLE_SHEETS: { code: G8ImportableSheet; label: string }[] = [
  { code: 'G8-2', label: 'G8-2 明细表' },
  { code: 'G8-3', label: 'G8-3 调整分录' },
  { code: 'G8-4', label: 'G8-4 公允价值测试' },
  { code: 'G8-6', label: 'G8-6 凭证检查' },
]

export const G8_DISCLOSURE_LISTED_ROWS = G8_DISCLOSURE_LISTED_SCHEMA
export const G8_DISCLOSURE_SOE_ROWS = G8_DISCLOSURE_SOE_SCHEMA
