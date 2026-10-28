/**
 * M1 应付股利（利润）披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：Tab 的 `useM1FormData` 只负责取 / 存本底稿 `M1-` 回复（框架按同一前缀取，离屏不存），
 * 表格状态由 `m1DisclosureForm` 的默认行 + 读回（Tab onMounted 同一函数）得到 → 同一个快照 + `buildM1SyncPayload`
 * （`buildM1SoeTabSyncPayload` / `buildM1ListedTabSyncPayload`，Tab 的同步函数调的也是它们）。
 *
 * 章节与 K3（及 L2）共用（国企 八、42 / 上市 五、42）：M1 只推「应付股利」子表，载荷不带 `_removed_table_keys`，
 * 按表名浅合并，不动其他底稿写的子表。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import {
  buildM1ListedTabSyncPayload,
  buildM1SoeTabSyncPayload,
  loadM1ListedDisclosureRows,
  loadM1SoeDisclosureRows,
  type M1ListedDisclosureRow,
  type M1SoeDisclosureRow,
} from './m1DisclosureForm'

type M1HeadlessInstance =
  | { variant: 'soe'; rows: M1SoeDisclosureRow[] }
  | { variant: 'listed'; rows: M1ListedDisclosureRow[] }

export const m1HeadlessProvider = defineHeadlessProvider<M1HeadlessInstance>({
  // 与 useM1FormData 的 ITEM_PREFIX 同口径（`M1-` 不会匹配 `M10-`）
  prefix: 'M1-',
  setup: ({ ctx, responses }) => (ctx.variant === 'soe'
    ? { variant: 'soe', rows: loadM1SoeDisclosureRows(responses) }
    : { variant: 'listed', rows: loadM1ListedDisclosureRows(responses) }),
  build: (inst, { ctx }) => (inst.variant === 'soe'
    ? buildM1SoeTabSyncPayload(ctx.wpId, inst.rows)
    : buildM1ListedTabSyncPayload(ctx.wpId, inst.rows)),
})
