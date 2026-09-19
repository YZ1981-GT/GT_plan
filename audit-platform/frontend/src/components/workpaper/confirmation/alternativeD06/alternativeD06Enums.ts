/**
 * alternativeD06Enums.ts — D0-6 应收及销售替代程序 枚举字典 key
 *
 * 与 D0-5 完全复用同一组枚举。
 */
export { CONFIRMATION_DICT_KEYS } from '../coordination/confirmationDicts'

export const ALTERNATIVE_D06_DICT_KEYS = {
  /** 抽样方法（随机选样/系统选样/货币单元抽样/随意选样） */
  SAMPLING_METHOD: 'sampling_method',
  /** 是/否 */
  YES_NO: 'yes_no',
} as const

export type AlternativeD06DictKey = typeof ALTERNATIVE_D06_DICT_KEYS[keyof typeof ALTERNATIVE_D06_DICT_KEYS]
