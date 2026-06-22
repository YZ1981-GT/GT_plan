/**
 * followupTypes.ts — D0-3 跟函函证过程控制 类型定义
 */

export interface FollowupRow {
  _row_id?: string
  seq?: number
  confirm_index?: string
  entity_name?: string
  entity_address?: string
  followup_person?: string
  followup_date?: string
  /** 确认场景 */
  scenario?: 'immediate' | 'later_follow'  // 现场即时确认 / 无法即时确认留函
  /** 现场确认字段 */
  confirm_location?: string
  confirm_time?: string
  confirm_contact?: string
  confirm_identity_verified?: string  // 是/否/不适用
  /** 无法即时确认 - 留函 */
  leave_date?: string
  leave_contact?: string
  follow_call_date?: string
  follow_call_phone?: string  // 独立公开来源电话
  follow_call_result?: string
  /** 三项控制检查 */
  control_process?: string  // 是/否/不适用 (了解流程)
  control_identity?: string  // 是/否/不适用 (确认身份权限)
  control_normal_flow?: string  // 是/否/不适用 (按正常流程)
  control_evidence?: string  // 证据描述
  control_conclusion?: 'pass' | 'fail' | 'incomplete'
  /** 签名 */
  sign_person?: string
  sign_date?: string
  sign_status?: 'signed' | 'unsigned'
  /** 回函收回补记 */
  later_received?: boolean
  received_date?: string
  received_office?: string
  received_confirm_index?: string
  /** 备忘录 */
  memo_text?: string
  memo_overridden?: boolean
  /** 标记 */
  _source?: string
  _overridden?: boolean
}

export interface ControlConclusion {
  pass_count: number
  fail_count: number
  incomplete_count: number
}

export interface SignStatus {
  signed_count: number
  unsigned_count: number
}

export interface FollowupProgressMetrics {
  total_count: number
  signed_count: number
  control_pass_count: number
  control_fail_count: number
  anomaly_count: number
  sign_rate: number
  control_pass_rate: number
}

export interface FollowupPayload {
  _format: 'confirmation-followup-v1'
  rows: FollowupRow[]
  progress_summary?: FollowupProgressMetrics
}
