/**
 * confirmationEnums.ts — 函证模块枚举字典 key 常量
 *
 * 与后端 system_dicts.py 中 _DICTS 的 key 一一对应。
 * 前端通过 GET /dicts 拉取字典后按此 key 取值。
 */

/** 函证模块枚举字典 key 常量 */
export const CONFIRMATION_DICT_KEYS = {
  /** 科目大类（应收账款/合同负债/其他应收款/预付账款/应付账款/其他应付款/短期借款/长期借款/银行存款/定期存款/理财产品/其他货币资金/其他） */
  ACCOUNT_TYPE: 'confirmation_account_type',
  /** 函证方式（积极式/消极式） */
  METHOD: 'confirmation_method',
  /** 回函方式（原件寄回/传真/电子邮件/当面确认） */
  REPLY_METHOD: 'confirmation_reply_method',
  /** 是/否 */
  YES_NO: 'yes_no',
  /** 相符情况（相符/不符/未回函） */
  MATCH_STATUS: 'confirmation_match',
  /** 抽样方式（统计抽样/非统计抽样/全部发函/其他） */
  SAMPLING_METHOD: 'sampling_method',
} as const

export type ConfirmationDictKey = typeof CONFIRMATION_DICT_KEYS[keyof typeof CONFIRMATION_DICT_KEYS]
