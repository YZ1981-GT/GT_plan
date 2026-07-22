/**
 * 费用底稿（K8/K9/I6/D5）从 I1-9-alloc-totals 拉取「无形资产摊销」金额。
 * 与 pushI1AmortToExpenseWps 互补：对方打开明细时可主动回填。
 */
import { api } from '@/services/apiProxy'

export type I1AmortExpenseTarget = 'K8' | 'K9' | 'I6' | 'D5'

const FIELD_BY_TARGET: Record<I1AmortExpenseTarget, string> = {
  K8: 'sellingExpenseAmort',
  K9: 'managementExpenseAmort',
  I6: 'rdExpenseAmort',
  D5: 'productionManufacturingAmort',
}

const FALLBACK_FIELD: Record<I1AmortExpenseTarget, string[]> = {
  K8: ['sellingExpense', '销售费用摊销'],
  K9: ['managementExpense', '管理费用摊销'],
  I6: ['rdExpense', '研发费用摊销'],
  D5: ['productionCost', '制造费用', 'productionManufacturingAmort'],
}

const KEYWORDS: Record<I1AmortExpenseTarget, string[]> = {
  K8: ['无形资产摊销', '折旧及摊销'],
  K9: ['无形资产摊销'],
  I6: ['无形资产摊销'],
  D5: ['无形资产摊销', '摊销'],
}

const DETAIL_ITEM: Record<I1AmortExpenseTarget, string> = {
  K8: 'K8-2-detail-rows',
  K9: 'K9-2-detail-rows',
  I6: 'I6-2-detail-rows',
  D5: 'D5-2-detail-rows',
}

function parseNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function rowName(row: any): string {
  return String(row?.accountName ?? row?.projectName ?? row?.category ?? row?.name ?? '').trim()
}

function extractRows(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  let data: any = raw
  if (typeof raw === 'string' && raw.trim()) {
    try { data = JSON.parse(raw) } catch { return [] }
  }
  if (Array.isArray(data)) return data
  if (data && typeof data === 'object' && Array.isArray(data.rows)) return data.rows
  return []
}

async function resolveWpId(projectId: string, wpCode: string): Promise<string | null> {
  try {
    const idRes = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
      params: { project_id: projectId, wp_code: wpCode },
      _silent: true,
    } as any)
    return (idRes as any)?.wp_id ?? (idRes as any)?.data?.wp_id ?? null
  } catch {
    return null
  }
}

function readAmountFromTotals(totals: any, target: I1AmortExpenseTarget): number {
  if (!totals || typeof totals !== 'object') return 0
  const primary = FIELD_BY_TARGET[target]
  if (totals[primary] != null) return parseNum(totals[primary])
  // nested totals from publishAllocated
  const nested = totals.totals
  if (nested && typeof nested === 'object') {
    if (target === 'K8') return parseNum(nested.sellingExpense)
    if (target === 'K9') return parseNum(nested.managementExpense)
    if (target === 'I6') return parseNum(nested.rdExpense)
    if (target === 'D5') return parseNum(nested.productionCost) + parseNum(nested.manufacturingCost)
  }
  for (const k of FALLBACK_FIELD[target]) {
    if (totals[k] != null) return parseNum(totals[k])
  }
  if (target === 'D5') {
    return parseNum(totals.productionCost) + parseNum(totals.manufacturingCost)
  }
  return 0
}

/**
 * 从 I1 底稿读取 I1-9-alloc-totals，回写到本费用底稿明细「无形资产摊销」行未审数。
 */
