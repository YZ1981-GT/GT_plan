/**
 * diffSecuritiesTypes — G0-3(证券) 函证差异核对表类型定义
 */

export type SecurityType = '股票' | '基金' | '债券' | '其他'

export type DiffReason =
  | '估值时点差异'
  | '交易日与结算日差异'
  | '计量方法差异'
  | '其他'

/** 是否需要调账（判断列，源模板 G0-3·P 列） */
export type NeedAdjust = '是' | '否' | '待定'

export interface SecuritiesDiffRow {
  _row_id?: string
  seq?: number
  /** 询证函索引号（源 G0-3·A，关联 G0-1；additive 补列） */
  confirm_index?: string
  security_name?: string
  /** 资金账号（源 G0-3·C；additive 补列） */
  fund_account?: string
  /** 开户名称（源 G0-3·D；additive 补列） */
  account_holder?: string
  /** 源外增强：证券代码（源模板无，保留不删） */
  security_code?: string
  /** 源外增强：证券类型（源模板无，保留不删） */
  security_type?: SecurityType | string
  confirmed_qty?: number
  booked_qty?: number
  qty_diff?: number
  confirmed_unit_fv?: number
  booked_unit_fv?: number
  fv_diff?: number
  confirmed_market_value?: number
  /** 账面余额（源 G0-3·G，=账面数量×账面市价，只读派生） */
  booked_market_value?: number
  market_value_diff?: number
  diff_reason?: DiffReason | string
  /** 相关支持性证据（源 G0-3·O；additive 补列） */
  support_evidence?: string
  /** 是否需要调账（源 G0-3·P，判断列；additive 补列） */
  need_adjust?: NeedAdjust
  /** 调节事项说明（保留为说明文本；旧数据 adjustment_note 迁移入口） */
  adjustment_note?: string
  verify_conclusion?: string
  remark?: string
}

export interface DiffSecuritiesPayload {
  _format: 'diff-securities-v1'
  rows: SecuritiesDiffRow[]
  conclusion?: string
  audit_note?: string
}

export interface DiffSecuritiesMetrics {
  total_count: number
  diff_count: number
  no_diff_count: number
  max_abs_diff: number
}
