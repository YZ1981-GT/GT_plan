/**
 * diffReconcileTypes.ts — D0-4 函证差异调节表 类型定义
 *
 * 核心设计：
 * - 科目列下拉(confirmation_subject + allow-create) 使一张底稿跨科目通用
 * - 三层自动派生：①差异=发函−回函 ②合计/科目小计实时 ③差异原因分析表自动聚合
 * - D0-1 自动带入差异≠0行（confirm_index 去重，_source 标识）
 * - 金额口径=净额(带符号)；差异=0 行淡化；精确小数避浮点漂移
 */

// ─── 差异调节明细行（~15 字段） ───────────────────────────────────────────────

export interface DiffReconcileRow {
  /** 内部行 ID（UUID，前端生成） */
  _row_id?: string
  /** 序号 */
  seq?: number
  /** 函证索引号（全局唯一主键，跨 D0 系列引用） */
  confirm_index?: string
  /** 被询证单位名称 */
  entity_name?: string
  /** 科目（下拉 confirmation_subject + allow-create 自定义） */
  subject?: string
  /** 发函金额（账面金额） */
  sent_amount?: number
  /** 回函金额 */
  reply_amount?: number
  /** 差异金额（自动计算：sent_amount - reply_amount，只读） */
  difference?: number
  /** 差异类型（时间性差异/记账差异/未达账项/其他差异） */
  diff_type?: string
  /** 差异说明 */
  diff_note?: string
  /** 是否需要调整 */
  needs_adjustment?: boolean
  /** 调整分录索引（跳转 AJE） */
  adj_ref_index?: string
  /** 替代程序索引（跳转 D0-5/D0-6） */
  alt_ref_index?: string
  /** 数据来源标识（auto/manual/import） */
  _source?: string
  /** 是否被用户覆盖 */
  _overridden?: boolean
}

// ─── 按科目分组汇总 ──────────────────────────────────────────────────────────

export interface DiffSummaryBySubject {
  /** 科目名称 */
  subject: string
  /** 该科目笔数 */
  count: number
  /** 发函金额合计 */
  sent_total: number
  /** 回函金额合计 */
  reply_total: number
  /** 差异净额合计（带符号） */
  difference_total: number
  /** 差异绝对值合计（防正负抵消误导） */
  difference_abs_total: number
  /** 已分析笔数（diff_type 已填） */
  analyzed_count: number
  /** 需调整笔数 */
  adjustment_count: number
}

// ─── 差异原因分析聚合（按 diff_type） ────────────────────────────────────────

export interface DiffAnalysisGroup {
  /** 差异类型（时间性差异/记账差异/未达账项/其他差异） */
  diff_type: string
  /** 该类型笔数 */
  count: number
  /** 该类型差异净额合计 */
  net_amount: number
  /** 该类型差异绝对值合计 */
  abs_amount: number
  /** 占比（%） */
  percentage: number
  /** 原因说明（可编辑，持久化） */
  note?: string
  /** 应对措施（可编辑，持久化） */
  action?: string
}

// ─── 看板指标 ────────────────────────────────────────────────────────────────

export interface DiffReconcileMetrics {
  /** 总笔数 */
  total_count: number
  /** 差异净额合计（带符号） */
  difference_net_total: number
  /** 差异绝对值合计 */
  difference_abs_total: number
  /** 已分析率（%） */
  analyzed_rate: number
  /** 需调整笔数 */
  adjustment_count: number
  /** 需调整金额合计 */
  adjustment_amount: number
  /** 超重要性笔数 */
  over_materiality_count: number
  /** 类型分布 */
  type_distribution: DiffAnalysisGroup[]
}

// ─── 重要性配置 ──────────────────────────────────────────────────────────────

export interface MaterialityConfig {
  /** 实际执行重要性（performance materiality，来自 B15） */
  performance_materiality?: number
  /** 是否手动覆盖（用户可手填覆盖默认值） */
  is_overridden?: boolean
  /** 数据来源（auto/manual） */
  source?: string
}

// ─── 审计说明 ────────────────────────────────────────────────────────────────

export interface DiffAuditNote {
  /** 差异总体情况说明 */
  note_general?: string
  /** 调整处理说明 */
  note_adjustment?: string
  /** 其他事项 */
  note_other?: string
}

// ─── 审计结论 ────────────────────────────────────────────────────────────────

export interface DiffConclusion {
  /** 结论类型：A 差异已全部查明并调整 / B 部分差异待确认 / C 存在重大未调差异 */
  conclusion_type?: 'A' | 'B' | 'C'
  /** 结论说明 */
  conclusion_text?: string
}

// ─── 持久化 payload ──────────────────────────────────────────────────────────

export interface DiffReconcilePayload {
  /** 格式版本标识 */
  _format: 'diff-reconcile-v1'
  /** 明细行数组 */
  rows: DiffReconcileRow[]
  /** 分析表注释（仅 note/action 持久化，笔数/金额重算不入库） */
  analysis_notes?: Record<string, { note?: string; action?: string }>
  /** 审计说明 */
  audit_note?: DiffAuditNote
  /** 审计结论 */
  conclusion?: DiffConclusion
  /** 重要性配置 */
  materiality_config?: MaterialityConfig
}
