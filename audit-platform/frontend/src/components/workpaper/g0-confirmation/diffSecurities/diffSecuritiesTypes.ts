/**
 * diffSecuritiesTypes — G0-3(证券) 函证差异核对表类型定义
 */

export type SecurityType = '股票' | '基金' | '债券' | '其他'

export type DiffReason =
  | '估值时点差异'
  | '交易日与结算日差异'
  | '计量方法差异'
  | '其他'

export interface SecuritiesDiffRow {
  _row_id?: string
  seq?: number
  security_name?: string
  security_code?: string
  security_type?: SecurityType | string
  confirmed_qty?: number
  booked_qty?: number
  qty_diff?: number
  confirmed_unit_fv?: number
  booked_unit_fv?: number
  fv_diff?: number
  confirmed_market_value?: number
  booked_market_value?: number
  market_value_diff?: number
  diff_reason?: DiffReason | string
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
