/**
 * G5 长期应收款披露 Tab 的同步快照与载荷（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1）。
 *
 * 由 `G5TabDisclosureListed` / `G5TabDisclosureSOE` 的 `syncToDisclosureNotes` 原样抽出：按 composable 现值组快照；上市侧
 * 组合计提表是动态多表（`组合计提项目：{组合名}`），再按「上次同步成功推送的表名」算出要清理的旧组合表（`_removed_table_keys`）。
 * 发送、同步成功后的记账（`G5_LISTED_SYNCED_TABLES_ITEM`）与提示仍在 Tab；离屏同步不记账（不写底稿），下次同步照同一基线再算。
 */
import type { ChecklistResponse } from './useF1FormData'
import {
  buildG5ListedSyncPayload,
  buildG5SoeSyncPayload,
  g5PortfolioTableNames,
  type G5ListedSnapshot,
  type G5SoeSnapshot,
  type G5SyncFromWorkpaperPayload,
} from './g5DisclosureSyncPayload'
import { buildRemovedTableKeys, parseSyncedTableNames } from './disclosureSyncedTables'
import type { useG5DisclosureListed } from './useG5DisclosureListed'
import type { useG5DisclosureSoe } from './useG5DisclosureSoe'

/** 上市：上次同步成功推送的组合表名（Tab 同步成功后才记账，失败也写会把现存表当孤儿删） */
export const G5_LISTED_SYNCED_TABLES_ITEM = 'G5-disclosure-listed-synced-tables'

type G5ListedDisclosure = Pick<
  ReturnType<typeof useG5DisclosureListed>,
  'state' | 'natureDisplayRows' | 'methodDisplayRows' | 'movementDisplayRows' | 'noteText'
>
type G5SoeDisclosure = Pick<ReturnType<typeof useG5DisclosureSoe>, 'state' | 'natureDisplayRows' | 'noteText'>

export function g5ListedSnapshot(dis: G5ListedDisclosure): G5ListedSnapshot {
  const st = dis.state.value
  return {
    natureRows: dis.natureDisplayRows.value,
    methodRows: dis.methodDisplayRows.value,
    individualDetails: st.individualDetails,
    portfolios: st.portfolios,
    movementRows: dis.movementDisplayRows.value,
    writeoffRows: st.writeoffRows,
    unrealizedNote: st.unrealizedNote ?? '',
    noteText: dis.noteText.value ?? '',
  }
}

/** 上市 五、16 载荷 + 本次推送的组合表名（供 Tab 同步成功后记账） */
export function buildG5ListedTabSyncPayload(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  dis: G5ListedDisclosure,
  allResponses: ReadonlyMap<string, ChecklistResponse>,
): { payload: G5SyncFromWorkpaperPayload | null; pushed: string[] } {
  const snap = g5ListedSnapshot(dis)
  const pushed = g5PortfolioTableNames(snap.portfolios)
  const previouslySynced = parseSyncedTableNames(
    allResponses.get(G5_LISTED_SYNCED_TABLES_ITEM)?.remark ?? null,
  )
  const payload = buildG5ListedSyncPayload(
    wpId,
    applicableStandards,
    snap,
    buildRemovedTableKeys({ previouslySynced, pushed }),
  )
  return { payload, pushed }
}

export function g5SoeSnapshot(dis: G5SoeDisclosure): G5SoeSnapshot {
  const st = dis.state.value
  return {
    natureRows: dis.natureDisplayRows.value,
    derecogRows: st.derecogRows,
    continuing: st.continuing,
    provisionMethodNote: st.provisionMethodNote ?? '',
    noteText: dis.noteText.value ?? '',
  }
}

/** 国企 八、17 载荷（只推性质 / 终止确认 / 继续涉入 3 张表，没有动态表名） */
export function buildG5SoeTabSyncPayload(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  dis: G5SoeDisclosure,
): G5SyncFromWorkpaperPayload | null {
  return buildG5SoeSyncPayload(wpId, applicableStandards, g5SoeSnapshot(dis))
}
