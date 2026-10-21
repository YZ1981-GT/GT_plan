/**
 * 公式参数值智能补全——映射表与静态候选。
 * spec: formula-input-param-completion · Task 1
 */

export interface CandidateItem {
  /** 插入公式的值（不含引号） */
  value: string
  /** 下拉展示标签 */
  label: string
}

export type CandidateSource =
  | 'account_codes'
  | 'tb_fields'
  | 'report_rows'
  | 'report_fields'
  | 'wp_codes'
  | 'static'

export interface ParamCandidateConfig {
  source: CandidateSource
  staticItems?: CandidateItem[]
}

/** TB 第二参数：字段名候选 */
export const TB_FIELDS: CandidateItem[] = [
  { value: '期末余额', label: '期末余额（audited_amount）' },
  { value: '期初余额', label: '期初余额（opening_balance）' },
  { value: '发生额', label: '本期发生额' },
  { value: '变动额', label: '变动额（期末-期初）' },
  { value: 'AJE调整', label: '审计调整净额' },
  { value: 'RJE调整', label: '重分类调整净额' },
]

/** REPORT 第二参数：字段名候选 */
export const REPORT_FIELDS: CandidateItem[] = [
  { value: '期末', label: '本期金额（current_period_amount）' },
  { value: '期初', label: '上期金额（prior_period_amount）' },
]

/** ADJ 第二参数：类型候选 */
const ADJ_TYPES: CandidateItem[] = [
  { value: 'aje_net', label: '审计调整净额' },
  { value: 'rje_net', label: '重分类调整净额' },
  { value: 'total_net', label: '调整合计净额' },
]

/** 每个函数每个参数位的候选来源 */
const PARAM_CANDIDATES: Record<string, ParamCandidateConfig[]> = {
  TB: [{ source: 'account_codes' }, { source: 'static', staticItems: TB_FIELDS }],
  SUM_TB: [{ source: 'account_codes' }, { source: 'static', staticItems: TB_FIELDS }],
  ROW: [{ source: 'report_rows' }],
  SUM_ROW: [{ source: 'report_rows' }, { source: 'report_rows' }],
  REPORT: [{ source: 'report_rows' }, { source: 'static', staticItems: REPORT_FIELDS }],
  WP: [{ source: 'wp_codes' }],
  ADJ: [{ source: 'account_codes' }, { source: 'static', staticItems: ADJ_TYPES }],
  AUX: [{ source: 'account_codes' }],
  PREV: [{ source: 'account_codes' }, { source: 'static', staticItems: TB_FIELDS }],
  PRIOR: [{ source: 'account_codes' }, { source: 'static', staticItems: TB_FIELDS }],
  LEDGER: [{ source: 'account_codes' }],
  LEDGER_DETAIL: [{ source: 'account_codes' }],
  TB_AUX: [{ source: 'account_codes' }],
  COUNT_LEDGER: [{ source: 'account_codes' }],
  NOTE: [{ source: 'static', staticItems: [] }], // 附注章节需要动态获取，暂不补全
}

/** 查询某函数某参数位的候选配置；无补全返回 null */
export function getCandidateConfig(funcName: string, argIndex: number): ParamCandidateConfig | null {
  const configs = PARAM_CANDIDATES[funcName]
  if (!configs || argIndex < 0 || argIndex >= configs.length) return null
  return configs[argIndex]
}

/** 前缀过滤候选列表（不区分大小写），最多返回 maxItems 条 */
export function filterCandidates(items: CandidateItem[], prefix: string, maxItems = 50): CandidateItem[] {
  if (!prefix) return items.slice(0, maxItems)
  const lower = prefix.toLowerCase()
  return items.filter(it => it.value.toLowerCase().includes(lower) || it.label.toLowerCase().includes(lower)).slice(0, maxItems)
}
