/**
 * useMemoCompose — 备忘录自动拼装 composable
 */
import type { FollowupRow } from '../followupTypes'
import { getTemplate } from '../memoTemplates'

/** 字段英文→中文标签映射 */
const FIELD_LABELS: Record<string, string> = {
  followup_date: '跟函日期',
  entity_name: '被函证单位',
  entity_address: '单位地址',
  confirm_contact: '确认联系人',
  confirm_identity_verified: '身份确认情况',
  confirm_location: '确认地点',
  leave_date: '留函日期',
  leave_contact: '留函联系人',
  follow_call_date: '跟踪致电日期',
  follow_call_phone: '跟踪电话',
  follow_call_result: '跟踪结果',
  received_date: '回函收回日期',
  received_office: '收回办公室',
  received_confirm_index: '函证索引号',
  // ── 源模板 X0-3 要求但改造前缺失的要素（h0 spec R9.1~R9.3） ──
  followup_staff: '跟函人员',
  escort_desc: '陪同情况',           // A10：与被审计单位XX一同 / 无人陪同独立前往
  confirm_staff_no: '处理人工号',     // A13：工号为[XX]（如有）
  leave_staff_no: '留函接收人工号',   // A17
  callback_staff: '回访人员',         // A18
  callback_date: '回访日期',
  callback_phone: '对外公开电话',
  callback_result: '回访结果',
}

export function useMemoCompose() {
  /** 根据行字段自动生成备忘录文本 */
  function compose(row: FollowupRow): { text: string; missingFields: string[] } {
    if (row.memo_overridden) return { text: row.memo_text ?? '', missingFields: [] }

    const template = getTemplate(row.scenario ?? 'immediate', row.later_received)
    const missingFields: string[] = []

    const text = template.replace(/〔(\w+)〕/g, (_match, field) => {
      const value = (row as any)[field]
      if (value != null && value !== '') return String(value)
      missingFields.push(FIELD_LABELS[field] || field)
      return `〔${FIELD_LABELS[field] || field}〕`
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
