/**
 * 附注 per-table guidance 显示逻辑（纯函数，供 DisclosureEditor.vue 与单测复用）
 *
 * 设计来源：.kiro/specs/note-per-table-guidance/design.md「前端：DisclosureEditor.vue」
 *
 * 核心规则：
 * - activeTableGuidance：优先取当前 Tab 表格的 `guidance` 字段，
 *   降级到章节级 `guidance_text`，两者皆空返回 ''。
 * - dismiss 粒度：`note_section:tabIdx`，各表 Tab 独立关闭记忆。
 */

/** 当前激活表格的最小结构（仅关心 guidance 字段，避免与组件类型耦合） */
export interface ActiveTableLike {
  guidance?: string | null
}

/** 章节级附注的最小结构 */
export interface NoteLike {
  note_section?: string | null
  guidance_text?: string | null
}

/**
 * 解析当前 Tab 应显示的提示文字。
 * per-table guidance 优先（非空白），否则降级章节级 guidance_text，皆空返回 ''。
 */
export function resolveActiveTableGuidance(
  activeTable: ActiveTableLike | null | undefined,
  currentNote: NoteLike | null | undefined,
): string {
  const tableGuidance = activeTable?.guidance
  if (typeof tableGuidance === 'string' && tableGuidance.trim()) {
    return tableGuidance
  }
  return currentNote?.guidance_text || ''
}

/**
 * 构造 dismiss 记忆键：`note_section:tabIdx`。
 * 同一章节的不同 Tab 拥有独立的键，互不影响。
 */
export function guidanceDismissKey(
  noteSection: string | null | undefined,
  activeTabIdx: string | number,
): string {
  return `${noteSection ?? ''}:${activeTabIdx}`
}

/**
 * 提示条是否应显示：
 * - guidance 为空白 → 不显示
 * - 当前 `note_section:tabIdx` 已被用户关闭 → 不显示
 */
export function isGuidanceVisible(
  guidance: string,
  noteSection: string | null | undefined,
  activeTabIdx: string | number,
  dismissed: ReadonlySet<string>,
): boolean {
  if (!guidance?.trim()) return false
  return !dismissed.has(guidanceDismissKey(noteSection, activeTabIdx))
}
