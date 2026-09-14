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

  // ─── 源模板 X0-3 要求但改造前缺失的要素（全部 optional，旧载荷读回为 undefined） ───
  // spec: h0-confirmation-source-fidelity-and-linkage R9.1 / R9.2 / R9.3

  /** 跟函人员（备忘录主语）— 源模板 A10「审计项目组成员[XXX…]」 */
  followup_staff?: string
  /**
   * 陪同情况 — 源模板 A10「与[被审计单位XX部XX]一同/或者在无被审计单位人员陪同下独立至」。
   * 🔴 有无被审计单位人员陪同是**串通舞弊防范的关键证据**，不得省略。
   */
  escort_desc?: string
  /** 办理函证的被函证单位人员工号 — 源模板 A13「工号为[XX]（如有）」 */
  confirm_staff_no?: string
  /** 留函接收人工号 — 源模板 A17 */
  leave_staff_no?: string

  /** 第三方回访：回访人员 — 源模板 A18「跟函人员（或者项目组其他成员）[XX]」 */
  callback_staff?: string
  /** 第三方回访：回访日期 — 源模板 A18 */
  callback_date?: string
  /** 第三方回访：被函证方**对外公开电话** — 源模板 A18 */
  callback_phone?: string
  /** 第三方回访：结果（确认其确实接待过跟函人员）— 源模板 A19 */
  callback_result?: string
  /** 是否已执行第三方回访核实 */
  third_party_callback_done?: boolean
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
