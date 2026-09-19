/**
 * 审计年度解析 + 试算取数（修补 D~N/G 类缺 year 导致 422 静默失败）
 */
import { computed, inject, unref, type ComputedRef, type MaybeRef } from 'vue'
import { api } from '@/services/apiProxy'
import { WorkpaperRuntimeContextKey } from './useWorkpaperScaffold'

export function resolveAuditYearNumber(
  ...candidates: Array<MaybeRef<number | string | null | undefined> | number | string | null | undefined>
): number | null {
  for (const c of candidates) {
    const raw = unref(c as any)
    if (raw == null || raw === '') continue
    const n = Number(raw)
    if (Number.isFinite(n) && n >= 1900 && n <= 2100) return Math.trunc(n)
  }
  return null
}

/**
 * 优先显式年度，回退 Runtime Boundary 注入的 project year。
 * 须在 setup / composable 顶层调用（依赖 inject）。
 */
export function useWorkpaperAuditYear(
  explicit?: MaybeRef<number | string | null | undefined>,
): ComputedRef<number | null> {
  const runtime = inject(WorkpaperRuntimeContextKey, null)
  return computed(() => resolveAuditYearNumber(explicit, runtime?.year))
}

/** 拉取试算行；year 必填（后端 Query(...)） */
export async function fetchTrialBalanceByPrefix(
  projectId: string,
  year: number,
  accountPrefix: string,
): Promise<any[]> {
  const res = await api.get(`/api/projects/${projectId}/trial-balance`, {
    params: { year, account_prefix: accountPrefix },
    _silent: true,
  } as any)
  const list = Array.isArray(res?.data ?? res)
    ? (res?.data ?? res)
    : (res?.data?.items ?? [])
  return Array.isArray(list) ? list : []
}

/** 从试算行解析金额（审定优先） */
export function pickTbAmount(hit: any): number {
  if (!hit) return 0
  const n = Number(
    hit.audited_amount
      ?? hit.unadjusted_amount
      ?? hit.ending_balance
      ?? (Number(hit.debit_amount ?? 0) - Number(hit.credit_amount ?? 0)),
  )
  return Number.isFinite(n) ? n : 0
}

/** 按科目前缀取首条匹配金额；无 year/无匹配返回 null */
export async function fetchTbAmountByPrefix(
  projectId: string,
  year: number | null,
  accountPrefix: string,
): Promise<number | null> {
  if (!projectId || year == null) return null
  try {
    const list = await fetchTrialBalanceByPrefix(projectId, year, accountPrefix)
    const hit = list.find((r: any) =>
      String(r.standard_account_code ?? r.account_code ?? '').startsWith(accountPrefix),
    )
    if (!hit) return null
    return pickTbAmount(hit)
  } catch {
    return null
  }
}
