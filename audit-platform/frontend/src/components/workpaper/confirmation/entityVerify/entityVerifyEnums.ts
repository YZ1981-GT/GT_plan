/**
 * entityVerifyEnums.ts — D0-2 枚举常量
 *
 * 大部分复用 D0-1 的 confirmationEnums，仅新增 confirmation_send_result
 */
export { CONFIRMATION_DICT_KEYS } from '../confirmationEnums'

/** D0-2 额外枚举 */
export const ENTITY_VERIFY_DICT_KEYS = {
  /** 发函结果（送抵/退回） */
  SEND_RESULT: 'confirmation_send_result',
  /** 一致性判定（一致/不一致/待核实） */
  CONSISTENCY: 'consistency_status',
} as const
