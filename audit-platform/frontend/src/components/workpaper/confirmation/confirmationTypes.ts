/**
 * confirmationTypes.ts — 函证模块（D0 系列）TypeScript 类型定义
 *
 * 覆盖 D0-1 函证汇总表所有数据结构：
 * - ConfirmationRow：28 字段明细行
 * - DashboardMetrics：按科目大类聚合的看板指标
 * - SamplingData / NotesData / ConclusionData：表单区块
 * - ConfirmationPayload：完整持久化 payload（_format='confirmation-v1'）
 * - ConfirmationCoverageMetrics：覆盖率/回函率质量指标
 */

// ─── 明细行（28 字段） ───────────────────────────────────────────────────────

export interface ConfirmationRow {
  /** 内部行 ID（UUID，前端生成） */
  _row_id?: string
  /** 序号 */
  seq?: number
  /** 函证索引号（全局唯一主键，跨 D0 系列引用） */
  confirm_index?: string
  /** 科目大类（应收账款/合同负债/其他应收款等） */
  account_type?: string
  /** 被询证单位名称 */
  entity_name?: string
  /** 地址 */
  entity_address?: string
  /** 联系人 */
  contact_person?: string
  /** 联系电话 */
  contact_phone?: string
  /** 函证金额（账面金额） */
  amount?: number
  /** 币种 */
  currency?: string
  /** 函证方式（积极式/消极式） */
  confirmation_method?: string
  /** 发函日期 */
  send_date?: string
  /** 收函日期 */
  reply_date?: string
  /** 是否已回函 */
  is_replied?: boolean
  /** 回函方式 */
  reply_method?: string
  /** 回函金额 */
  reply_amount?: number
  /** 相符情况（相符/不符/未回函） */
  match_status?: string
  /** 差异金额（自动计算） */
  difference?: number
  /** 可确认金额（业务规则自动） */
  confirmed_amount?: number
  /** 替代程序确认金额 */
  alt_confirmed?: number
  /** 差异调节表索引（跳转 D0-4） */
  diff_ref_index?: string
  /** 替代程序索引（跳转 D0-5/D0-6） */
  alt_ref_index?: string
  /** 备注 */
  remark?: string
  /** 数据来源标识（auto/manual/import） */
  _source?: string
  /** 是否被用户覆盖 */
  _overridden?: boolean
  /** 是否电子回函 */
  electronic_reply?: boolean
  /** 可靠性已验证 */
  reliability_verified?: boolean
  /** 舞弊风险标志 */
  fraud_risk_flag?: boolean
}

// ─── 看板指标（按科目大类聚合） ──────────────────────────────────────────────

export interface DashboardMetrics {
  /** 科目大类 */
  account_type: string
  /** 总笔数 */
  total_count: number
  /** 已回函笔数 */
  replied_count: number
  /** 相符笔数 */
  matched_count: number
  /** 函证总金额 */
  total_amount: number
  /** 可确认金额合计 */
  confirmed_amount: number
  /** 未确认金额合计 */
  unconfirmed_amount: number
  /** 差异金额合计 */
  difference_amount: number
}

// ─── 抽样区块 ────────────────────────────────────────────────────────────────

export interface SamplingData {
  /** 抽样方式 */
  sampling_method?: string
  /** 抽样范围 */
  sampling_scope?: string
  /** 抽样标准 */
  sampling_criteria?: string
  /** 样本量 */
  sampling_size?: string
  /** 抽样结果 */
  sampling_result?: string
  /** 抽样结论 */
  sampling_conclusion?: string
}

// ─── 审计说明区块（5 专题） ──────────────────────────────────────────────────

export interface NotesData {
  /** 函证总体情况说明 */
  note_general?: string
  /** 异常情况说明 */
  note_exception?: string
  /** 未回函处理 */
  note_unreplied?: string
  /** 替代程序说明 */
  note_alternative?: string
  /** 其他事项 */
  note_other?: string
}

// ─── 审计结论区块 ────────────────────────────────────────────────────────────

export interface ConclusionData {
  /** 结论类型：A 无保留 / B 保留 / C 否定 */
  conclusion_type?: 'A' | 'B' | 'C'
  /** 结论说明 */
  conclusion_text?: string
}

// ─── 完整持久化 payload ──────────────────────────────────────────────────────

export interface ConfirmationPayload {
  /** 格式版本标识 */
  _format: 'confirmation-v1'
  /** 明细行数组 */
  rows: ConfirmationRow[]
  /** 汇总配置（可选） */
  summary_config?: { account_types: string[] }
  /** 抽样数据 */
  sampling: SamplingData
  /** 审计说明 */
  notes: NotesData
  /** 审计结论 */
  conclusion: ConclusionData
}

// ─── 覆盖率质量指标 ──────────────────────────────────────────────────────────

export interface ConfirmationCoverageMetrics {
  /** 函证覆盖率（confirmed / total amount） */
  confirmation_coverage: number
  /** 回函覆盖率（replied / total count） */
  reply_coverage: number
  /** 预警等级 */
  warn_level: 'ok' | 'warn' | 'danger'
}
