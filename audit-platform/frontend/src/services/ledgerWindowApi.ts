/** Ledger window wire adapter: camelCase UI state ↔ snake_case API. */
import api from '@/services/apiProxy'
import { ledger as P_ledger } from '@/services/apiPaths'

export type LedgerWindowKind = 'ledger' | 'aux_ledger'
export type LedgerAmountDirection = 'all' | 'debit' | 'credit'

export interface LedgerWindowQuery {
  kind: LedgerWindowKind
  projectId: string
  year: number
  accountCode: string
  dateFrom?: string | null
  dateTo?: string | null
  keyword?: string | null
  amountDir?: LedgerAmountDirection
  auxType?: string | null
  auxCode?: string | null
  cursor?: string | null
  limit?: number
}

export interface LedgerMonthSummary {
  month: string | null
  label: string
  row_count: number
  debit_total: string
  credit_total: string
  closing_balance: string
  closing_balance_signed: string
  closing_direction: 'debit' | 'credit'
}

export interface LedgerWindowSummary {
  total: number
  annual_opening: string
  annual_opening_signed: string
  annual_opening_direction: 'debit' | 'credit'
  range_opening: string
  range_opening_signed: string
  range_opening_direction: 'debit' | 'credit'
  debit_total: string
  credit_total: string
  undated_count: number
  months: LedgerMonthSummary[]
  warnings: string[]
}

export interface LedgerWindowResponse {
  kind: LedgerWindowKind
  dataset_id: string
  query_fingerprint: string
  entries: Array<Record<string, any>>
  summary: LedgerWindowSummary
  page: {
    limit: number
    page_index: number
    start: number
    end: number
    has_more: boolean
    next_cursor: string | null
  }
  extra_columns: string[]
  subtotals: Array<{ after_entry_id: string; month: LedgerMonthSummary }>
}

function paramsOf(query: LedgerWindowQuery, includePaging = true): Record<string, unknown> {
  const params: Record<string, unknown> = {
    year: query.year,
    amount_dir: query.amountDir ?? 'all',
  }
  if (includePaging) params.limit = query.limit ?? 200
  if (query.dateFrom) params.date_from = query.dateFrom
  if (query.dateTo) params.date_to = query.dateTo
  if (query.keyword?.trim()) params.keyword = query.keyword.trim()
  if (query.kind === 'aux_ledger') {
    if (query.auxType) params.aux_type = query.auxType
    if (query.auxCode) params.aux_code = query.auxCode
  }
  if (includePaging && query.cursor) params.cursor = query.cursor
  return params
}

export async function fetchLedgerWindow(
  query: LedgerWindowQuery,
  signal?: AbortSignal,
): Promise<LedgerWindowResponse> {
  const path = query.kind === 'aux_ledger'
    ? P_ledger.auxWindow(query.projectId, query.accountCode)
    : P_ledger.window(query.projectId, query.accountCode)
  return await api.get<LedgerWindowResponse>(path, {
    params: paramsOf(query), signal, _dedupe: false, _silent: true,
  } as any)
}

export async function downloadLedgerWindow(query: LedgerWindowQuery): Promise<Blob> {
  const path = query.kind === 'aux_ledger'
    ? P_ledger.auxWindowExport(query.projectId, query.accountCode)
    : P_ledger.windowExport(query.projectId, query.accountCode)
  const result = await api.get(path, {
    params: paramsOf({ ...query, cursor: null }, false), responseType: 'blob',
    _dedupe: false, _silent: true,
  } as any)
  return result instanceof Blob ? result : new Blob([result as any])
}

export function ledgerWindowQueryKey(query: LedgerWindowQuery): string {
  const stable = {
    kind: query.kind,
    projectId: query.projectId,
    year: query.year,
    accountCode: query.accountCode,
    dateFrom: query.dateFrom || '',
    dateTo: query.dateTo || '',
    keyword: query.keyword?.trim() || '',
    amountDir: query.amountDir || 'all',
    auxType: query.auxType || '',
    auxCode: query.auxCode ?? null,
    limit: query.limit ?? 200,
  }
  return JSON.stringify(stable)
}
