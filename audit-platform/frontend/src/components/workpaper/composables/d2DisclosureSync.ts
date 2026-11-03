/**
 * D2 应收账款披露表 → 附注同步的发送步骤（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-header-formula-closure R2.3）。
 *
 * 只做「基线播种 → 按快照建载荷 → POST sync-from-workpaper → 记录已同步表名」四步；提示、事件、受限资产段等
 * 页面行为留在调用方（`D2DisclosureNoteBody.syncToDisclosureNotes`）。两条路径因此发出逐字节相同的载荷。
 */
import type { Ref } from 'vue'
import http from '@/utils/http'
import { getDisclosureNoteDetail } from '@/services/auditPlatformApi'
import {
  buildD2SyncPayload,
  D2_NOTE_SECTION,
  type D2DisclosureSnapshot,
  type D2DisclosureVariant,
  type D2SyncPayload,
} from './d2NoteSectionMap'
import { dataTableNames } from './disclosureSyncedTables'

/** `useD2DisclosureNote` 返回值里同步要用的四项 */
export interface D2DisclosureSyncSource {
  syncedTableNames: Ref<string[]>
  seedSyncedTablesFromNote: (noteTableData: unknown) => string[]
  buildSnapshot: () => D2DisclosureSnapshot
  markSynced: (tableNames: readonly string[]) => void
}

export interface D2DisclosureSyncContext {
  projectId: string
  /** 审计年度；取不到（null）时不读附注播种基线（不按今年猜） */
  year: number | null
  variant: D2DisclosureVariant
  wpId: string
  applicableStandards: readonly string[] | null
  /** 离屏同步自己汇总提示：请求不经全局拦截器弹错 */
  silent?: boolean
}

/**
 * R7.5 基线播种：首次同步（尚无「上次已同步表名」持久化）时读一次附注现存表名，按 D2 命名空间过滤后写入基线 →
 * 让上线前就残留的孤儿表在本轮一次性被清掉。读取失败（附注尚未生成）不阻断同步，下次同步再试。
 * Tab 与离屏同步同一步（离屏 provider 在 `prepare` 里调，spec note-pull-followup-closure R1）。
 */
export async function seedD2SyncBaseline(
  source: Pick<D2DisclosureSyncSource, 'syncedTableNames' | 'seedSyncedTablesFromNote'>,
  ctx: Pick<D2DisclosureSyncContext, 'projectId' | 'year' | 'variant'>,
): Promise<void> {
  if (source.syncedTableNames.value.length !== 0 || ctx.year == null) return
  try {
    const detail: any = await getDisclosureNoteDetail(ctx.projectId, ctx.year, D2_NOTE_SECTION[ctx.variant])
    source.seedSyncedTablesFromNote(detail?.table_data)
  } catch {
    // 附注章节不存在 / 网络失败 → 跳过播种
  }
}

export async function postD2DisclosureSync(
  source: D2DisclosureSyncSource,
  ctx: D2DisclosureSyncContext,
): Promise<{ rows: number; payload: D2SyncPayload }> {
  await seedD2SyncBaseline(source, ctx)
  const payload = buildD2SyncPayload(ctx.variant, ctx.wpId || '', ctx.applicableStandards ?? null, source.buildSnapshot())
  const result: any = await http.post(
    `/api/projects/${ctx.projectId}/disclosure-notes/sync-from-workpaper`,
    payload,
    ...(ctx.silent ? [{ _silent: true } as any] : []),
  )
  const data = result?.data ?? result
  // R7：POST 成功后才记录本轮推送的子表名，作为下次孤儿表差集的基准。
  // 失败路径绝不写入 —— 否则下次会把本轮表名当「上次已同步」而误删现存表。
  source.markSynced(dataTableNames(payload.sub_table_data as Record<string, unknown>))
  return { rows: Number(data?.rows_synced ?? 0), payload }
}
