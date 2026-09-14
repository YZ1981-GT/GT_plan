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

  // ─── additive 补列（confirmation-shared-model-extension，Requirement 3） ───
  // 全部可选，旧 entity-verify-v1 payload 读回时为 undefined。
  // Reply_Verification_Block（回函核实块）+ 企查查块缺列。
  // 单一真源（决策 5/Property 8）：回函方式/是否原件/是否直接接收 以 X0-7 为唯一录入位置，
  //   本表 is_original/direct_received 为只读引用（UI 层禁编辑，明示「详见 X0-7」）。

  /** 是否原件（只读引用，权威在 X0-7）— X0-2 回函核实块 */
  is_original?: '是' | '否' | '不适用'
  /** 是否项目组直接收到（只读引用，权威在 X0-7）— X0-2 回函核实块 */
  direct_received?: '是' | '否' | '不适用'
  /** 回函发出地址 — X0-2 回函核实块 */
  reply_from_addr?: string
  /** 回函寄件人 — X0-2 回函核实块 */
  reply_sender?: string
  /** 回函电话 — X0-2 回函核实块 */
  reply_phone?: string
  /** 回函单位名称一致性 — X0-2（点选：是/否/不适用） */
  reply_name_match?: 'consistent' | 'inconsistent' | 'pending'
  /** 回函地址一致性 — X0-2 */
  reply_addr_match?: 'consistent' | 'inconsistent' | 'pending'
  /** 回函电话一致性 — X0-2 */
  reply_phone_match?: 'consistent' | 'inconsistent' | 'pending'
  /** 三项不一致说明（判定不一致时要求填，Requirement 3.4）— X0-2 */
  reply_inconsistent_note?: string
  /** 核实证据索引 — X0-2 */
  verify_evidence_index?: string
  /** 跟函控制过程索引 — X0-2 */
  followup_control_index?: string

  // ─── 企查查块缺列 ─────────────────────────────────────────────────────────
  /** 企查查-邮编 — X0-2 企查查核对块 */
  qcc_zipcode?: string
  /** 企查查-邮箱/传真 — X0-2 企查查核对块 */
  qcc_email_fax?: string
  /** 企查查-不一致说明是否合理 — X0-2（合理/不合理） */
  qcc_inconsistent_reasonable?: '合理' | '不合理' | '不适用'
  /** 企查查-支持性文件索引 — X0-2 */
  qcc_support_index?: string
  /** 企查查-备注 — X0-2 */
  qcc_remark?: string

  // ─── 被审计单位提供侧缺列（源模板 X0-2 E6/H6） ────────────────────────────
  // 🔴 上面的 `qcc_zipcode`/`qcc_email_fax` 是**企查查侧**（源外增强）；
  //    源模板「被审计单位提供的被函证单位信息」块本身也有邮编与邮箱/传真两列。
  // spec: h0-confirmation-source-fidelity-and-linkage R8.2

  /** 邮编（被审计单位提供）— 源模板 X0-2!E6 */
  provided_zipcode?: string
  /** 邮箱/传真（被审计单位提供）— 源模板 X0-2!H6 */
  provided_email_fax?: string

  // ─── 第二次发函的被函证单位信息（源模板 X0-2 AF6:AK6 六列） ────────────────
  // 第一次发函被退回后，重新核实到的单位信息。改造前平台只有二次发函的
  // 日期/方式/结果/退回原因，**没有重新核实到的单位信息落笔位置**。
  // 全部 optional：旧 `entity-verify-v1` 载荷读回为 undefined，写回不产生 undefined 键。
  // spec: h0-confirmation-source-fidelity-and-linkage R8.1

  /** 第二次发函-地址 — 源模板 AF6 */
  second_entity_address?: string
  /** 第二次发函-邮编 — 源模板 AG6 */
  second_entity_zipcode?: string
  /** 第二次发函-联系人 — 源模板 AH6 */
  second_contact_person?: string
  /** 第二次发函-联系电话 — 源模板 AI6 */
  second_contact_phone?: string
  /** 第二次发函-传真 — 源模板 AJ6 */
  second_fax?: string
  /** 第二次发函-信息是否核查一致 — 源模板 AK6（是/否） */
  second_info_verified?: '是' | '否'
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
