/**
 * useAuditSheetSections — 审定表审计说明 / 审计结论区（spec workpaper-frontend-large-component-split, Req 3）
 *
 * 从 GtAuditSheet.vue 抽出：
 * - auditSections ref（notes/conclusion/notes_label/conclusion_label）
 * - buildSections（从 htmlData.audit_sections 构建，缺失回退默认标题）
 * - onSectionChange（readonly 时不修改，行为不变）
 *
 * 铁律：行为零变更、保响应式（ref）；依赖单向（主组件 → composable → htmlData getter）；
 *       composable 之间不互相 import。
 */
import { ref } from 'vue'
import type { AuditSheetHtmlData, AuditSheetSections } from '@/components/workpaper/auditSheetTypes'

export function useAuditSheetSections(options: {
  /** htmlData 取值（getter，保持响应式） */
  htmlData: () => AuditSheetHtmlData | undefined
  /** readonly 取值（getter，保持响应式） */
  readonly: () => boolean
}) {
  const { htmlData } = options

  // ─── 审计说明 / 审计结论区 ───
  const auditSections = ref<Required<AuditSheetSections>>({
    notes: '', conclusion: '', notes_label: '审计说明', conclusion_label: '审计结论',
  })
  function buildSections() {
    const s = htmlData()?.audit_sections || {}
    auditSections.value = {
      notes: s.notes ?? '', conclusion: s.conclusion ?? '',
      notes_label: s.notes_label || '审计说明', conclusion_label: s.conclusion_label || '审计结论',
    }
  }
  buildSections()
  function onSectionChange(field: 'notes' | 'conclusion', value: string) {
    if (options.readonly()) return
    auditSections.value[field] = value ?? ''
  }

  return {
    auditSections,
    buildSections,
    onSectionChange,
  }
}
