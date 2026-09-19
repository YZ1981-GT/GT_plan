/**
 * h6H10Pull — 从 H10 资产处置损益底稿拉取审定数
 *
 * 复用 wp-id-by-code + checklist-responses pull 范式（同 h1CipH2Pull/h6LedgerPull）。
 * H6 清理净损益结转至 H10 资产处置损益，两者应勾稽一致。
 *
 * 数据源：H10 审定表的 endAudited 合计（item_id: H10-1-audited-total 或 H10-adj-total）
 */
import { ref, type Ref } from 'vue'
import { api } from '@/services/apiProxy'

export interface H10PullResult {
  status: 'ok' | 'wp_missing' | 'empty' | 'error'
  message: string
  /** H10 资产处置损益审定合计 */
  h10AuditedAmount: number
}

/**
 * 解析 H10 底稿的 wp_id
 */
async function _resolveH10WpId(projectId: string): Promise<string | null> {
  try {
    const res: any = await api.get('/api/custom-query/wp-id-by-code', {
      params: { project_id: projectId, wp_code: 'H10' },
      _silent: true,
    } as any)
    return res?.wp_id ?? res?.data?.wp_id ?? null
  } catch {
    return null
  }
}

/**
 * 从 H10 的 checklist_responses 读取审定合计
 */
async function _loadH10AuditedTotal(wpId: string): Promise<number> {
  try {
    const res: any = await api.get(`/api/workpapers/${wpId}/checklist-responses`, {
      _silent: true,
    } as any)
    const items: any[] = Array.isArray(res) ? res : (res?.data ?? [])

    // 优先级：H10-1-audited-total > H10-adj-total > H10-1-end-audited
    const keyPriority = [
      'H10-1-audited-total',
      'H10-adj-total',
      'H10-1-end-audited',
      'H10-1-disposal-gain-loss',
    ]
    for (const key of keyPriority) {
      const item = items.find((i: any) => i.item_id === key)
      if (item) {
        const raw = item.remark ?? item.conclusion
        const val = Number(raw)
        if (Number.isFinite(val) && val !== 0) return val
      }
    }

    // 尝试从 H10-1-rows JSON 聚合
    const rowsItem = items.find((i: any) => i.item_id === 'H10-1-rows')
    if (rowsItem) {
      const raw = rowsItem.remark ?? rowsItem.conclusion
      try {
        const rows = JSON.parse(raw)
        if (Array.isArray(rows)) {
          let total = 0
          for (const r of rows) {
            if (r.isTotal || r.is_total) continue
            total += Number(r.endAudited ?? r.audited ?? r.auditedAmount ?? 0)
          }
          if (total !== 0) return total
        }
      } catch { /* not JSON */ }
    }

    return 0
  } catch {
    return 0
  }
}

/**
 * 从 H10 拉取资产处置损益审定数（供 H6-1 勾稽）
 */
export async function pullH10DisposalAmount(projectId: string): Promise<H10PullResult> {
  if (!projectId) {
    return { status: 'error', message: '缺少 projectId', h10AuditedAmount: 0 }
  }

  const wpId = await _resolveH10WpId(projectId)
  if (!wpId) {
    return { status: 'wp_missing', message: '项目中未找到 H10 资产处置损益底稿', h10AuditedAmount: 0 }
  }

  const amount = await _loadH10AuditedTotal(wpId)
  if (amount === 0) {
    return { status: 'empty', message: 'H10 暂无审定数（请先编制 H10-1 审定表）', h10AuditedAmount: 0 }
  }

  return {
    status: 'ok',
    message: `H10 资产处置损益审定：${amount.toLocaleString('zh-CN')}`,
    h10AuditedAmount: amount,
  }
}

/**
 * Composable: 在 H6 主入口 onMounted 异步拉取并 provide 给 H6-1
 */
export function useH6H10Pull(projectId: Ref<string>) {
  const h10Amount = ref(0)
  const h10Status = ref<'idle' | 'loading' | 'ok' | 'empty' | 'error'>('idle')

  async function loadH10(): Promise<void> {
    if (!projectId.value) return
    h10Status.value = 'loading'
    const result = await pullH10DisposalAmount(projectId.value)
    h10Amount.value = result.h10AuditedAmount
    h10Status.value = result.status === 'ok' ? 'ok' : result.status === 'empty' ? 'empty' : 'error'
  }

  return { h10Amount, h10Status, loadH10 }
}
