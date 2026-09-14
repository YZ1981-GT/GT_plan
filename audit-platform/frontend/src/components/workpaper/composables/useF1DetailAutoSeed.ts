/**
 * useF1DetailAutoSeed — F1-2 明细表「四表库自动取数」（打开即取，手工优先）
 *
 * 背景：F1 的取数级联根是 F1-2 明细（→ F1-1 按性质/账龄 → 附注）。此前 F1-2 仅靠
 * 手动按钮「从辅助余额表导入」填充，导致「四表入库后刷新底稿无数据」。本 helper 在
 * 底稿加载后、当 F1-2 完全为空时，自动复用**既有且已测**的 `/f1/import-aux-balance`
 * 端点（tb_aux_balance 科目 1123 按往来单位归集）落库 `F1-det-rows`，再 reload 使
 * useF1CrossSheet / 附注（均读 allResponses 的 `F1-det-rows`）级联刷新。
 *
 * 手工优先：仅当 `F1-det-rows` 为空（无 / `[]` / `null` / `{}` / 空数组）时才 seed，
 * 绝不覆盖审计师已录入或既有一键取数结果。fail-open：四表无数据 / 端点异常一律
 * 静默跳过，不阻断底稿渲染。
 *
 * 与 D6/H1/F2 render `*_prefill` 同口径（手工优先 + 来源可溯），差异在于 F1 的下游
 * （审定表/附注）读取的是**持久化的** `F1-det-rows`，故 seed 必须落库（走既有端点），
 * 而非 transient —— 否则级联读不到。
 */
import type { Ref } from 'vue'
import { api } from '@/services/apiProxy'
import type { ChecklistResponse } from './useF1FormData'

const F1_DETAIL_ITEM_ID = 'F1-det-rows'

/**
 * 纯函数：判定 F1-2 明细是否为空（可 seed）。
 * 无法解析或非数组一律保守视为「非空」（不 seed），避免覆盖不明数据。
 */
export function shouldAutoSeedF1Detail(remark: string | null | undefined): boolean {
  const s = String(remark ?? '').trim()
  if (!s || s === '[]' || s === 'null' || s === '{}') return true
  try {
    const parsed = JSON.parse(s)
    return Array.isArray(parsed) && parsed.length === 0
  } catch {
    return false
  }
}

export interface UseF1DetailAutoSeedOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  isReadonly: Ref<boolean>
  allResponses: Ref<Map<string, ChecklistResponse>>
  /** 重新拉取 checklist 全量，使跨 sheet / 附注级联刷新 */
  reloadAll: () => Promise<void>
}

/**
 * 打开底稿后自动 seed F1-2（仅当为空）。返回是否实际执行了导入。
 */
export async function autoSeedF1DetailFromAux(
  opts: UseF1DetailAutoSeedOptions,
): Promise<boolean> {
  const { wpId, projectId, isReadonly, allResponses, reloadAll } = opts
  if (isReadonly.value) return false
  if (!wpId.value) return false

  const remark = allResponses.value.get(F1_DETAIL_ITEM_ID)?.remark
  if (!shouldAutoSeedF1Detail(remark)) return false

  try {
    const res: any = await api.post(
      `/api/workpapers/${wpId.value}/f1/import-aux-balance`,
      { project_id: projectId.value },
    )
    const body = res?.data ?? res
    const imported: any[] = Array.isArray(body) ? body : (body?.rows ?? [])
    if (imported.length === 0) return false
    // 端点已 upsert 落库 F1-det-rows → 重新拉取使 useF1CrossSheet / 附注级联
    await reloadAll()
    return true
  } catch {
    // fail-open：四表无数据 / 端点异常不阻断渲染
    return false
  }
}
