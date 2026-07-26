/**
 * H3 互转审核 ↔ H1 固定资产 / H2 在建工程 跨底稿勾稽
 *
 * 纯函数模块：pull 对方底稿数据 + 计算差额 + 判定状态。
 * 复用 wp-id-by-code + checklist-responses 范式（已在 h1CipH2Pull/h2H1TransferPull 验证）。
 */
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface TransferSummary {
  fromH1: number
  toH1: number
  fromH2: number
}

export interface H1TransferData {
  /** H1-8 减少检查中「转出至投资性房地产」合计 */
  disposalToInvest: number | null
  /** H1-7 增加检查中「从投资性房地产转入」合计 */
  additionFromInvest: number | null
}

export interface H2TransferData {
  /** H2-5 转固中「转出至投资性房地产」合计 */
  cipToInvest: number | null
}

export interface TransferReconcileResult {
  h3FromH1: number
  h1DisposalToInvest: number | null
  h3ToH1: number
  h1AdditionFromInvest: number | null
  h3FromH2: number
  h2CipToInvest: number | null
  diffFromH1: number | null
  diffToH1: number | null
  diffFromH2: number | null
  status: 'ok' | 'warning' | 'unavailable'
}

// ─── Pull functions ─────────────────────────────────────────────────────────

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
      const found = items.find((it: any) => it.item_id === itemId)
      return found || null
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

function sumByFilter(rows: any[], filter: (r: any) => boolean, field: string): number {
  return rows
    .filter(filter)
    .reduce((sum, r) => sum + (Number(r[field]) || 0), 0)
}

const INVEST_KEYWORDS = ['投资性房地产', '投资']

function matchesInvest(value: string | undefined): boolean {
  if (!value) return false
  return INVEST_KEYWORDS.some(kw => value.includes(kw))
}

/**
 * 从 H1 底稿拉取与投资性房地产相关的增减数据。
 */
export async function pullH1TransferForH3(projectId: string): Promise<H1TransferData> {
  try {
    const wpId = await resolveWpId(projectId, 'H1')
    if (!wpId) return { disposalToInvest: null, additionFromInvest: null }

    // H1-8 减少检查行（转出至投资性房地产）
    const disposalItem = await loadResponseItem(wpId, 'H1-8-disposal-rows')
    const disposalRows = parseJsonRows(disposalItem)
    const disposalTotal = sumByFilter(
      disposalRows,
      r => matchesInvest(r.changeType) || matchesInvest(r.disposalType) || matchesInvest(r.remark),
      'netValue',
    )

    // H1-7 增加检查行（从投资性房地产转入）
    const additionItem = await loadResponseItem(wpId, 'H1-7-addition-rows')
    const additionRows = parseJsonRows(additionItem)
    const additionTotal = sumByFilter(
      additionRows,
      r => matchesInvest(r.changeType) || matchesInvest(r.sourceType) || matchesInvest(r.remark),
      'originalCost',
    )

    return {
      disposalToInvest: disposalTotal,
      additionFromInvest: additionTotal,
    }
  } catch {
    return { disposalToInvest: null, additionFromInvest: null }
  }
}

/**
 * 从 H2 底稿拉取与投资性房地产相关的转固数据。
 */
export async function pullH2TransferForH3(projectId: string): Promise<H2TransferData> {
  try {
    const wpId = await resolveWpId(projectId, 'H2')
    if (!wpId) return { cipToInvest: null }

    const cipItem = await loadResponseItem(wpId, 'H2-5-cip-transfer-rows')
    const cipRows = parseJsonRows(cipItem)
    const cipTotal = sumByFilter(
      cipRows,
      r => matchesInvest(r.assetType) || matchesInvest(r.transferTarget) || matchesInvest(r.remark),
      'transferAmount',
    )

    return { cipToInvest: cipTotal }
  } catch {
    return { cipToInvest: null }
  }
}

// ─── Reconcile 纯函数 ──────────────────────────────────────────────────────

const TOLERANCE = 1 // 1元容差

/**
 * 构建 H3↔H1/H2 三方向勾稽结果。
 */
export function buildH3TransferReconcile(
  h3: TransferSummary,
  h1: H1TransferData,
  h2: H2TransferData,
): TransferReconcileResult {
  const diffFromH1 = h1.disposalToInvest != null ? h3.fromH1 - h1.disposalToInvest : null
  const diffToH1 = h1.additionFromInvest != null ? h3.toH1 - h1.additionFromInvest : null
  const diffFromH2 = h2.cipToInvest != null ? h3.fromH2 - h2.cipToInvest : null

  const anyUnavailable = h1.disposalToInvest == null && h1.additionFromInvest == null && h2.cipToInvest == null
  if (anyUnavailable) {
    return {
      h3FromH1: h3.fromH1,
      h1DisposalToInvest: h1.disposalToInvest,
      h3ToH1: h3.toH1,
      h1AdditionFromInvest: h1.additionFromInvest,
      h3FromH2: h3.fromH2,
      h2CipToInvest: h2.cipToInvest,
      diffFromH1,
      diffToH1,
      diffFromH2,
      status: 'unavailable',
    }
  }

  const hasWarning = [diffFromH1, diffToH1, diffFromH2].some(d => d != null && Math.abs(d) > TOLERANCE)

  return {
    h3FromH1: h3.fromH1,
    h1DisposalToInvest: h1.disposalToInvest,
    h3ToH1: h3.toH1,
    h1AdditionFromInvest: h1.additionFromInvest,
    h3FromH2: h3.fromH2,
    h2CipToInvest: h2.cipToInvest,
    diffFromH1,
    diffToH1,
    diffFromH2,
    status: hasWarning ? 'warning' : 'ok',
  }
}
