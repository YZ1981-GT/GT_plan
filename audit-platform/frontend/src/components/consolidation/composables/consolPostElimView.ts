/**
 * 四张抵销后表读服务端 canonical projection 的共用取数（batch 3 / ADR-CRW-004）。
 *
 * 抵消分录数唯一真源 = `GET /api/consolidation/post-elimination/{pid}/{year}`（approved 分录派生）。
 * 四张表（长投 / 投资收益 / 少数股东权益 / 资本公积）各按自己的标准科目前缀取逐企业合计与未分配额。
 * 前端只读取、展示，不反推成分录事实。
 */
import type { PostEliminationProjection, PostElimAccount } from '@/services/consolidationApi'

/** 取某科目前缀的权威抵销（无 projection / 无该科目 ⇒ null）。 */
export function accountOf(
  projection: PostEliminationProjection | null | undefined,
  prefix: string,
): PostElimAccount | null {
  return projection?.accounts?.[prefix] ?? null
}

/** 某科目逐企业抵销合计：company_code → 金额（Number，sign 归一后净额）。 */
export function companyElimMap(
  projection: PostEliminationProjection | null | undefined,
  prefix: string,
): Map<string, number> {
  const m = new Map<string, number>()
  for (const s of accountOf(projection, prefix)?.by_company ?? []) {
    m.set(s.company_code, Number(s.amount) || 0)
  }
  return m
}

/** 某企业在某科目的抵销额（按 company_code 命中，缺来源/未命中 ⇒ 0）。 */
export function companyElim(
  projection: PostEliminationProjection | null | undefined,
  prefix: string,
  companyCode: string | undefined,
): number {
  if (!companyCode) return 0
  return companyElimMap(projection, prefix).get(companyCode) ?? 0
}

/** 某科目无法唯一归属到单家的未分配额（Number）。 */
export function unallocatedOf(
  projection: PostEliminationProjection | null | undefined,
  prefix: string,
): number {
  return Number(accountOf(projection, prefix)?.unallocated ?? 0) || 0
}

/** 某科目的提示（多家关联 / 未标企业等）。 */
export function warningsOf(
  projection: PostEliminationProjection | null | undefined,
  prefix: string,
): string[] {
  return accountOf(projection, prefix)?.warnings ?? []
}
