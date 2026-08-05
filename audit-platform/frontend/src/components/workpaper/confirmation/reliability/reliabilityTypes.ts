/**
 * reliabilityTypes.ts — D0-7 邮件/传真回函可靠性验证 类型定义
 *
 * 核心设计：
 * - 中等宽度~14列单层网格（与 D0-4 类似，无需 master-detail）
 * - 条件列：寄回原件=是 → 灰掉验证6列；=否 → 展开身份确认+邮箱验证+致电
 * - 从 D0-1 带入"回函方式=传真/电子邮件"行（confirm_index 去重）
 * - 质量红线：未验证=橙, 不可靠=红
 * - 结论枚举：可靠/部分可靠需补充/不可靠
 */

// ─── 可靠性验证明细行（~18 字段） ───────────────────────────────────────────

export interface ReliabilityRow {
  /** 内部行 ID（UUID，前端生成） */
  _row_id?: string
  /** 序号 */
  seq?: number
  /** 函证索引号（全局唯一主键，跨 D0 系列引用） */
  confirm_index?: string
  /** 被询证单位名称 */
  entity_name?: string
  /** 回函方式（传真/电子邮件） */
  reply_method?: string
  /** 回函日期 */
  reply_date?: string

  // ─── 条件控制列 ─────────────────────────────────────────────────────────

  /** 是否寄回原件（是/否）—— 控制验证6列的展开/灰掉 */
  original_returned?: '是' | '否'

  // ─── 验证列（寄回原件=否时需填） ───────────────────────────────────────

  /** 身份已确认（注1） */
  identity_verified?: boolean
  /** 身份确认方式（电话确认/邮件确认/见面确认/系统确认） */
  identity_method?: string
  /** 邮箱已验证（注2） */
  email_verified?: boolean
  /** 邮箱域名/类型 */
  email_domain?: string
  /** 是否致电确认 */
  phone_called?: boolean
  /** 电话来源（工商/官网/独立来源） */
  phone_source?: string

  // ─── 结论列 ─────────────────────────────────────────────────────────────

  /** 信息可靠性结论（可靠/部分可靠需补充/不可靠） */
  conclusion_status?: '可靠' | '部分可靠需补充' | '不可靠'
  /** 可靠性说明/备注 */
  reliability_note?: string

  // ─── additive 补列（confirmation-shared-model-extension，Requirement 4.1） ─
  // 全部可选，旧 reliability-v1 payload 读回时为 undefined。
  // 已有等价字段复用不新增（confirm_index=函证索引号 / entity_name=被询证单位名称 /
  //   reply_method=回函方式 / original_returned=是否寄回原件 / email_domain=邮箱域名）。

  /** 是否项目组直接接收 — X0-7 回函可靠性核对（单一真源，Requirement 3.5） */
  direct_received?: '是' | '否' | '不适用'
  /** 传真信息及验证 — X0-7「传真信息及验证」 */
  fax_info_verify?: string
  /** 发函邮箱 — X0-7「发函邮箱」（与 email_domain 并存，双列口径） */
  send_email?: string
  /** 回函邮箱 — X0-7「回函邮箱」 */
  reply_email?: string
  /** 可靠性考虑文本 — X0-7「可靠性考虑」 */
  reliability_consideration?: string

  // ─── 按渠道可靠性核对项（e0-confirmation-completion R7，源 F1-12）────────
  // 全部 optional，旧 payload 读回为 undefined，写回不产生 undefined 键。
  // 按 reply_method 只展开对应渠道列组，其余折叠。

  // 通用（两项，适用所有渠道）
  /** D 回函是否分别由经办人和复核人签名 — 源 F1-12 D 列 */
  signed_by_both?: '是' | '否'
  /** E 签字人员是否与银行公示名单相符 — 源 F1-12 E 列 */
  signer_in_public_list?: '是' | '否'

  // 邮寄渠道（3 项）
  /** H 回函信封上名称、地址是否一致 — 源 F1-12 H 列 */
  envelope_addr_match?: '是' | '否'
  /** I 邮戳显示发出城市或地区是否一致 — 源 F1-12 I 列 */
  postmark_city_match?: '是' | '否'
  /** J 回函信息是否完整 — 源 F1-12 J 列 */
  reply_info_complete?: '是' | '否'

  // 跟函渠道（3 项）
  /** K 是否了解处理函证的通常流程和处理人员 — 源 F1-12 K 列 */
  followup_flow_known?: '是' | '否'
  /** L 是否确认询证函处理人员的身份及权限 — 源 F1-12 L 列 */
  followup_identity_verified?: '是' | '否'
  /** M 处理人员是否按正常流程处理 — 源 F1-12 M 列 */
  followup_normal_process?: '是' | '否'

  // 电子平台渠道（4 项）
  /** N 电子签名信息是否一致 — 源 F1-12 N 列 */
  esign_match?: '是' | '否'
  /** O 回函的 IP 地址是否一致 — 源 F1-12 O 列 */
  ip_match?: '是' | '否'
  /** Q 电子函证平台操作时间 — 源 F1-12 Q 列 */
  platform_op_time?: string
  /** S 意见反馈（如适用）— 源 F1-12 S 列 */
  platform_feedback?: string

  // ─── 元数据 ─────────────────────────────────────────────────────────────

  /** 数据来源标识（auto/manual/import） */
  _source?: string
}

// ─── 看板指标 ────────────────────────────────────────────────────────────────

export interface ReliabilityMetrics {
  /** 总行数 */
  total_count: number
  /** 已验证数（conclusion_status 非空） */
  verified_count: number
  /** 已验证率（%） */
  verified_rate: number
  /** 可靠数 */
  reliable_count: number
  /** 部分可靠数 */
  partial_count: number
  /** 不可靠数 */
  unreliable_count: number
  /** 寄回原件数（免验证） */
  original_returned_count: number
}

// ─── 审计说明 ────────────────────────────────────────────────────────────────

export interface ReliabilityAuditNote {
  /** 验证总体情况说明 */
  note_general?: string
  /** 不可靠情况说明 */
  note_unreliable?: string
  /** 其他事项 */
  note_other?: string
}

// ─── 审计结论 ────────────────────────────────────────────────────────────────

export interface ReliabilityConclusion {
  /** 结论类型（可靠/部分可靠需补充/不可靠） */
  conclusion_type?: '可靠' | '部分可靠需补充' | '不可靠'
  /** 结论说明 */
  conclusion_text?: string
}

// ─── 持久化 payload ──────────────────────────────────────────────────────────

export interface ReliabilityPayload {
  /** 格式版本标识 */
  _format: 'reliability-v1'
  /** 明细行数组 */
  rows: ReliabilityRow[]
  /** 审计说明 */
  audit_note?: ReliabilityAuditNote
  /** 审计结论 */
  conclusion?: ReliabilityConclusion
}
