/**
 * H1-18 关联交易检查 ↔ H10 资产处置损益 跨底稿拉数
 *
 * H10 明细存于 H10 WP 的 checklist_responses「H10-detail-rows」，
 * 不在 H1 allResponses 内——须跨 WP 拉取后再做勾稽。
 */
import { api } from '@/services/apiProxy'

export interface H10DetailPullRow {
  rowId?: string
  assetNo?: string
  assetName?: string
  name?: string
  disposalGainLoss?: number
  sourceWp?: string
  sourceIndex?: string
  sourceRowRef?: string
  [key: string]: unknown
}

export interface H10DetailPullResult {
  status: 'ok' | 'wp_missing' | 'empty' | 'error'
  message: string
  h10WpId: string | null
  rows: H10DetailPullRow[]
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

function parseRemark(raw: unknown): unknown {
  if (raw == null) return null
  if (typeof raw !== 'string') return raw
  const s = raw.trim()
  if (!s) return null
  try {
    return JSON.parse(s)
  } catch {
    return raw
  }
}

/** 拉取 H10 处置明细行（优先 H1 来源） */
export async function pullH10DetailRowsForH1(projectId: string): Promise<H10DetailPullResult> {
  if (!projectId) {
    return { status: 'error', message: '缺少 projectId', h10WpId: null, rows: [] }
  }
  const h10WpId = await resolveWpId(projectId, 'H10')
  if (!h10WpId) {
    return { status: 'wp_missing', message: '未找到 H10 资产处置损益底稿', h10WpId: null, rows: [] }
  }
  try {
    const res = await api.get(`/api/workpapers/${h10WpId}/checklist-responses`, { _silent: true } as any)
    const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    const item = list.find((r) => r?.item_id === 'H10-detail-rows')
    const parsed = parseRemark(item?.remark)
    const rows = Array.isArray(parsed) ? (parsed as H10DetailPullRow[]) : []
    const h1Related = rows.filter(
      (r) => !r.sourceWp || r.sourceWp === 'H1' || String(r.sourceIndex || '').includes('H1'),
    )
    if (!h1Related.length && !rows.length) {
      return { status: 'empty', message: 'H10 明细为空', h10WpId, rows: [] }
    }
    return {
      status: 'ok',
      message: `已拉取 H10 明细 ${h1Related.length || rows.length} 行`,
      h10WpId,
      rows: h1Related.length ? h1Related : rows,
    }
  } catch (e: any) {
    return {
      status: 'error',
      message: e?.message || '拉取 H10 失败',
      h10WpId,
      rows: [],
    }
  }
}
