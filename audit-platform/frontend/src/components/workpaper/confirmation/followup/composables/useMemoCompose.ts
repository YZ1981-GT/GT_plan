/**
 * useMemoCompose — 备忘录自动拼装 composable
 */
import type { FollowupRow } from '../followupTypes'
import { getTemplate } from '../memoTemplates'

export function useMemoCompose() {
  /** 根据行字段自动生成备忘录文本 */
  function compose(row: FollowupRow): { text: string; missingFields: string[] } {
    if (row.memo_overridden) return { text: row.memo_text ?? '', missingFields: [] }

    const template = getTemplate(row.scenario ?? 'immediate', row.later_received)
    const missingFields: string[] = []

    const text = template.replace(/〔(\w+)〕/g, (_match, field) => {
      const value = (row as any)[field]
      if (value != null && value !== '') return String(value)
      missingFields.push(field)
      return `〔${field}〕`  // Keep placeholder highlighted
    })

    return { text, missingFields }
  }

  /** Apply generated memo to row */
  function applyToRow(row: FollowupRow): FollowupRow {
    if (row.memo_overridden) return row
    const { text } = compose(row)
    return { ...row, memo_text: text }
  }

  /** Force regenerate (even if overridden) */
  function regenerate(row: FollowupRow): FollowupRow {
    const templateRow = { ...row, memo_overridden: false }
    const { text } = compose(templateRow)
    return { ...row, memo_text: text, memo_overridden: false }
  }

  return { compose, applyToRow, regenerate }
}
