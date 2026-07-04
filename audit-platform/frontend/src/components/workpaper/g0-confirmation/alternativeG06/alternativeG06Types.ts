/**
 * alternativeG06Types — G0-6 投资循环替代程序类型
 */
import type { AlternativeCompany } from '../../confirmation/alternativeD05/alternativeD05Types'

export interface InvestmentBalanceSummary {
  item_name?: string
  investment_type?: string
  opening_balance?: number
  increase_amount?: number
  decrease_amount?: number
  closing_balance?: number
  investment_income?: number
  fv_change?: number
}

export interface AlternativeG06Company extends Omit<AlternativeCompany, 'balance'> {
  balance?: InvestmentBalanceSummary
}

export interface AlternativeG06Payload {
  _format: 'alternative-g06-v1'
  companies: AlternativeG06Company[]
}
