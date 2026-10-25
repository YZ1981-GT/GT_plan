/**
 * useNoteValidationMarks — 附注校验错误标记（左侧目录树红色标记 + 单元格红色边框）
 *
 * 从 `DisclosureEditor.vue` 抽出（该宿主 3398 行 / HARD_CAPS ceiling 1800，
 * 见 `backend/scripts/check/check_file_size.py`）。纯读：只依据 `validationFindings`
 * 派生标记，不写任何状态。
 *
 * 三个判据各自的用途：
 *   hasSectionValidationError   —— 叶子章节节点是否标红
 *   getGroupValidationErrorCount —— 分组节点上的错误计数角标
 *   getCellValidationError       —— 单元格 tooltip 文案（区分余额类 / 宽表类）
 */
import type { ComputedRef, Ref } from 'vue'

/** 校验发现项（只取本模块用到的字段，避免与后端 schema 强耦合） */
export interface NoteValidationFinding {
  note_section: string
  severity: string
  check_type?: string
  message?: string
  expected_value?: unknown
  actual_value?: unknown
}

interface NoteLike {
  note_section?: string
}

interface TableLike {
  rows?: Array<{ is_total?: boolean; formula_type?: string }>
}

export interface UseNoteValidationMarksOptions {
  validationFindings: Ref<NoteValidationFinding[]> | ComputedRef<NoteValidationFinding[]>
  currentNote: Ref<NoteLike | null | undefined> | ComputedRef<NoteLike | null | undefined>
  activeTableData: Ref<TableLike | null | undefined> | ComputedRef<TableLike | null | undefined>
}

export function useNoteValidationMarks(options: UseNoteValidationMarksOptions) {
  const { validationFindings, currentNote, activeTableData } = options

  /** 判断某章节是否有校验错误 */
  function hasSectionValidationError(noteSection: string | undefined): boolean {
    if (!noteSection || !validationFindings.value.length) return false
    return validationFindings.value.some(
      (f) => f.note_section === noteSection && f.severity === 'error',
    )
  }

  /** 获取分组节点下的校验错误数量 */
  function getGroupValidationErrorCount(groupNode: any): number {
    if (!validationFindings.value.length) return 0
    const sections = new Set<string>()
    function collectSections(node: any) {
      if (node?.data?.note_section) sections.add(node.data.note_section)
      if (node?.children) node.children.forEach(collectSections)
    }
    collectSections(groupNode)
    return validationFindings.value.filter(
      (f) => sections.has(f.note_section) && f.severity === 'error',
    ).length
  }

  /** 获取单元格的校验错误信息（用于 tooltip） */
  function getCellValidationError(rowIndex: number, _colIndex: number): string {
    if (!currentNote.value || !validationFindings.value.length) return ''
    const section = currentNote.value.note_section
    // 匹配当前章节的校验错误，检查是否有针对特定行列的错误
    const findings = validationFindings.value.filter(
      (f) => f.note_section === section && f.severity === 'error',
    )
    if (!findings.length) return ''
    // 对合计行（最后一行或 is_total）显示余额类校验错误
    const rows = activeTableData.value?.rows || []
    const row = rows[rowIndex]
    if (row?.is_total) {
      const balanceFinding = findings.find(
        (f) => f.check_type === '余额' || f.check_type === '其中项',
      )
      if (balanceFinding) {
        const expected = balanceFinding.expected_value ?? '-'
        const actual = balanceFinding.actual_value ?? '-'
        return `${balanceFinding.message}（期望: ${expected}, 实际: ${actual}）`
      }
    }
    // 对宽表行检查横向公式错误
    if (row?.formula_type === 'opening_plus_changes') {
      const wideFinding = findings.find((f) => f.check_type === '宽表')
      if (wideFinding) return `${wideFinding.message}`
    }
    return ''
  }

  return { hasSectionValidationError, getGroupValidationErrorCount, getCellValidationError }
}
