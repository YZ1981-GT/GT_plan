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
  /** 函证中心台账投影 id（syncHubFromSummary 写回，平台内部） */
  _hub_confirmation_id?: string

  // ─── additive 补列（confirmation-shared-model-extension） ─────────────────
  // 全部可选字段，旧 confirmation-v1 payload 读回时为 undefined（Requirement 5.1/5.2）
  // 每字段注释源模板出处（Requirement 8.2）；不进 syncHubFromSummary 映射（Property 2）

  /** 选取样本目的 — 源模板 X0-1 首列 */
  sample_purpose?: string
  /** 发函单号 — 源模板 X0-1「发函单号」 */
  send_doc_no?: string
  /** 收件地址核查是否一致 — 源模板 X0-1「收件地址核查是否一致」 */
  send_addr_match?: 'consistent' | 'inconsistent' | 'pending'
  /** 回函快递单号 — 源模板 X0-1「回函快递单号」 */
  reply_courier_no?: string
  /** 回函发出地址 — 源模板 X0-1「回函发出地址」 */
  reply_from_addr?: string
  /** 发函地址与回函地址是否一致 — 源模板 X0-1「发函地址与回函地址是否一致」 */
  send_reply_addr_match?: 'consistent' | 'inconsistent' | 'pending'
  /** 是否采取替代程序 — 源模板 X0-1「是否采取替代程序」 */
  use_alternative?: boolean
  /** 替代后不可确认金额 — 源模板 X0-1「替代后不可确认金额」 */
  alt_unconfirmed?: number

  // ─── K0/L0 variant（源模板 5 段 28 列） ───────────────────────────────────
  /** 发函询证纪要 — K0-1/L0-1「发函询证纪要」段 */
  send_memo?: string
  /** 行级审计结论 — K0-1/L0-1「审计结论」列 */
  row_conclusion?: string

  // ─── E0 variant（原币/本位币/汇率；amount/confirmed_amount 复用为本位币不改语义） ─
  /** 账号或理财产品名称 — E0-1「账号或理财产品名称」 */
  account_no?: string
  /** 汇率 — E0-1「汇率」 */
  fx_rate?: number
  /** 发函金额（原币）— E0-1「发函金额（原币）」（amount 仍为本位币，参与覆盖率/差异计算） */
  amount_orig?: number
  /** 可确认金额（原币）— E0-1「可确认金额（原币）」（confirmed_amount 仍为本位币） */
  confirmed_amount_orig?: number

  // ─── H0 variant（金额或合同条款双口径的条款侧；amount 仍为 number 不改类型） ────
  /** 账面合同条款 — H0-1「金额或合同条款」账面侧 */
  term_book?: string
  /** 回函合同条款 — H0-1「金额或合同条款」回函侧 */
  term_reply?: string
  /** 条款是否一致 — H0-1 条款一致性 */
  term_match?: 'consistent' | 'inconsistent' | 'pending'
  /** 条款差异说明 — H0-1 条款差异说明 */
  term_note?: string
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
  /**
   * 函证覆盖率 = 发函总额(Σ已发函行账面金额) / 科目审定总额(TB population) × 100%。
   * 度量该科目余额被纳入函证程序的比例。population 缺失(无法从 TB 解析)时为 null（不误导）。
   */
  confirmation_coverage: number | null
  /**
   * 确认覆盖率 =（回函确认 + 替代确认金额）/ 科目审定总额(TB population) × 100%。
   * 度量已取得确认证据占科目余额的比例。population 缺失时为 null。
   */
  confirmed_coverage: number | null
  /** 回函覆盖率 = 已回函笔数 / 已发函笔数 × 100%（笔数口径，与公式面板一致） */
  reply_coverage: number
  /** 预警等级 */
  warn_level: 'ok' | 'warn' | 'danger'
  /** 科目审定总额(population)是否可用；false 时 UI 显示占位而非百分比 */
  population_available: boolean
}
