/**
 * H9 租赁负债披露说明文本域的 AI section 键集与中文名（单一真源）
 *
 * 与 `h8NoteAiSections.ts` 同款：前端 `useDisclosureNoteAi` 的 `buildSectionId`
 * 与后端 `review_dialog._SECTION_PROMPTS` 由守卫
 * `test_review_dialog_h_cycle_prompts.py` 交叉锁死。
 */
export type H9DisclosureAiVariant = 'listed' | 'soe'

export const H9_NOTE_AI_SECTIONS = {
  listed: {
    interestNote: '租赁负债利息费用说明',
    auditNote: '审计说明',
    auditConclusion: '审计结论',
  },
  soe: {
    supplementNote: '补充披露说明',
    auditNote: '审计说明',
    auditConclusion: '审计结论',
  },
} as const satisfies Record<H9DisclosureAiVariant, Record<string, string>>

export function h9NoteAiSectionId(variant: H9DisclosureAiVariant, key: string): string {
  return `H9-disclosure-${variant}-${key}`
}

export function h9NoteAiLabel(variant: H9DisclosureAiVariant, key: string): string {
  const map = H9_NOTE_AI_SECTIONS[variant] as Record<string, string>
  return map[key] ?? key
}
