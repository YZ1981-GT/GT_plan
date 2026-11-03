export type AppendStrategy = 'skip' | 'overwrite'

export const VOUCHER_DIFF_STATUS = {
  OK: 'ok',
  FAILED: 'failed',
} as const

export interface IncrementalUploadRequest {
  year: number
  strategy: AppendStrategy
  filePeriods: number[]
}

export interface MergeTableResult {
  copied_rows?: number
  carried?: boolean
  actual_rows?: number
}

export interface LedgerAppendReport {
  strategy?: AppendStrategy
  base_dataset_id?: string | null
  no_base?: boolean
  file_months?: number[]
  inherited_months?: number[]
  skipped_months?: number[]
  overwritten_months?: number[]
  balance_confirmation_required?: boolean
  balance_carry_confirmed?: boolean
  tables?: Record<string, MergeTableResult>
}

export interface VoucherDiffCell {
  count?: number
  amount?: string
  net_amount_change?: string
}

export interface VoucherDiffReport {
  status?: 'ok' | 'failed' | 'not_applicable' | string
  reason?: string
  duration_ms?: number
  summary?: Record<'added' | 'deleted' | 'modified', VoucherDiffCell>
  samples?: Record<string, Array<Record<string, unknown>>>
}

export function monthList(value: number[] | undefined): string {
  return value?.length ? value.map(month => `${month} 月`).join('、') : '无'
}

export function carriedSnapshotTables(report: LedgerAppendReport | null | undefined): string[] {
  const labels: Record<string, string> = {
    tb_balance: '科目余额表',
    tb_aux_balance: '辅助余额表',
    account_chart: '客户科目表',
    direction_override: '方向修正',
  }
  return Object.entries(report?.tables || {})
    .filter(([, value]) => value?.carried)
    .map(([key]) => labels[key] || key)
}


export function normalizeIncrementalRequest(value: IncrementalUploadRequest): IncrementalUploadRequest {
  const periods = [...new Set(value.filePeriods)]
    .filter(month => Number.isInteger(month) && month >= 1 && month <= 12)
    .sort((a, b) => a - b)
  return {
    year: value.year,
    strategy: value.strategy,
    filePeriods: periods,
  }
}

export function voucherDiffEntries(report: VoucherDiffReport | null | undefined) {
  const labels: Record<string, string> = {
    added: '新增凭证',
    deleted: '删除凭证',
    modified: '分录变化',
  }
  return (['added', 'deleted', 'modified'] as const).map(key => {
    const value = report?.summary?.[key] || {}
    return {
      key,
      label: labels[key],
      count: Number(value.count || 0),
      amount: value.amount || '0.00',
      netAmountChange: value.net_amount_change || '0.00',
    }
  })
}


export function buildIncrementalDetectBody(request: IncrementalUploadRequest) {
  const normalized = normalizeIncrementalRequest(request)
  return {
    year: normalized.year,
    file_periods: normalized.filePeriods,
    overlap_strategy: normalized.strategy,
  }
}

export function appendFormFields(
  request: IncrementalUploadRequest | null | undefined,
  balanceCarryConfirmed: boolean,
): Record<string, string> {
  if (!request) return {}
  return {
    append_strategy: request.strategy,
    balance_carry_confirmed: String(balanceCarryConfirmed),
  }
}
