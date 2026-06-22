/**
 * fraudRiskEnums.ts — D0-8 舞弊风险评价表枚举
 *
 * 复用 yes_no_na 枚举 + 结论枚举
 */

/** 是否存在 枚举选项 */
export const FRAUD_RISK_EXIST_OPTIONS = [
  { value: '是', label: '是' },
  { value: '否', label: '否' },
  { value: '待核实', label: '待核实' },
  { value: 'NA', label: 'N/A' },
] as const

/** 结论类型枚举 */
export const FRAUD_RISK_CONCLUSION_OPTIONS = [
  { value: 'A', label: 'A — 未发现舞弊风险迹象' },
  { value: 'B', label: 'B — 存在舞弊风险迹象但影响有限' },
  { value: 'C', label: 'C — 存在重大舞弊风险迹象' },
] as const

/** 字典 key 常量 */
export const FRAUD_RISK_DICT_KEYS = {
  /** 是/否/NA */
  YES_NO_NA: 'yes_no_na',
  /** 结论类型 */
  CONCLUSION_TYPE: 'fraud_risk_conclusion',
} as const
