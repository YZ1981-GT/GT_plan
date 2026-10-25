/**
 * h6H10Pull — 从 H10 资产处置损益底稿拉取审定数
 *
 * 复用 wp-id-by-code + checklist-responses pull 范式（同 h1CipH2Pull/h6LedgerPull）。
 * H6 清理净损益结转至 H10 资产处置损益，两者应勾稽一致。
 *
 * 数据源（**权威单键**）：`H10-1-adjudicated-amount` 的 `conclusion`
 * —— 由 `useH10Adjudication.emitAdjudicated()` / `publishToTb()` 写入
 * （值 = `totalRow.currentAudited`，即 H10-1 审定表的审定合计）。
 *
 * 🔴 **HC-9 / BP-12 修复（原为 4 键猜测回退链 + 1 个假聚合键）**：
 * 原实现按优先级试 `H10-1-audited-total` → `H10-adj-total` → `H10-1-end-audited`
 * → `H10-1-disposal-gain-loss`，再退回聚合 `H10-1-rows`。现算实证：**这 5 个键在
 * 全仓生产代码里的唯一出现处就是本文件自己**（H10 侧从未写过任何一个）⇒ 这条反向
 * 勾稽**恒落到**「H10 暂无审定数」分支，是一条死路，而 4 层 try 让它看起来很稳健。
 * 真源经现算确认是 `H10-1-adjudicated-amount`（`useH10CrossSheet.ts` 读的就是它）。
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

/** H10-1 审定合计的**唯一权威键**（写入方 `useH10Adjudication`，载荷列 `conclusion`）。 */
export const H10_ADJUDICATED_AMOUNT_KEY = 'H10-1-adjudicated-amount'

/**
 * 从 H10 的 checklist_responses 读取审定合计（单一权威键，不做猜键回退）。
 *
 * 🔴 载荷在 **`conclusion`**（`debouncedSave(KEY, { conclusion: String(amount) })`），
 * `remark` 只作历史兜底 —— 顺序写反会读到空。
 */
async function _loadH10AuditedTotal(wpId: string): Promise<number | null> {
  try {
    const res: any = await api.get(`/api/workpapers/${wpId}/checklist-responses`, {
      _silent: true,
    } as any)
    const items: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    const item = items.find((i: any) => i.item_id === H10_ADJUDICATED_AMOUNT_KEY)
    if (!item) return null
    const raw = item.conclusion ?? item.remark
    if (raw == null || String(raw).trim() === '') return null
    const val = Number(raw)
    return Number.isFinite(val) ? val : null
  } catch {
    return null
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
  // 🔴 `null`（键不存在/空串/非数）与 `0`（H10 真的审定为 0）必须分开：
  //    原实现用 `0` 兼表两者，H10 审定确实为 0 时会误报「暂无审定数」。
  if (amount == null) {
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
