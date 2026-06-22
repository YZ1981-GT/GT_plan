/**
 * entityVerifyTypes.ts — D0-2 核实被函证单位信息 类型定义
 */

/** D0-2 核实行（约38字段） */
export interface EntityVerifyRow {
  _row_id?: string
  seq?: number
  /** 函证索引号（与 D0-1 一一对应，跨表主键） */
  confirm_index?: string
  /** 被审计单位提供的信息 */
  entity_name?: string
  entity_address?: string
  contact_person?: string
  contact_phone?: string
  account_type?: string
  /** 企查查核对信息 */
  qcc_entity_name?: string
  qcc_address?: string
  qcc_contact?: string
  qcc_phone?: string
  /** 一致性判定 */
  name_match?: 'consistent' | 'inconsistent' | 'pending'
  address_match?: 'consistent' | 'inconsistent' | 'pending'
  contact_match?: 'consistent' | 'inconsistent' | 'pending'
  phone_match?: 'consistent' | 'inconsistent' | 'pending'
  /** 地址不一致时的核实 */
  address_verify_result?: string
  address_verify_note?: string
  /** 第一次发函信息 */
  first_send_date?: string
  first_send_method?: string
  first_result?: string  // 送抵/退回
  return_reason?: string
  reason_reasonable?: string  // 合理/不合理
  /** 第二次发函（条件字段：is_second_send=true 时展开） */
  is_second_send?: boolean
  second_send_date?: string
  second_send_method?: string
  second_result?: string
  second_return_reason?: string
  /** 回函信息 */
  reply_method?: string
  reply_date?: string
  /** 电子函证特殊字段 */
  is_electronic?: boolean
  electronic_platform?: string
  electronic_verify_note?: string
  /** 质量标志 */
  _source?: string
  _overridden?: boolean
  /** 反舞弊检测结果 */
  fraud_flags?: string[]
  row_status?: 'ok' | 'suspect' | 'fraud_flag'
}

/** D0-2 进度指标 */
export interface ProgressMetrics {
  total_count: number
  verified_count: number
  pending_count: number
  returned_count: number
  fraud_flag_count: number
  verify_rate: number  // verified / total * 100
  return_rate: number  // returned / total * 100
}

/** D0-2 持久化 payload */
export interface EntityVerifyPayload {
  _format: 'entity-verify-v1'
  rows: EntityVerifyRow[]
  progress_summary?: ProgressMetrics
}
