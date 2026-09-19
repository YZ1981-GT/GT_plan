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
import {
  parseAuxImportResponse,
  auxImportPrompt,
  AUX_IMPORT_NETWORK_ERROR_PROMPT,
  type AuxImportPrompt,
} from './fourTableAuxImportFeedback'

export const K1_DETAIL_ITEM_ID = 'K1-2-detail-rows'

/** K1 aux 取数端点（AutoSeed 与手动入口共用同一后端 merge 端点）。 */
export const K1_IMPORT_AUX_URL = (wpId: string) => `/api/workpapers/${wpId}/k1/import-aux-balance`

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
    const res = await http.post(K1_IMPORT_AUX_URL(wpId), null, {
      _silent: true,
    } as any)
    const outcome = parseAuxImportResponse(res)
    if (outcome.importedCount > 0) await reload()
    return { imported: outcome.importedCount, skipped: false, message: outcome.message }
  } catch (err) {
    console.warn('[useK1DetailAutoSeed] 自动归集失败:', err)
    return { imported: 0, skipped: false }
  }
}

export interface ManualImportK1DetailResult {
  /** 本次新增行数（merge 后追加）。 */
  imported: number
  /** 是否请求成功（false = 网络/服务器异常，非"0 行"）。 */
  ok: boolean
  /** 给用户看的规范化提示（reason 码可辨别，见 fourTableAuxImportFeedback）。 */
  prompt: AuxImportPrompt
}

/**
 * K1-2 明细表**手动**「从余额表导入」——与 AutoSeed 语义严格区分：
 *   - AutoSeed（`autoSeedK1DetailFromAux`）：仅**空表**触发一次、静默、失败不打断页面；
 *   - 手动入口（本函数）：可在**非空表**上触发，走后端 merge 语义（已有往来单位名不覆盖、
 *     只追加新单位），并把 reason 码提示回传给宿主展示（Requirement 4.4 / 4.5）。
 *
 * 二者共用同一后端 merge 端点（`K1_IMPORT_AUX_URL`），后端保证幂等 merge，
 * 故手动入口无需前端判空、无需客户端拼行——成功后直接 reload 让明细/审定表/披露级联刷新
 * （Requirement 4.6）。
 */
export async function manualImportK1DetailFromAux(opts: {
  wpId: string
  reload: () => Promise<void>
}): Promise<ManualImportK1DetailResult> {
  const { wpId, reload } = opts
  if (!wpId) {
    return { imported: 0, ok: false, prompt: AUX_IMPORT_NETWORK_ERROR_PROMPT }
  }
  try {
    const res = await http.post(K1_IMPORT_AUX_URL(wpId), null)
    const outcome = parseAuxImportResponse(res)
    // 无论新增几行都 reload：后端已 merge 落库，reload 才能让下游（K1-1/披露）读到最新持久化行
    await reload()
    return { imported: outcome.importedCount, ok: true, prompt: auxImportPrompt(outcome) }
  } catch (err) {
    console.warn('[useK1DetailAutoSeed] 手动归集失败:', err)
    return { imported: 0, ok: false, prompt: AUX_IMPORT_NETWORK_ERROR_PROMPT }
  }
}
