/**
 * d1D5FinancingPull — D1-8 贴现/背书 ↔ D5 应收款项融资 跨底稿勾稽
 *
 * 复用 h1CipH2Pull 范式：resolveWpId + loadResponseItem + 纯函数提取 + reconcile。
 * D5-1 审定表 item_id 模式为 "D5-1-adj-{rowKey}-{field}"。
 * fv-total currentAudited = 应收款项融资公允价值合计审定数。
 */
import { api } from '@/services/apiProxy'

export interface D5FinancingPullResult {
  status: 'ok' | 'wp_missing' | 'empty' | 'error'
  message: string
  d5WpId: string | null
  d5AuditedBalance: number
}

export interface D1D5Reconcile {
  d1NotDerecognizedTotal: number
  d5AuditedBalance: number
  diff: number
  matched: boolean
  tolerance: number
}

function parseNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

async function resolveWpId(projectId: string, wpCode: string): Promise<string | null> {
  try {
    const res = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
      params: { project_id: projectId, wp_code: wpCode },
      _silent: true,
    } as any)
    return (res as any)?.wp_id ?? (res as any)?.data?.wp_id ?? null
  } catch { return null }
}

async function loadAllResponses(wpId: string): Promise<Map<string, string>> {
  try {
    const res = await api.get(`/api/workpapers/${wpId}/checklist-responses`, { _silent: true } as any)
    const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    const map = new Map<string, string>()
    for (const r of list) {
      if (r?.item_id && r?.remark != null) map.set(r.item_id, String(r.remark))
    }
    return map
  } catch { return new Map() }
}

/**
 * 纯函数：从 D5 checklist responses 提取 fv-total 审定数。
 * D5-1 fv-total currentAudited = 小计(notes+accounts) - OCI变动。
 * 直接取各子行 remark 数值重算，不依赖预存合计（更准确）。
 */
export function extractD5AuditedBalance(responses: Map<string, string>): number {
  const get = (key: string) => parseNum(responses.get(key))
  // 应收票据: notes-receivable
  const notesUnadj = get('D5-1-adj-notes-receivable-currentUnadjusted')
  const notesAje = get('D5-1-adj-notes-receivable-currentAje')
  const notesRje = get('D5-1-adj-notes-receivable-currentRje')
  const notesAudited = notesUnadj + notesAje + notesRje
  // 应收账款: accounts-receivable
  const accUnadj = get('D5-1-adj-accounts-receivable-currentUnadjusted')
  const accAje = get('D5-1-adj-accounts-receivable-currentAje')
  const accRje = get('D5-1-adj-accounts-receivable-currentRje')
  const accAudited = accUnadj + accAje + accRje
  // 小计
  const subtotal = notesAudited + accAudited
  // OCI变动
  const ociUnadj = get('D5-1-adj-oci-change-currentUnadjusted')
  const ociAje = get('D5-1-adj-oci-change-currentAje')
  const ociRje = get('D5-1-adj-oci-change-currentRje')
  const ociAudited = ociUnadj + ociAje + ociRje
  // FV合计 = 小计 - OCI变动
  return subtotal - ociAudited
}

export async function pullD5FinancingForD1(projectId: string): Promise<D5FinancingPullResult> {
  const base: D5FinancingPullResult = { status: 'error', message: '', d5WpId: null, d5AuditedBalance: 0 }
  if (!projectId) return { ...base, message: '缺少 projectId' }
  const d5WpId = await resolveWpId(projectId, 'D5')
  if (!d5WpId) return { ...base, status: 'wp_missing', message: '项目中未找到 D5 应收款项融资底稿' }
  const responses = await loadAllResponses(d5WpId)
  if (responses.size === 0) return { ...base, status: 'empty', message: 'D5 暂无审定数据，请先编制 D5-1', d5WpId }
  const balance = extractD5AuditedBalance(responses)
  return { status: 'ok', message: `D5-1 应收款项融资审定 FV 合计 ${balance.toLocaleString('zh-CN')}`, d5WpId, d5AuditedBalance: balance }
}

export function buildD1D5Reconcile(d1NotDerecognizedTotal: number, d5AuditedBalance: number, tolerance = 1): D1D5Reconcile {
  const diff = parseNum(d1NotDerecognizedTotal) - parseNum(d5AuditedBalance)
  return { d1NotDerecognizedTotal: parseNum(d1NotDerecognizedTotal), d5AuditedBalance: parseNum(d5AuditedBalance), diff, matched: Math.abs(diff) < tolerance, tolerance }
}
