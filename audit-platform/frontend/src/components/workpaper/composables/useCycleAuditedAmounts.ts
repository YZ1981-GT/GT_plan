import { ref, unref, type MaybeRef } from 'vue'
import { api } from '@/services/apiProxy'

export interface CycleAuditedAmounts {
  summary?: string
  asset_total: number | null
  liability_total: number | null
  equity_total: number | null
  revenue_total: number | null
  expense_total: number | null
}

const cache = new Map<string, CycleAuditedAmounts>()
const pending = new Map<string, Promise<CycleAuditedAmounts>>()
const FIELDS = ['asset_total', 'liability_total', 'equity_total', 'revenue_total', 'expense_total'] as const

function toNumber(value: unknown): number | null {
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

export function normalizeCycleAuditedAmounts(value: unknown): CycleAuditedAmounts {
  const raw = (value && typeof value === 'object' && 'data' in value
    ? (value as { data?: unknown }).data
    : value) as Record<string, unknown> | null
  const source = raw && typeof raw === 'object' ? raw : {}
  return {
    summary: typeof source.summary === 'string' ? source.summary : undefined,
    asset_total: toNumber(source.asset_total),
    liability_total: toNumber(source.liability_total),
    equity_total: toNumber(source.equity_total),
    revenue_total: toNumber(source.revenue_total),
    expense_total: toNumber(source.expense_total),
  }
}

export function clearCycleAuditedAmountsCache(): void {
  cache.clear()
  pending.clear()
}

export async function fetchCycleAuditedAmounts(
  projectId: string,
  year: number,
): Promise<CycleAuditedAmounts> {
  const key = `${projectId}:${year}`
  const cached = cache.get(key)
  if (cached) return cached
  const inFlight = pending.get(key)
  if (inFlight) return inFlight

  const request = api.get<CycleAuditedAmounts>(
    `/api/projects/${encodeURIComponent(projectId)}/auto-data/cycle_audited_amounts`,
    { params: { year }, _silent: true } as any,
  ).then((response) => {
    const result = normalizeCycleAuditedAmounts(response)
    cache.set(key, result)
    return result
  }).finally(() => pending.delete(key))

  pending.set(key, request)
  return request
}

export function useCycleAuditedAmounts(
  projectId: MaybeRef<string | undefined>,
  year: MaybeRef<number | null | undefined>,
) {
  const amounts = ref<CycleAuditedAmounts | null>(null)
  const loading = ref(false)
  const error = ref('')
  let loadedKey = ''

  async function load(): Promise<CycleAuditedAmounts | null> {
    const pid = String(unref(projectId) || '').trim()
    const auditYear = Number(unref(year))
    if (!pid || !Number.isInteger(auditYear) || auditYear <= 0) return null
    const key = `${pid}:${auditYear}`
    if (loadedKey === key && amounts.value) return amounts.value

    loadedKey = key
    loading.value = true
    error.value = ''
    try {
      amounts.value = await fetchCycleAuditedAmounts(pid, auditYear)
      return amounts.value
    } catch {
      amounts.value = null
      error.value = '暂时无法读取审定数'
      return null
    } finally {
      loading.value = false
    }
  }

  return { amounts, loading, error, load, fields: FIELDS }
}
