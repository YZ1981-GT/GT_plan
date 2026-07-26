/**
 * H3 产权抵押 ↔ L1 短期借款质押 / L3 长期借款抵押 跨底稿勾稽
 *
 * 纯函数模块：pull L1/L3 质押数据 + 计算差额 + 判定状态。
 */
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface MortgageReconcileResult {
  h3RestrictedTotal: number
  l1PledgeTotal: number | null
  l3PledgeTotal: number | null
  lTotal: number | null
  diff: number | null
  status: 'ok' | 'warning' | 'unavailable'
}

// ─── Internal helpers ────────────────────────────────────────────────────────

async function resolveWpId(projectId: string, wpCode: string): Promise<string | null> {
  try {
    const res = await api.get('/custom-query/wp-id-by-code', {
      params: { project_id: projectId, wp_code: wpCode },
    })
    return res?.data?.wp_id || res?.wp_id || null
  } catch {
    return null
  }
}

async function loadResponseItem(wpId: string, itemId: string): Promise<any> {
  try {
    const res = await api.get(`/workpapers/${wpId}/checklist-responses`)
    const items: any[] = res?.data?.items || res?.items || res?.data || []
    if (Array.isArray(items)) {
      return items.find((it: any) => it.item_id === itemId) || null
    }
    return null
  } catch {
    return null
  }
}

function parseJsonRows(item: any): any[] {
  if (!item) return []
  const raw = item.remark || item.conclusion || ''
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : (parsed?.rows || [])
  } catch {
    return []
  }
}

const PROPERTY_KEYWORDS = ['投资性房地产', '房地产']

function matchesProperty(value: string | undefined): boolean {
  if (!value) return false
  return PROPERTY_KEYWORDS.some(kw => value.includes(kw))
}

// ─── Pull functions ─────────────────────────────────────────────────────────

/**
 * 从 L1 短期借款底稿拉取含「投资性房地产」的质押物金额合计。
 */
export async function pullL1PledgeForH3(projectId: string): Promise<number | null> {
  try {
    const wpId = await resolveWpId(projectId, 'L1')
    if (!wpId) return null

    // L1 质押检查行：可能存储在 L1-L1-8-rows 或 L1-pledge-rows
    const candidates = ['L1-L1-8-rows', 'L1-pledge-rows']
    for (const itemId of candidates) {
      const item = await loadResponseItem(wpId, itemId)
      const rows = parseJsonRows(item)
      if (rows.length > 0) {
        return rows
          .filter(r => matchesProperty(r.pledgeType) || matchesProperty(r.pledgeAsset) || matchesProperty(r.assetType) || matchesProperty(r.remark))
          .reduce((sum, r) => sum + (Number(r.pledgeValue) || Number(r.amount) || 0), 0)
      }
    }
    return null
  } catch {
    return null
  }
}

/**
 * 从 L3 长期借款底稿拉取含「投资性房地产」的抵押物金额合计。
 */
export async function pullL3PledgeForH3(projectId: string): Promise<number | null> {
  try {
    const wpId = await resolveWpId(projectId, 'L3')
    if (!wpId) return null

    const item = await loadResponseItem(wpId, 'L3-8-rows')
    const rows = parseJsonRows(item)
    if (rows.length === 0) return null

    return rows
      .filter(r => matchesProperty(r.pledgeType) || matchesProperty(r.pledgeAsset) || matchesProperty(r.assetType) || matchesProperty(r.remark))
      .reduce((sum, r) => sum + (Number(r.pledgeValue) || Number(r.appraisalValue) || Number(r.amount) || 0), 0)
  } catch {
    return null
  }
}

// ─── Reconcile 纯函数 ──────────────────────────────────────────────────────

const TOLERANCE = 1

/**
 * 构建 H3↔L1/L3 抵押勾稽结果。
 */
export function buildH3MortgageReconcile(
  h3RestrictedTotal: number,
  l1PledgeTotal: number | null,
  l3PledgeTotal: number | null,
): MortgageReconcileResult {
  const l1 = l1PledgeTotal ?? 0
  const l3 = l3PledgeTotal ?? 0
  const anyAvailable = l1PledgeTotal != null || l3PledgeTotal != null

  if (!anyAvailable) {
    return {
      h3RestrictedTotal,
      l1PledgeTotal,
      l3PledgeTotal,
      lTotal: null,
      diff: null,
      status: 'unavailable',
    }
  }

  const lTotal = l1 + l3
  const diff = h3RestrictedTotal - lTotal
  const hasWarning = Math.abs(diff) > TOLERANCE

  return {
    h3RestrictedTotal,
    l1PledgeTotal,
    l3PledgeTotal,
    lTotal,
    diff,
    status: hasWarning ? 'warning' : 'ok',
  }
}
