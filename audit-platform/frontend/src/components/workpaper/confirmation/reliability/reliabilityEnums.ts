/**
 * reliabilityEnums.ts — D0-7 回函可靠性验证 枚举字典 key
 *
 * 与后端 system_dicts.py 中 _DICTS 的 key 一一对应。
 */
export { CONFIRMATION_DICT_KEYS } from '../confirmationEnums'

export const RELIABILITY_DICT_KEYS = {
  /** 回函方式（原件寄回/传真/电子邮件/当面确认） */
  REPLY_METHOD: 'confirmation_reply_method',
  /** 是/否 */
  YES_NO: 'yes_no',
  /** 可靠性结论（可靠/部分可靠需补充/不可靠） */
  CONCLUSION: 'reply_reliability_conclusion',
  /** 身份确认方式（电话确认/邮件确认/见面确认/系统确认） */
  IDENTITY_METHOD: 'reliability_identity_method',
} as const

export type ReliabilityDictKey = typeof RELIABILITY_DICT_KEYS[keyof typeof RELIABILITY_DICT_KEYS]
