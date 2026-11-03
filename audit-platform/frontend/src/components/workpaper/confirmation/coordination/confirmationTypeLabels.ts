/**
 * 函证类型 / 状态的中文与选项（spec attachment-confirmation-evidence-loop 需求 5.1，ADR-ACE-05）
 *
 * 六类与后端 `ConfirmationType` 枚举逐项一致（守卫读后端枚举比对）。「从底稿导入」只认按科目取候选的四类：
 * 后端 `_CONFIRM_TYPE_ACCOUNT_PREFIXES` 没有律师 / 其他，传了也只会得到空列表。
 */

export const CONFIRM_TYPE_OPTIONS = [
  { value: 'receivable', label: '应收' },
  { value: 'payable', label: '应付' },
  { value: 'bank', label: '银行' },
  { value: 'loan', label: '借款' },
  { value: 'legal', label: '律师' },
  { value: 'other', label: '其他' },
] as const

export type ConfirmType = (typeof CONFIRM_TYPE_OPTIONS)[number]['value']

/** 「从底稿导入」可选的类型（按科目从辅助余额表取候选） */
export const IMPORTABLE_CONFIRM_TYPES: ReadonlyArray<{ value: ConfirmType; label: string }> = [
  { value: 'bank', label: '银行（货币资金）' },
  { value: 'receivable', label: '应收' },
  { value: 'payable', label: '应付' },
  { value: 'loan', label: '借款' },
]

/** 列表「类型」列的内置筛选项 */
export const CONFIRM_TYPE_FILTERS = CONFIRM_TYPE_OPTIONS.map((o) => ({ text: o.label, value: o.value }))

const TYPE_LABELS: Record<string, string> = Object.fromEntries(CONFIRM_TYPE_OPTIONS.map((o) => [o.value, o.label]))

type TagType = 'success' | 'warning' | 'info' | 'danger' | 'primary' | undefined

const TYPE_TAGS: Record<string, TagType> = {
  bank: 'primary',
  receivable: 'success',
  payable: 'warning',
  loan: 'danger',
  legal: 'info',
}

export function confirmTypeLabel(t: string | null | undefined): string {
  return TYPE_LABELS[t ?? ''] || t || ''
}

export function confirmTypeTagType(t: string | null | undefined): TagType {
  return TYPE_TAGS[t ?? '']
}

export const CONFIRMATION_STATUS_LABELS: Record<string, string> = {
  pending: '待发函',
  sent: '已发函',
  returned: '已回函',
  matched: '相符',
  discrepancy: '差异',
}

export function confirmationStatusLabel(s: string | null | undefined): string {
  return CONFIRMATION_STATUS_LABELS[s ?? ''] || s || ''
}
