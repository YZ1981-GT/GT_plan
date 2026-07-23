/**
 * g1G11IncomePull — G1-5 收益测算 ↔ G11 投资收益 跨底稿勾稽
 *
 * G1-5 测算的利息收入 + 股利收入 + 处置损益 应与 G11(6111 投资收益)审定数一致。
 * 差异常见原因：权益法核算(G7-14)、债务重组损益、其他非 G1 循环投资收益。
 *
 * 本模块提供纯函数(可单测) + 异步 pull 函数(复用 wp-id-by-code + checklist-responses 范式)。
 */
import { api } from '@/services/apiProxy'

export interface G1G11ReconcileResult {
  /** G1-5 利息测算合计 */
  g1InterestTotal: number
  /** G1-5 股利测算合计 */
  g1DividendTotal: number
  /** G1-5 处置净损益合计 */
  g1DisposalTotal: number
  /** G1-5 合计 = 利息 + 股利 + 处置 */
  g1Total: number
  /** G11 审定数(投资收益) */
  g11Audited: number
  /** 差异 = G1合计 - G11审定 */
  difference: number
  /** 是否一致(差异绝对值 < 1元) */
  isConsistent: boolean
  /** G11数据来源说明 */
  g11Source: 'audited' | 'unadjusted' | 'unavailable'
}

/**
 * 纯函数：计算 G1-5 ↔ G11 勾稽结果
 */
export function buildG1G11Reconcile(opts: {
  g1InterestTotal: number
  g1DividendTotal: number
  g1DisposalTotal: number
  g11Audited: number
  g11Source: 'audited' | 'unadjusted' | 'unavailable'
}): G1G11ReconcileResult {
  const g1Total = opts.g1InterestTotal + opts.g1DividendTotal + opts.g1DisposalTotal
  const difference = g1Total - opts.g11Audited
  return {
    g1InterestTotal: opts.g1InterestTotal,
    g1DividendTotal: opts.g1DividendTotal,
    g1DisposalTotal: opts.g1DisposalTotal,
    g1Total,
    g11Audited: opts.g11Audited,
    difference,
    isConsistent: Math.abs(difference) < 1,
    g11Source: opts.g11Source,
  }
}

/**
 * 从 G11 底稿拉取投资收益审定数。
 * 路径：wp-id-by-code → checklist-responses → 解析 G11-1-adjudicated-amount
 */
export async function pullG11AuditedForG1(projectId: string): Promise<{
  audited: number
  source: 'audited' | 'unadjusted' | 'unavailable'
}> {
  try {
    // Step 1: 获取 G11 底稿 wp_id
    const wpRes = await api.get('/api/custom-query/wp-id-by-code', {
      params: { project_id: projectId, wp_code: 'G11' },
      _silent: true,
    } as any)
    const wpId = wpRes?.wp_id ?? wpRes?.data?.wp_id
    if (!wpId) return { audited: 0, source: 'unavailable' }

    // Step 2: 从 checklist-responses 取审定数
    const crRes = await api.get(`/api/workpapers/${wpId}/checklist-responses`, {
      _silent: true,
    } as any)
    const items: any[] = Array.isArray(crRes) ? crRes : (crRes?.data ?? [])

    // 优先读 G11-1-adjudicated-amount（审定数EventBus持久化）
    const adjItem = items.find((i: any) => i.item_id === 'G11-1-adjudicated-amount')
    if (adjItem?.conclusion) {
      const val = parseFloat(adjItem.conclusion)
      if (Number.isFinite(val)) return { audited: val, source: 'audited' }
    }

    // 回退：G11-1-tb-closing（试算表期末数）
    const tbItem = items.find((i: any) => i.item_id === 'G11-1-tb-closing')
    if (tbItem?.conclusion) {
      const val = parseFloat(tbItem.conclusion)
      if (Number.isFinite(val)) return { audited: val, source: 'unadjusted' }
    }

    return { audited: 0, source: 'unavailable' }
  } catch {
    return { audited: 0, source: 'unavailable' }
  }
}
