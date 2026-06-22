/**
 * diffChecklistTypes.ts — D0-4b 函证差异检查表（示例）类型定义
 *
 * 核心设计：
 * - 多公司 master-detail：每家差异公司独立做 A-I 双向余额调节
 * - A-I 9步公式链全自动（用户只填 A/E + B/C/F/G 明细行金额）
 * - DetailSubTable 复用结构：B/C/F/G 四区共用子表类型
 * - 从 D0-4 带入：entity_name + subject + A(reply_amount) / E(sent_amount)
 * - 科目列复用 confirmation_subject（与 D0-4 共享）
 */

// ─── 未达明细子表行（B/C/F/G 通用） ──────────────────────────────────────────

export interface SubTableRow {
  /** 内部行 ID */
  _row_id?: string
  /** 序号 */
  seq?: number
  /** 日期1（如入账日期） */
  date1?: string
  /** 日期2（如对方入账日期） */
  date2?: string
  /** 凭证号 */
  voucher_no?: string
  /** 摘要 */
  summary?: string
  /** 金额 */
  amount?: number
  /** 索引号（交叉引用） */
  ref_index?: string
  /** 是否调整 */
  need_adjust?: boolean
}

// ─── 公司级调节数据（master 行） ─────────────────────────────────────────────

export interface DiffChecklistCompany {
  /** 内部 ID */
  _row_id?: string
  /** 序号 */
  seq?: number
  /** 函证索引号（关联 D0-4/D0-1） */
  confirm_index?: string
  /** 被询证单位名称 */
  entity_name?: string
  /** 科目（复用 confirmation_subject） */
  subject?: string

  // ─── A-I 公式链 ───────────────────────────────────────────────────────────

  /** A: 回函金额（对方确认余额） */
  a_reply_amount?: number
  /** B: 对方已收我方未付明细（子表合计，只读） */
  b_total?: number
  /** B 明细子表 */
  b_rows?: SubTableRow[]
  /** C: 我方已付对方未收明细（子表合计，只读） */
  c_total?: number
  /** C 明细子表 */
  c_rows?: SubTableRow[]
  /** D: 调节后对方余额 = A + B - C（只读自动） */
  d_adjusted_reply?: number

  /** E: 账面金额（我方账面余额 / 发函金额） */
  e_book_amount?: number
  /** F: 我方已收对方未付明细（子表合计，只读） */
  f_total?: number
  /** F 明细子表 */
  f_rows?: SubTableRow[]
  /** G: 对方已付我方未收明细（子表合计，只读） */
  g_total?: number
  /** G 明细子表 */
  g_rows?: SubTableRow[]
  /** H: 调节后我方余额 = E + F - G（只读自动） */
  h_adjusted_book?: number

  /** I: 最终差异 = H - D（只读自动，=0 则平衡） */
  i_final_diff?: number

  // ─── 状态 + 审计说明 ──────────────────────────────────────────────────────

  /** 差异状态：balanced / diff / over_materiality */
  status?: 'balanced' | 'diff' | 'over_materiality'
  /** 审计说明（逐公司） */
  audit_note?: string
  /** 是否需要调整 */
  need_adjust?: boolean
  /** 调整分录索引 */
  adj_ref_index?: string
  /** 数据来源标识 */
  _source?: string
}

// ─── 看板指标 ────────────────────────────────────────────────────────────────

export interface DiffChecklistMetrics {
  /** 总公司数 */
  total_count: number
  /** 已平衡公司数（I=0） */
  balanced_count: number
  /** 有差异公司数（I≠0） */
  diff_count: number
  /** 超重要性公司数 */
  over_materiality_count: number
  /** 完成率（已平衡/总数，%） */
  completion_rate: number
  /** 差异净额合计 */
  diff_net_total: number
  /** 差异绝对值合计 */
  diff_abs_total: number
}

// ─── 重要性配置 ──────────────────────────────────────────────────────────────

export interface ChecklistMaterialityConfig {
  /** 实际执行重要性 */
  performance_materiality?: number
  /** 是否手动覆盖 */
  is_overridden?: boolean
  /** 来源 */
  source?: string
}

// ─── 全局审计结论 ────────────────────────────────────────────────────────────

export interface ChecklistConclusion {
  /** 结论类型 */
  conclusion_type?: 'A' | 'B' | 'C'
  /** 结论说明 */
  conclusion_text?: string
}

// ─── 持久化 payload ──────────────────────────────────────────────────────────

export interface DiffChecklistPayload {
  /** 格式版本标识 */
  _format: 'diff-checklist-v1'
  /** 公司列表 */
  companies: DiffChecklistCompany[]
  /** 全局审计说明 */
  global_note?: string
  /** 审计结论 */
  conclusion?: ChecklistConclusion
  /** 重要性配置 */
  materiality_config?: ChecklistMaterialityConfig
}
