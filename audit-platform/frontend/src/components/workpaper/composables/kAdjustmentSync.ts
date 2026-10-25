/**
 * kAdjustmentSync — K 循环「调整分录汇总K{n}-3」六张表的真双向接桥（K8/K9/K10/K11/K12/K13）。
 *
 * spec: k-cycle-sync-foundation-and-first-canary Task 22~24 ·
 *       k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub Task 18
 *
 * ═══ 为什么不直接各 Tab 调 useD4SyncMode ═══
 *
 * 平台的统一接桥实现在 `d4/composables/useD4SyncMode.ts`（健康 / 竞态 / descriptor /
 * busy 门禁四合一，它的 `entryId` 选项本就为非 D4 entry 留了口）。六张 K 表除此之外还共有
 * 两件事：① flush 前必须把**本表**最新行数组直写 store（宿主 `handleChildSave` 是 fire-and-
 * forget，`readStoreProjection` 可能读到上一版 ⇒ OO 打开就是旧值）② OO 回写后从服务端
 * 重读本表 item 并回填宿主 `allResponses`（否则宿主 watch 用旧值把刚回写的数据覆盖回去）。
 * 六份各写一遍 = 六个漂移面，故收在这里。
 *
 * 🔴 后端对端：`phase5_k_adjustment_summary.py` + 六个 `phase5_k{n}_*.py`；sheetKey 与
 *    后端 `KAdjustmentEntryConfig.sheet_key`（`k{n}03-managed`）逐字一致。
 */
import type { Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { readStoreProjection } from '../sync/workpaperSyncApi'
import { useD4SyncMode } from '../d4/composables/useD4SyncMode'

export interface UseKAdjustmentSyncOptions {
  /** manifest entry_id，如 `xlsx/gt-k10-other-income`。 */
  readonly entryId: string
  /** 后端契约 sheet_key，如 `k1003-managed`。 */
  readonly sheetKey: string
  /** 本表 store item_id，如 `K10-3-entries`。 */
  readonly itemId: string
  readonly wpId: Ref<string>
  readonly projectId: Ref<string>
  readonly isReadonly: Ref<boolean>
  /** 现时行数组（必须每行带稳定 `id`）。 */
  readonly snapshotRows: () => unknown[]
  /** 服务端重读到本表 remark 后的回调（由 Tab 自己解析 + 回填宿主 Map）。 */
  readonly onReloaded: (remark: string | null) => void
  /** HTML 侧视图标签，默认 `['结构化视图']`。 */
  readonly views?: readonly string[]
}

/** 本表 item 直写 store（与 K12/K13 FormData 同一端点同一 body 形态）。 */
async function writeItem(wpId: string, projectId: string, itemId: string, rows: unknown[]): Promise<void> {
  await api.put(`/api/workpapers/${wpId}/checklist-responses`, {
    project_id: projectId,
    items: [{ item_id: itemId, conclusion: null, remark: JSON.stringify(rows) }],
  })
}

/** 从服务端重读单个 item 的 remark（不存在返回 null）。 */
async function readItemRemark(wpId: string, itemId: string): Promise<string | null> {
  const res: any = await api.get(`/api/workpapers/${wpId}/checklist-responses`)
  const items: any[] = Array.isArray(res) ? res : (res?.data ?? res?.items ?? [])
  const hit = items.find((r: any) => (r?.item_id ?? r?.itemId) === itemId)
  return hit ? (hit.remark ?? null) : null
}

export function useKAdjustmentSync(options: UseKAdjustmentSyncOptions) {
  return useD4SyncMode({
    entryId: options.entryId,
    sheetKey: options.sheetKey,
    wpId: options.wpId,
    projectId: options.projectId,
    isReadonly: options.isReadonly,
    views: options.views ?? ['结构化视图'],
    flushHtml: async () => {
      await writeItem(options.wpId.value, options.projectId.value, options.itemId, options.snapshotRows())
      const snap = await readStoreProjection({
        projectId: options.projectId.value,
        wpId: options.wpId.value,
        entryId: options.entryId,
      })
      return {
        expectedRevision: snap.expectedRevision,
        projection: snap.projection,
        sheetKey: options.sheetKey,
      }
    },
    reloadHtml: async () => {
      options.onReloaded(await readItemRemark(options.wpId.value, options.itemId))
    },
  })
}

export const K_ONLINE_EDIT_LABEL = '在线编辑'
