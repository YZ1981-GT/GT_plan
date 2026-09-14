/**
 * 统一借贷不平衡诊断类型定义。
 *
 * 与后端 diagnostics_types.py 字段一一对应。
 * Requirements: 1.1, 1.3, 1.4, 1.5, 6.5
 */

// ---------------------------------------------------------------------------
// Caliber — 平衡口径
// ---------------------------------------------------------------------------

export type Caliber =
  | 'ledger_debit_credit'
  | 'trial_balance_debit_credit'
  | 'balance_vs_ledger'
  | 'balance_sheet_equation'

export const CALIBER_VALUES: Caliber[] = [
  'ledger_debit_credit',
  'trial_balance_debit_credit',
  'balance_vs_ledger',
  'balance_sheet_equation',
]

export const CALIBER_LABELS: Record<Caliber, string> = {
  ledger_debit_credit: '序时账凭证借贷合计',
  trial_balance_debit_credit: '试算表全科目借方合计 vs 贷方合计',
  balance_vs_ledger: '余额表期末 vs 序时账累计',
  balance_sheet_equation: '资产 = 负债 + 权益（报表生成后 BS 勾稽）',
}

// ---------------------------------------------------------------------------
// CauseCode — 原因代码
// ---------------------------------------------------------------------------

export type CauseCode =
  | 'report_line_unmatched'
  | 'sign_convention_anomaly'
  | 'pnl_not_closed_or_caliber_gap'
  | 'source_data_unbalanced'
  | 'manual_review_required'

export const CAUSE_CODE_VALUES: CauseCode[] = [
  'report_line_unmatched',
  'sign_convention_anomaly',
  'pnl_not_closed_or_caliber_gap',
  'source_data_unbalanced',
  'manual_review_required',
]

// ---------------------------------------------------------------------------
// JumpTargetType — 跳转目标类型
// ---------------------------------------------------------------------------

export type JumpTargetType =
  | 'report_line_mapping'
  | 'sign_anomaly_review'
  | 'ledger_penetration'
  | 'data_quality'

export const JUMP_TARGET_TYPE_VALUES: JumpTargetType[] = [
  'report_line_mapping',
  'sign_anomaly_review',
  'ledger_penetration',
  'data_quality',
]

// ---------------------------------------------------------------------------
// Transport — 跳转传参方式
// ---------------------------------------------------------------------------

export type Transport = 'route_query' | 'dialog_prop' | 'event_payload'

export const TRANSPORT_VALUES: Transport[] = [
  'route_query',
  'dialog_prop',
  'event_payload',
]

// ---------------------------------------------------------------------------
// DiagnosticCause — 诊断原因
// ---------------------------------------------------------------------------

export interface DiagnosticCause {
  cause_code: CauseCode
  severity: number // 1-5
  confidence: number // 0.0-1.0
  description: string // 中文解释
  evidence: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// DiagnosticJumpTarget — 跳转目标
// ---------------------------------------------------------------------------

export interface DiagnosticJumpTarget {
  target_type: JumpTargetType
  label: string // 中文按钮文案
  transport: Transport
  params: Record<string, string>
}

// ---------------------------------------------------------------------------
// UnmatchedAccount — 未匹配报表行次科目
// ---------------------------------------------------------------------------

export interface UnmatchedAccount {
  account_code: string
  account_name: string | null
  amount: number
  mapping_status: 'unmapped' | 'seed_missing' | 'unconfirmed'
}

// ---------------------------------------------------------------------------
// CaliberDataSource — 口径数据源定义
// ---------------------------------------------------------------------------

export interface CaliberDataSource {
  table_name: string
  formula: string
  description: string
  top_contributors_source: string
}

export const CALIBER_DATA_SOURCES: Record<Caliber, CaliberDataSource> = {
  ledger_debit_credit: {
    table_name: 'tb_ledger',
    formula: 'SUM(debit_amount) == SUM(credit_amount)',
    description: '序时账全部凭证借方发生额合计应等于贷方发生额合计',
    top_contributors_source: 'voucher_no',
  },
  trial_balance_debit_credit: {
    table_name: 'trial_balance',
    formula: '按方向汇总借方余额合计 == 贷方余额合计',
    description: '试算表按科目类别分方向，借方类（资产+费用）余额合计应等于贷方类（负债+权益+收入）余额合计',
    top_contributors_source: 'standard_account_code',
  },
  balance_vs_ledger: {
    table_name: 'tb_balance + tb_ledger',
    formula: 'closing_balance = opening_balance + SUM(debit_amount) - SUM(credit_amount)',
    description: '余额表期末余额应等于期初余额加借方发生额减贷方发生额',
    top_contributors_source: 'account_code',
  },
  balance_sheet_equation: {
    table_name: 'financial_report',
    formula: '资产合计 = 负债和所有者权益合计',
    description: '资产负债表生成后资产合计应等于负债加所有者权益合计，仅报表生成后使用',
    top_contributors_source: 'report_line_code',
  },
}

// ---------------------------------------------------------------------------
// BalanceDiagnosticsResult — 统一诊断结果
// ---------------------------------------------------------------------------

export interface BalanceDiagnosticsResult {
  caliber: Caliber
  caliber_label: string
  status: 'passed' | 'warning' | 'blocking'
  difference: number
  debit_total: number
  credit_total: number
  asset_total?: number
  liability_equity_total?: number
  likely_causes: DiagnosticCause[]
  unmatched_accounts: UnmatchedAccount[]
  sign_anomalies: Record<string, unknown>[]
  sign_anomalies_unavailable: boolean
  top_contributors: Record<string, unknown>[]
  jump_targets: DiagnosticJumpTarget[]
  data_sources: Record<string, unknown>
}
