/**
 * 账套数据页的默认年度。
 *
 * 项目审计年度有账套数据就用它；没有但项目在别的年度有数据，取最近（数值最大）的那个；
 * 项目一个年度都没有数据时才回落到审计年度（页面按空态引导导入）。
 * 取年度列表失败时回落到审计年度，不阻断进入页面。
 */
import api from '@/services/apiProxy'
import { ledger as P_ledger } from '@/services/apiPaths'
import { getProjectAuditYear } from '@/services/auditPlatformApi'

export function pickLedgerDefaultYear(dataYears: unknown[], auditYear: number | null): number | null {
  const years = dataYears.map(Number).filter((y) => Number.isFinite(y) && y > 0)
  if (!years.length) return auditYear
  if (auditYear != null && years.includes(auditYear)) return auditYear
  return Math.max(...years)
}

/** 入口没带年度时的默认年度：项目审计年度 → 无数据则最近有数据的年度。 */
export async function resolveProjectLedgerYear(projectId: string): Promise<number | null> {
  return resolveLedgerDefaultYear(projectId, await getProjectAuditYear(projectId))
}

export async function resolveLedgerDefaultYear(projectId: string, auditYear: number | null): Promise<number | null> {
  try {
    const data: any = await api.get(P_ledger.years(projectId), {
      validateStatus: (s: number) => s === 200 || s === 404, _silent: true,
    } as any)
    return pickLedgerDefaultYear(data?.years ?? [], auditYear)
  } catch {
    return auditYear
  }
}
