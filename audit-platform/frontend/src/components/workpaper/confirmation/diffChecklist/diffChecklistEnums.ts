/**
 * diffChecklistEnums.ts — D0-4b 函证差异检查表 枚举字典 key
 *
 * 复用 confirmation_subject（与 D0-4 共享科目列），yes_no 通用。
 */
export { CONFIRMATION_DICT_KEYS } from '../coordination/confirmationDicts'

export const DIFF_CHECKLIST_DICT_KEYS = {
  /** 科目（应收账款/合同负债/…，allow-create 自定义） */
  SUBJECT: 'confirmation_subject',
  /** 是/否 */
  YES_NO: 'yes_no',
} as const

export type DiffChecklistDictKey = typeof DIFF_CHECKLIST_DICT_KEYS[keyof typeof DIFF_CHECKLIST_DICT_KEYS]
