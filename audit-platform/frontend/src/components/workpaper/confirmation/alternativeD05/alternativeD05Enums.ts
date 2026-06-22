/**
 * alternativeD05Enums.ts — D0-5 合同负债及销售替代程序 枚举字典 key
 *
 * 与后端 system_dicts.py 中 _DICTS 的 key 一一对应。
 */
export { CONFIRMATION_DICT_KEYS } from '../confirmationEnums'

export const ALTERNATIVE_D05_DICT_KEYS = {
  /** 抽样方法（随机选样/系统选样/货币单元抽样/随意选样） */
  SAMPLING_METHOD: 'sampling_method',
  /** 是/否 */
  YES_NO: 'yes_no',
} as const

export type AlternativeD05DictKey = typeof ALTERNATIVE_D05_DICT_KEYS[keyof typeof ALTERNATIVE_D05_DICT_KEYS]
