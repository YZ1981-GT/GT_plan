/**
 * 审计年度解析 + 试算取数（修补 D~N/G 类缺 year 导致 422 静默失败）
 */
import { computed, inject, unref, type ComputedRef, type MaybeRef } from 'vue'
import { fetchTrialBalanceRows, tbNumber, tbRowsUnder } from '@/services/trialBalanceRows'
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

/** 拉取指定年度、科目前缀下的试算行（经试算表唯一入口；后端按前缀筛） */
export async function fetchTrialBalanceByPrefix(
  projectId: string,
  year: number,
  accountPrefix: string,
): Promise<any[]> {
  const result = await fetchTrialBalanceRows(projectId, {
    year,
    accountPrefix,
    silent: true,
  })
  return result.rows
}

/** 从试算行解析金额（审定优先） */
export function pickTbAmount(hit: any): number {
  if (!hit) return 0
  const audited = tbNumber(hit.audited_amount)
  if (audited != null) return audited
  const unadjusted = tbNumber(hit.unadjusted_amount)
  return unadjusted ?? 0
}

/**
 * 按科目前缀取科目及其明细之和（逐行审定优先、其次未审，与报表 TB() 同口径）；无 year / 无匹配返回 null。
 * 原先只取首条匹配行：有明细科目时少计。
 */
export async function fetchTbAmountByPrefix(
  projectId: string,
  year: number | null,
  accountPrefix: string,
): Promise<number | null> {
  if (!projectId || year == null) return null
  try {
    const family = tbRowsUnder(await fetchTrialBalanceByPrefix(projectId, year, accountPrefix), accountPrefix)
    if (!family.length) return null
    return family.reduce((sum, r) => sum + pickTbAmount(r), 0)
  } catch {
    return null
  }
}
