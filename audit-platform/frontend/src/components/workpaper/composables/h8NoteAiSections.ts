/**
 * H8 使用权资产披露说明文本域的 AI section 键集与中文名（单一真源）
 *
 * 用途：
 * 1. 前端两个披露 Tab 的 `useDisclosureNoteAi` 的 `buildSectionId` / `labelOf`；
 * 2. 后端守卫 `test_review_dialog_h_cycle_prompts.py` 从本文件抽键集，断言
 *    `review_dialog._SECTION_PROMPTS` 全部登记（缺一即该按钮回退通用 prompt，
 *    过短的通用 prompt 会诱导模型自造披露内容）。
 *
 * 🔴 `sectionId` 是后端 prompt 字典的键，改名必须同步后端，守卫会拦。
 */
export type H8DisclosureAiVariant = 'listed' | 'soe'

export const H8_NOTE_AI_SECTIONS = {
  listed: {
    shortLow: '短期/低价值租赁费用说明',
    impairment: '减值测试披露说明',
    auditNote: '审计说明',
    auditConclusion: '审计结论',
  },
  soe: {
    impairment: '减值测试披露说明',
    auditNote: '审计说明',
    auditConclusion: '审计结论',
  },
} as const satisfies Record<H8DisclosureAiVariant, Record<string, string>>

export function h8NoteAiSectionId(variant: H8DisclosureAiVariant, key: string): string {
  return `H8-disclosure-${variant}-${key}`
}

export function h8NoteAiLabel(variant: H8DisclosureAiVariant, key: string): string {
  const map = H8_NOTE_AI_SECTIONS[variant] as Record<string, string>
  return map[key] ?? key
}
