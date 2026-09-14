/**
 * 循环底稿 HTML ↔ OnlyOffice 双模式页签文案（全平台统一）
 */
export const DUAL_MODE_LABEL_STRUCTURED = '结构化视图'
export const DUAL_MODE_LABEL_ONLINE = '在线编辑'

export interface DualModeSegmentedOption {
  label: string
  value: string
  disabled?: boolean
}

/** html / onlyoffice 值对（G/D/F/H 等 bundle 通用） */
export function dualModeHtmlOoOptions(opts?: { onlineDisabled?: boolean }): DualModeSegmentedOption[] {
  return [
    { label: DUAL_MODE_LABEL_STRUCTURED, value: 'html' },
    {
      label: DUAL_MODE_LABEL_ONLINE,
      value: 'onlyoffice',
      ...(opts?.onlineDisabled ? { disabled: true } : {}),
    },
  ]
}
