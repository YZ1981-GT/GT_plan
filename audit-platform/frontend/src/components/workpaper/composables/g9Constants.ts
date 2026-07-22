/** G9 其他非流动金融资产 — 常量与种子行 */
import { G9_ADJUDICATION_ITEMS, G9_GROUP_LABELS } from './g9AdjudicationItems'

export { G9_ADJUDICATION_ITEMS, G9_GROUP_LABELS }
export type { G9MeasurementCategory, G9AdjudicationLineDef } from './g9AdjudicationItems'

/**
 * G9 主科目码 — 与 wp_account_mapping / 致同 G9 底稿一致。
 * 历史项目可能仍用 1510/1504；取数/回写/调整汇总请配合 g9TbResolve + isG9AccountCode。
 */
export const G9_ACCOUNT_CODE = '1519'
/** 科目名称（试算表按名称回退匹配） */
export const G9_ACCOUNT_NAME = '其他非流动金融资产'
/** 试算表/分录匹配别名（按优先级） */
export const G9_ACCOUNT_ALIASES = ['1519', '1510', '1504'] as const

/** G9-3 调整分录 AJE/RJE 回写目标行（FVTPL 组首行「其他非流动金融资产（合计）」） */
export const G9_ADJ_WRITEBACK_ROW_KEY = 'fvtpl_1'
/** 与平台 G 循环审定表一致：|变动率|>20% 原因分析必填；审计说明中对 |变动率|>30% 作重点说明（对齐 Excel） */
export const G9_CHANGE_RATE_THRESHOLD = 0.2
export const G9_CHANGE_RATE_NOTE_THRESHOLD = 0.3
export const G9_VIRTUAL_SCROLL_THRESHOLD = 50

export const G9_CLASSIFICATION_OPTIONS = ['FVTPL', 'FVOCI', '摊余成本'] as const
/** 附注工具种类（对齐披露四类；衍生归入「其他」） */
export const G9_INSTRUMENT_TYPE_OPTIONS = [
  '债务工具投资',
  '权益工具投资',
  '衍生金融资产',
  '其他',
] as const
export const G9_FV_LEVEL_OPTIONS = ['Level1', 'Level2', 'Level3'] as const
export const G9_VALUATION_METHOD_OPTIONS = ['市场法', '收益法', '资产基础法', '其他'] as const
export const G9_RISK_LEVEL_OPTIONS = [
  { value: 'high', label: '高' },
  { value: 'medium', label: '中' },
  { value: 'low', label: '低' },
] as const

import {
  G9_DISCLOSURE_LISTED_SCHEMA,
  G9_DISCLOSURE_SOE_SCHEMA,
} from './g9SchemaRows'

export type { G9DisclosureRowDef } from './g9SchemaRows'

export const G9_DISCLOSURE_LISTED_ROWS = G9_DISCLOSURE_LISTED_SCHEMA
export const G9_DISCLOSURE_SOE_ROWS = G9_DISCLOSURE_SOE_SCHEMA

export const G9_IMPORTABLE_SHEETS = [
  { code: 'G9-2', label: '明细表' },
  { code: 'G9-3', label: '调整分录' },
  { code: 'G9-4', label: '公允价值测试' },
  { code: 'G9-5', label: '第三层次调节表' },
  { code: 'G9-6', label: '凭证检查' },
  { code: '附注上市', label: '附注披露（上市公司）' },
  { code: '附注国企', label: '附注披露（国企）' },
] as const
