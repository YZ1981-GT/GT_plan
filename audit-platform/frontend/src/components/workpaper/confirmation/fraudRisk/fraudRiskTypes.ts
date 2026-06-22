/**
 * fraudRiskTypes.ts — D0-8 函证程序舞弊风险评价表类型定义
 *
 * 核心设计：
 * - 检查清单式（d-form-qa 类）：预置 ~19 条舞弊风险迹象
 * - 每条评估 3 个字段：是否存在(是/否/NA) + 相关索引 + 应对措施
 * - 条件高亮：是=是 → 行高亮 + 应对空 → 橙色警示
 * - 汇总 → B50 风险评估跳转
 * - 跨循环复用（D0-8/E0-8/F0-8/K0-8 等）
 */

// ─── 预置条目定义（不可变模板） ───────────────────────────────────────────────

export interface FraudRiskItem {
  /** 条目序号（1-19） */
  seq: number
  /** 风险迹象描述文本 */
  description: string
  /** 是否有关联的 tooltip 举例（key → ITEM_TOOLTIPS_D08） */
  tooltip_key?: string
  /** 是否为预置条目 */
  _preset: boolean
}

// ─── 评估行（运行时可编辑） ──────────────────────────────────────────────────

export interface FraudRiskRow {
  /** 内部行 ID（UUID） */
  _row_id?: string
  /** 序号 */
  seq: number
  /** 风险迹象描述（预置条目可编辑适配，自定义条目自由填写） */
  description: string
  /** 是否存在该风险迹象（是/否/NA/待核实） */
  is_exist?: '是' | '否' | 'NA' | '待核实' | ''
  /** 相关索引号（交叉引用，可跳转） */
  source_ref?: string
  /** 应对措施 */
  countermeasure?: string
  /** 是否为预置条目 */
  _preset: boolean
  /** tooltip key（从预置带入） */
  tooltip_key?: string
  /** 数据来源标识 */
  _source?: 'preset' | 'manual' | 'auto'
  /** 是否由上游联动自动填充 */
  _auto_filled?: boolean
}

// ─── 汇总评价 ────────────────────────────────────────────────────────────────

export interface FraudRiskSummary {
  /** 财务报表层次舞弊风险评价 */
  statement_level_risk?: string
  /** 认定层次舞弊风险评价 */
  assertion_level_risk?: string
  /** 初步应对措施 */
  initial_response?: string
  /** 是否存在重大舞弊风险迹象 */
  has_significant_risk?: boolean
  /** B50 索引号（跳转目标） */
  b50_ref?: string
}

// ─── 审计结论 ────────────────────────────────────────────────────────────────

export interface FraudRiskConclusion {
  /** 结论类型 */
  conclusion_type?: 'A' | 'B' | 'C'
  /** 结论说明 */
  conclusion_text?: string
  /** 未决事项提示 */
  pending_note?: string
}

// ─── 看板指标 ────────────────────────────────────────────────────────────────

export interface FraudRiskMetrics {
  /** 总条目数 */
  total_count: number
  /** 存在风险迹象数（is_exist=是） */
  exist_count: number
  /** 已填应对措施数 */
  with_measure_count: number
  /** 未填应对措施数（is_exist=是 且 应对空） */
  without_measure_count: number
  /** 完成率（已评估/总数 %） */
  completion_rate: number
}

// ─── 持久化 payload ──────────────────────────────────────────────────────────

export interface FraudRiskPayload {
  /** 格式版本标识 */
  _format: 'fraud-risk-d08-v1'
  /** 评估行 */
  items: FraudRiskRow[]
  /** 汇总评价 */
  summary: FraudRiskSummary
  /** 审计结论 */
  conclusion: FraudRiskConclusion
}
