/**
 * confirmationDicts.ts — 函证模块统一枚举字典 key 注册表
 *
 * 归集 D0-1 ~ D0-8 全部 11 类枚举 key，去重统一。
 * 后端 system_dicts.py 中 confirmation_dicts 命名空间一一对应。
 * 前端通过 GET /dicts 拉取后按此 key 取值。
 *
 * Sprint 1 Task 1.1: 统一 confirmation_dicts 命名空间
 */

// ─── 统一字典 key 常量（11 类） ──────────────────────────────────────────────

export const CONFIRMATION_DICTS = {
  /** 1. 科目大类（应收账款/合同负债/其他应收款/预付账款/应付账款/其他应付款/短期借款/长期借款/银行存款/定期存款/理财产品/其他货币资金/其他） */
  ACCOUNT_TYPE: 'confirmation_account_type',

  /** 2. 函证方式（积极式/消极式） */
  METHOD: 'confirmation_method',

  /** 3. 回函方式（原件寄回/传真/电子邮件/当面确认） */
  REPLY_METHOD: 'confirmation_reply_method',

  /** 4. 发函结果（送抵/退回/无法送达） */
  SEND_RESULT: 'confirmation_send_result',

  /** 5. 跟函场景（现场确认/留函后收回/电话核实） */
  FOLLOWUP_SCENARIO: 'confirmation_followup_scenario',

  /** 6. 差异类型（时间性差异/记账差异/未达账项/其他） */
  DIFF_TYPE: 'confirmation_diff_type',

  /** 7. 抽样方式（统计抽样/非统计抽样/全部发函/其他） */
  SAMPLING_METHOD: 'sampling_method',

  /** 8. 回函可靠性结论（可靠/部分可靠/不可靠） */
  REPLY_RELIABILITY: 'confirmation_reply_reliability',

  /** 9. 函证状态（12 态状态机） */
  STATUS: 'confirmation_status',

  /** 10. 是/否 */
  YES_NO: 'yes_no',

  /** 11. 是/否/不适用 */
  YES_NO_NA: 'yes_no_na',
} as const

export type ConfirmationDictKey = typeof CONFIRMATION_DICTS[keyof typeof CONFIRMATION_DICTS]

// ─── 按组件使用频次映射（方便各 D0 组件引用） ────────────────────────────────

/** D0-1 函证汇总表使用的字典 */
export const D01_DICT_KEYS = [
  CONFIRMATION_DICTS.ACCOUNT_TYPE,
  CONFIRMATION_DICTS.METHOD,
  CONFIRMATION_DICTS.REPLY_METHOD,
  CONFIRMATION_DICTS.SAMPLING_METHOD,
  CONFIRMATION_DICTS.STATUS,
  CONFIRMATION_DICTS.YES_NO,
] as const

/** D0-2 核实被函证单位使用的字典 */
export const D02_DICT_KEYS = [
  CONFIRMATION_DICTS.ACCOUNT_TYPE,
  CONFIRMATION_DICTS.SEND_RESULT,
  CONFIRMATION_DICTS.YES_NO,
  CONFIRMATION_DICTS.YES_NO_NA,
] as const

/** D0-3 跟函过程控制使用的字典 */
export const D03_DICT_KEYS = [
  CONFIRMATION_DICTS.FOLLOWUP_SCENARIO,
  CONFIRMATION_DICTS.YES_NO,
] as const

/** D0-4 差异调节表使用的字典 */
export const D04_DICT_KEYS = [
  CONFIRMATION_DICTS.ACCOUNT_TYPE,
  CONFIRMATION_DICTS.DIFF_TYPE,
  CONFIRMATION_DICTS.YES_NO,
] as const

/** D0-4b 差异检查表使用的字典 */
export const D04B_DICT_KEYS = [
  CONFIRMATION_DICTS.ACCOUNT_TYPE,
] as const

/** D0-5/D0-6 替代程序使用的字典 */
export const D05_D06_DICT_KEYS = [
  CONFIRMATION_DICTS.ACCOUNT_TYPE,
  CONFIRMATION_DICTS.SAMPLING_METHOD,
  CONFIRMATION_DICTS.YES_NO,
] as const

/** D0-7 回函可靠性验证使用的字典 */
export const D07_DICT_KEYS = [
  CONFIRMATION_DICTS.REPLY_METHOD,
  CONFIRMATION_DICTS.REPLY_RELIABILITY,
  CONFIRMATION_DICTS.YES_NO,
] as const

/** D0-8 舞弊风险评价使用的字典 */
export const D08_DICT_KEYS = [
  CONFIRMATION_DICTS.YES_NO_NA,
  CONFIRMATION_DICTS.STATUS,
] as const

// ─── 辅助：全量字典 key 数组（批量拉取用） ──────────────────────────────────

export const ALL_CONFIRMATION_DICT_KEYS = Object.values(CONFIRMATION_DICTS)
