/**
 * L3 长期借款披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：外壳 `GtL3LongTermLoans` 注入的表单 = `useL3FormData.loadData()` 读的本底稿 L3- 回复
 * （与框架同口径），Tab 用 `useL3Disclosure(allResponses, debouncedSave, variant)` 从 L3-2 明细按借款类型聚合 →
 * `buildL3SyncOptions` → `buildL3SyncPayload` → 同一个请求体函数。保存回调为空（离屏不改底稿）。
 *
 * - 上市只推 五、45：`buildL3ListedSyncBody` 经 `sync-from-workpaper`（框架默认发送）；
 * - 国企推 八、49 + 八、45：Tab 一次 `sync-batch-from-workpaper` 发两节；离屏要逐章节过保护判定、逐章节回报，故每节
 *   各发一次同一批量端点（`buildL3SoeBatchBody` 只放这一节，item 与 Tab 的逐字节相同），按响应 `results[0]` 回报。
 */
import { ref } from 'vue'
import http from '@/utils/http'
import {
  defineHeadlessProvider,
  postHeadlessSyncPayload,
  type HeadlessSectionResult,
} from '@/components/workpaper/headless/headlessFramework'
import { useL3Disclosure } from './useL3Disclosure'
import { buildL3SyncPayload, type L3SyncItem } from './l3NoteSectionMap'
import { buildL3ListedSyncBody, buildL3SoeBatchBody, buildL3SyncOptions } from './l3DisclosureSync'

/** 国企一节：同一批量端点、只放这一节（静默），按 `results[0]` 回报 */
async function postSoeSection(projectId: string, wpId: string, item: L3SyncItem): Promise<HeadlessSectionResult> {
  const res: any = await http.post(
    `/api/projects/${projectId}/disclosure-notes/sync-batch-from-workpaper`,
    buildL3SoeBatchBody(wpId, [item]),
    { _silent: true } as any,
  )
  const data = res?.data ?? res
  const result = (Array.isArray(data?.results) ? data.results[0] : null) ?? {}
  const section = String(result.section_id || item.section_id)
  if (result.blocked_by_manual_override) return { section, rows: 0, skipped: `附注 ${section} 标记了整节人工覆盖，未写入` }
  if (result.skipped) return { section, rows: 0, skipped: `章节未写入：${result.reason || '不适用'}` }
  return {
    section,
    rows: Number(result.rows_synced ?? 0),
    kept: Array.isArray(result.push_kept) ? result.push_kept.length : 0,
  }
}

export const l3HeadlessProvider = defineHeadlessProvider({
  // 与 useL3FormData.loadResponses 同前缀（L3-{sheet}-{field}）
  prefix: 'L3-',
  setup: ({ ctx, responses }) => useL3Disclosure(ref(responses), () => {}, ctx.variant),
  build: (disclosure, { ctx }) => buildL3SyncPayload(buildL3SyncOptions(ctx.variant, disclosure)),
  post: (_disclosure, payload, { ctx }) => (ctx.variant === 'listed'
    ? postHeadlessSyncPayload(ctx.projectId, buildL3ListedSyncBody(ctx.wpId, payload as L3SyncItem))
    : postSoeSection(ctx.projectId, ctx.wpId, payload as L3SyncItem)),
})
