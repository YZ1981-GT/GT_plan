/**
 * nonSecuritiesDiffTypes — G0-4(非证券) 函证差异核对表类型定义
 *
 * 源模板 `函证差异核对表G0-4(非证券投资)` 15 列，三维差异：
 *   持股比例 / 投资金额 / 投资条款 × 账面·回函·差异
 *
 * 与共享 diffReconcile（单维金额调节 sent/reply/difference）本质不同 → 独立类型，
 * 不改共享 DiffReconcileRow（六枢纽零回归红线，Requirement 2.4 / 5.1）。
 * 列集合对 g0DiffSourceManifest 的 NONSECURITIES_DIFF_COLUMNS（Requirement 2.5 / 6.1）。
 */

export type DiffReason =
  | '计量方法差异'
  | '权益变动未同步'
  | '协议条款理解差异'
  | '其他'

/** 是否需要调账（判断列，源模板 G0-4·N 列） */
export type NeedAdjust = '是' | '否' | '待定'

/** 投资条款差异（源模板 G0-4·K 列，条款维不做数值相减，Requirement 2.3） */
export type TermMatch = '一致' | '不一致'

export interface NonSecuritiesDiffRow {
  _row_id?: string
  seq?: number
  /** 询证函索引号（源 G0-4·A，关联 G0-1） */
  confirm_index?: string
  /** 被投资单位名称（源 G0-4·B） */
  entity_name?: string
  // ─── 维度①持股比例（百分点，scale=百分比数值，如 30 表示 30%） ───
  /** 账面持股比例 %（源 G0-4·C） */
  booked_ratio?: number
  /** 账面投资金额（源 G0-4·D） */
  booked_amount?: number
  /** 账面其他投资限制/投资条款（源 G0-4·E，文本） */
  booked_term?: string
  /** 回函持股比例 %（源 G0-4·F） */
  reply_ratio?: number
  /** 回函投资金额（源 G0-4·G） */
  reply_amount?: number
  /** 回函其他投资限制/投资条款（源 G0-4·H，文本） */
  reply_term?: string
  /** 差异比例（源 G0-4·I，= 账面 − 回函，百分点，只读派生） */
  ratio_diff?: number
  /** 差异金额（源 G0-4·J，= 账面 − 回函，只读派生） */
  amount_diff?: number
  /** 投资条款差异（源 G0-4·K，判断列，不做数值相减） */
  term_match?: TermMatch
  /** 差异原因（源 G0-4·L） */
  diff_reason?: DiffReason | string
  /** 相关支持性证据（源 G0-4·M） */
  support_evidence?: string
  /** 是否需要调账（源 G0-4·N，判断列） */
  need_adjust?: NeedAdjust
  /** 备注（源 G0-4·O） */
  remark?: string
  // ─── 源外增强（非渲染列/可选补充数据，登记于 manifest NONSECURITIES_SOURCE_EXTRA） ───
  /** 条款差异说明（term_match=不一致 时补充） */
  term_diff_note?: string
  /** 调整分录索引（需要调账时跳转 AJE） */
  adj_ref_index?: string
  /** 数据来源标识（manual/hydrated-from-reconcile） */
  _source?: string
}

export interface NonSecuritiesDiffPayload {
  _format: 'diff-nonsecurities-v1'
  rows: NonSecuritiesDiffRow[]
  conclusion?: string
  audit_note?: string
}

export interface NonSecuritiesDiffMetrics {
  total_count: number
  /** 有差异笔数（比例/金额/条款任一有差异） */
  diff_count: number
  no_diff_count: number
  /** 金额差异绝对值合计 */
  amount_diff_abs_total: number
}