export async function pullI1AmortIntoExpenseDetail(
  projectId: string,
  target: I1AmortExpenseTarget,
  opts?: {
    /** 本底稿 wpId；缺省则按 target 解析 */
    localWpId?: string
    /** 本地已有明细行；若提供则就地更新并返回，由调用方 persist */
    localRows?: any[]
  },
): Promise<{
  ok: boolean
  amount: number
  message: string
  rows?: any[]
}> {
  const i1WpId = await resolveWpId(projectId, 'I1')
  if (!i1WpId) {
    return { ok: false, amount: 0, message: '未找到 I1 无形资产底稿' }
  }

  let totals: any = null
  try {
    const res = await api.get(`/api/workpapers/${i1WpId}/checklist-responses`, { _silent: true } as any)
    const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    const item = list.find((x) => x?.item_id === 'I1-9-alloc-totals')
    const raw = item?.remark ?? item?.conclusion
    if (raw) totals = typeof raw === 'string' ? JSON.parse(raw) : raw
  } catch {
    return { ok: false, amount: 0, message: '读取 I1-9-alloc-totals 失败' }
  }

  const amount = readAmountFromTotals(totals, target)
  if (Math.abs(amount) < 0.005) {
    return { ok: false, amount: 0, message: 'I1-9 对应费用列摊销合计为 0，请先编制并发布摊销分配' }
  }

  const applyToRows = (rows: any[]): { rows: any[]; hit: boolean } => {
    const keywords = KEYWORDS[target]
    let hitIdx = -1
    for (const kw of keywords) {
      hitIdx = rows.findIndex((r) => rowName(r) === kw)
      if (hitIdx >= 0) break
    }
    if (hitIdx < 0) {
      hitIdx = rows.findIndex((r) => keywords.some((k) => rowName(r).includes(k)))
    }
    if (hitIdx < 0) return { rows, hit: false }

    const row = { ...rows[hitIdx] }
    if (Array.isArray(row.months)) {
      const months = new Array(12).fill(0)
      months[11] = amount
      row.months = months
      row.unadjTotal = amount
      row.audited = amount + parseNum(row.aje) + parseNum(row.rje)
    } else if ('unadjTotal' in row || row.unadjTotal != null) {
      row.unadjTotal = amount
      row.audited = amount + parseNum(row.aje) + parseNum(row.rje)
    } else if ('unadjusted' in row || row.unadjusted != null) {
      row.unadjusted = amount
      row.audited = amount + parseNum(row.aje) + parseNum(row.rje)
    } else {
      row.amount = amount
      row.audited = amount
    }
    row._i1AmortPulledAt = new Date().toISOString()
    const next = [...rows]
    next[hitIdx] = row
    return { rows: next, hit: true }
  }

  if (opts?.localRows) {
    const { rows, hit } = applyToRows(opts.localRows)
    if (!hit) {
      return {
        ok: false,
        amount,
        message: `本表未找到「无形资产摊销」行（建议金额 ${amount.toFixed(2)}）`,
        rows,
      }
    }
    return {
      ok: true,
      amount,
      message: `已从 I1-9 回填无形资产摊销 ${amount.toFixed(2)}`,
      rows,
    }
  }

  const localWpId = opts?.localWpId || (await resolveWpId(projectId, target))
  if (!localWpId) {
    return { ok: false, amount, message: `未找到 ${target} 底稿` }
  }

  const itemId = DETAIL_ITEM[target]
  try {
    const res = await api.get(`/api/workpapers/${localWpId}/checklist-responses`, { _silent: true } as any)
    const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    const item = list.find((x) => x?.item_id === itemId)
    if (!item) {
      return { ok: false, amount, message: `${target} 无明细数据 ${itemId}` }
    }
    const rows = extractRows(item.remark ?? item.conclusion)
    const { rows: next, hit } = applyToRows(rows)
    if (!hit) {
      return { ok: false, amount, message: `${target} 未找到无形资产摊销行` }
    }
    await api.put(`/api/workpapers/${localWpId}/checklist-responses`, {
      items: [{ item_id: itemId, conclusion: null, remark: JSON.stringify(next) }],
    }, { _silent: true } as any)
    return { ok: true, amount, message: `已回写 ${target} 无形资产摊销 = ${amount.toFixed(2)}`, rows: next }
  } catch (e: any) {
    return { ok: false, amount, message: e?.message || '回写失败' }
  }
}

export default pullI1AmortIntoExpenseDetail
