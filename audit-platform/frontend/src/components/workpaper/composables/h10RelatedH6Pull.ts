/**
 * H10 ↔ H6 固定资产清理 跨底稿拉数
 *
 * H6 明细在 H6 WP 的 checklist「H6-2-rows」，不在 H10 allResponses —— 须 HTTP 拉取后勾稽。
 */
import { api } from '@/services/apiProxy'
import { parseNum } from './useH10FormulaEngine'

export interface H6ClearingPullResult {
  status: 'ok' | 'wp_missing' | 'empty' | 'error'
  message: string
  h6WpId: string | null
  netGainLoss: number | null
  rowCount: number
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

function rowGain(r: Record<string, unknown>): number {
  return parseNum(
    r.netGainLoss ?? r.gainLoss ?? r.disposalGainLoss ?? r.toDisposalGain ?? r.amount,
  )
}

/** 拉取 H6-2 清理明细净损益合计（结转至资产处置收益口径） */
export async function pullH6ClearingNetForH10(projectId: string): Promise<H6ClearingPullResult> {
  if (!projectId) {
    return { status: 'error', message: '缺少 projectId', h6WpId: null, netGainLoss: null, rowCount: 0 }
  }
  const h6WpId = await resolveWpId(projectId, 'H6')
  if (!h6WpId) {
    return { status: 'wp_missing', message: '未找到 H6 固定资产清理底稿', h6WpId: null, netGainLoss: null, rowCount: 0 }
  }
  try {
    const res = await api.get(`/api/workpapers/${h6WpId}/checklist-responses`, { _silent: true } as any)
    const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    const keys = ['H6-2-rows', 'H6-detail-rows', 'H6-clearing-rows']
    let rows: any[] = []
    for (const key of keys) {
      const item = list.find((r) => r?.item_id === key)
      const parsed = parseRemark(item?.remark)
      if (Array.isArray(parsed) && parsed.length) {
        rows = parsed
        break
      }
    }
    if (!rows.length) {
      return { status: 'empty', message: 'H6 清理明细为空', h6WpId, netGainLoss: null, rowCount: 0 }
    }
    const netGainLoss = rows.reduce((s, r) => s + rowGain(r), 0)
    return {
      status: 'ok',
      message: `已拉取 H6 清理 ${rows.length} 行，净损益 ${netGainLoss.toFixed(2)}`,
      h6WpId,
      netGainLoss,
      rowCount: rows.length,
    }
  } catch (e: any) {
    return {
      status: 'error',
      message: e?.message || '拉取 H6 失败',
      h6WpId,
      netGainLoss: null,
      rowCount: 0,
    }
  }
}
