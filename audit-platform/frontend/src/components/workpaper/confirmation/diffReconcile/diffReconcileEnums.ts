/**
 * diffReconcileEnums.ts — D0-4 函证差异调节表 枚举字典 key
 *
 * 与后端 system_dicts.py 中 _DICTS 的 key 一一对应。
 */
export { CONFIRMATION_DICT_KEYS } from '../coordination/confirmationDicts'

export const DIFF_RECONCILE_DICT_KEYS = {
  /** 科目（应收账款/合同负债/销售收入/…，allow-create 自定义） */
  SUBJECT: 'confirmation_subject',
  /** 差异类型（时间性差异/记账差异/未达账项/其他差异） */
  DIFF_TYPE: 'confirmation_diff_type',
  /** 是/否 */
  YES_NO: 'yes_no',
} as const

export type DiffReconcileDictKey = typeof DIFF_RECONCILE_DICT_KEYS[keyof typeof DIFF_RECONCILE_DICT_KEYS]
