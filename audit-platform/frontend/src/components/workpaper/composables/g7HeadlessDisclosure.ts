/** G7 长期股权投资离屏同步：恢复真实 Tab 状态，并以一次严格 batch 原子写入全部章节。 */
import http from '@/utils/http'
import {
  defineHeadlessProvider,
  type HeadlessSectionResult,
  type HeadlessSyncPayload,
} from '@/components/workpaper/headless/headlessFramework'
import { restoreG7ListedState, restoreG7SoeState } from './g7DisclosureStateCodec'
import {
  buildG7ListedBatchRequest,
  buildG7SoeBatchRequest,
  type G7BatchSyncItem,
  type G7BatchSyncRequest,
} from './g7DisclosureSyncPayload'

type Instance = { request: G7BatchSyncRequest | null }

function itemPayloads(request: G7BatchSyncRequest | null): G7BatchSyncItem[] {
  return request ? request.items : []
}

async function postBatch(
  instance: Instance,
  payloads: readonly HeadlessSyncPayload[],
  projectId: string,
): Promise<HeadlessSectionResult[]> {
  if (!instance.request) return []
  const items = payloads as readonly G7BatchSyncItem[]
  const response: any = await http.post(
    `/api/projects/${projectId}/disclosure-notes/sync-batch-from-workpaper`,
    { ...instance.request, items },
    { _silent: true } as any,
  )
  const data = response?.data ?? response
  const results = Array.isArray(data?.results) ? data.results : []
  if (results.length !== items.length) {
    throw new Error(`G7 批量同步回执数 ${results.length} 与请求章节数 ${items.length} 不一致`)
  }
  return items.map((payload, index) => {
    const result = results[index] ?? {}
    const section = String(result.section_id || payload.section_id)
    return {
      section,
      rows: Number(result.rows_synced ?? 0),
      kept: Array.isArray(result.push_kept) ? result.push_kept.length : 0,
    }
  })
}

export const g7HeadlessProvider = defineHeadlessProvider<Instance>({
  prefix: ['G7-main-disclosure-listed-v2', 'G7-main-disclosure-soe-v2'],
  setup: ({ ctx, responses }) => {
    if (ctx.variant === 'listed') {
      const restored = restoreG7ListedState(responses)
      return {
        request: restored.hasSource
          ? buildG7ListedBatchRequest({ wpId: ctx.wpId, year: ctx.year, state: restored.state })
          : null,
      }
    }
    const restored = restoreG7SoeState(responses)
    return {
      request: restored.hasSource
        ? buildG7SoeBatchRequest({ wpId: ctx.wpId, year: ctx.year, state: restored.state })
        : null,
    }
  },
  build: instance => itemPayloads(instance.request),
  postAll: (instance, payloads, { ctx }) => postBatch(instance, payloads, ctx.projectId),
})
