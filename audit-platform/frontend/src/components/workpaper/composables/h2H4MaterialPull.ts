/**
 * H2 ↔ H4 工程物资跨底稿勾稽
 *
 * 复用 wp-id-by-code + checklist-responses pull 范式（同 h1CipH2Pull / h2L1LoanPull）。
 * H4 工程物资（科目 1605）审定合计 vs H2 审定表工程物资段审定合计。
 */
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H4PullResult {
  status: 'ok' | 'wp_missing' | 'empty' | 'error'
  message: string
  h4WpId: string | null
  h4AuditedTotal: number | null
}

export interface H2H4ReconcileResult {
  h2Total: number
  h4Total: number | null
  difference: number | null
  isConsistent: boolean
  status: 'consistent' | 'inconsistent' | 'h4_missing' | 'error'
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function resolveWpId(projectId: string, wpCode: string): Promise<string | null> {
  try {
    const res = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
      params: { project_id: projectId, wp_code: wpCode },
      _silent: true,
    } as any)
    return (res as any)?.wp_id ?? (res as any)?.data?.wp_id ?? null
  } catch {
    return null
  }
}

// ─── 拉取 ─────────────────────────────────────────────────────────────────────

/**
 * 从 H4 工程物资底稿拉取审定合计。
 * 读 checklist_responses item_id = 'H4-1-audited-total'。
 */
export async function pullH4AuditedForH2(projectId: string): Promise<H4PullResult> {
  const base: H4PullResult = { status: 'error', message: '', h4WpId: null, h4AuditedTotal: null }
  if (!projectId) return { ...base, message: '缺少 projectId' }

  const h4WpId = await resolveWpId(projectId, 'H4')
  if (!h4WpId) {
    return { ...base, status: 'wp_missing', message: '项目中未找到 H4 工程物资底稿', h4WpId: null }
  }

  try {
    const res = await api.get(`/api/workpapers/${h4WpId}/checklist-responses`, { _silent: true } as any)
    const items: any[] = Array.isArray(res) ? res : ((res as any)?.data ?? [])
    const totalItem = items.find((r: any) => r?.item_id === 'H4-1-audited-total')
    if (!totalItem) {
      return { ...base, status: 'empty', message: 'H4 审定表暂无审定合计数据', h4WpId }
    }
    const val = Number(totalItem.remark ?? totalItem.conclusion)
    if (!Number.isFinite(val)) {
      return { ...base, status: 'empty', message: 'H4 审定合计为空', h4WpId }
    }
    return {
      status: 'ok',
      message: `H4 工程物资审定合计 ${val.toLocaleString('zh-CN')}`,
      h4WpId,
      h4AuditedTotal: val,
    }
  } catch (e: any) {
    return { ...base, status: 'error', message: e?.message || '拉取 H4 失败', h4WpId }
  }
}

// ─── 勾稽纯函数 ──────────────────────────────────────────────────────────────

/**
 * 构建 H2 工程物资段 vs H4 审定合计勾稽结果。
 * 差异 ≤ 1 元视为一致（四舍五入容差）。
 */
export function buildH2H4MaterialReconcile(h2Total: number, h4Total: number | null): H2H4ReconcileResult {
  if (h4Total == null) {
    return { h2Total, h4Total: null, difference: null, isConsistent: false, status: 'h4_missing' }
  }
  const diff = h2Total - h4Total
  const isConsistent = Math.abs(diff) <= 1
  return {
    h2Total,
    h4Total,
    difference: diff,
    isConsistent,
    status: isConsistent ? 'consistent' : 'inconsistent',
  }
}
