/**
 * useK1DetailAutoSeed — K1-2 明细表空表时自动从四表库（辅助余额）归集.
 *
 * K1 是四表库取数级联的**根**：K1-1 账龄/性质、两个披露表的账龄/性质/前五名均从
 * K1-2 派生。四表入库后若 K1-2 仍是空表，整条链路都是空的（实证：全库
 * `K1-2-detail-rows` 0 条）。本模块在打开底稿时对**空表**触发一次自动归集
 * （非空不触发，不覆盖已有数据；失败静默不打断页面）。
 *
 * 🔴 K1-2 下游读的是**持久化**行（`useK1Detail.loadRows` 读 `allResponses`），
 * 故必须调端点落库后 reload，而不能走 D6/H1 式 transient `detail_prefill`
 * （transient 不落库，下游级联读不到）。
 *
 * spec: .kiro/specs/k1-extraction-chain-and-note-alignment/
 * Requirements 1.7 / Property 2
 */
import http from '@/utils/http'

export const K1_DETAIL_ITEM_ID = 'K1-2-detail-rows'

/** 空表判定：缺失 / 空数组 / 解析失败 → true（可以自动 seed）。 */
export function shouldAutoSeedK1Detail(allResponses: Map<string, any>): boolean {
  const raw = allResponses.get(K1_DETAIL_ITEM_ID)?.remark
  if (!raw) return true
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    return !Array.isArray(parsed) || parsed.length === 0
  } catch {
    return true
  }
}

export interface AutoSeedK1DetailResult {
  imported: number
  skipped: boolean
  message?: string
}

/**
 * 空表时调 `/k1/import-aux-balance` 落库并 reload；非空表跳过（`skipped:true`）。
 * fail-open：端点失败/网络异常时静默返回 `{imported:0, skipped:false}`，不抛出。
 */
export async function autoSeedK1DetailFromAux(opts: {
  wpId: string
  allResponses: Map<string, any>
  reload: () => Promise<void>
}): Promise<AutoSeedK1DetailResult> {
  const { wpId, allResponses, reload } = opts
  if (!wpId || !shouldAutoSeedK1Detail(allResponses)) {
    return { imported: 0, skipped: true }
  }
  try {
    const res = await http.post(`/api/workpapers/${wpId}/k1/import-aux-balance`, null, {
      _silent: true,
    } as any)
    const data = res?.data?.data ?? res?.data ?? {}
    const imported = Number(data?.imported_count ?? 0)
    if (imported > 0) await reload()
    return { imported, skipped: false, message: data?.message }
  } catch (err) {
    console.warn('[useK1DetailAutoSeed] 自动归集失败:', err)
    return { imported: 0, skipped: false }
  }
}
