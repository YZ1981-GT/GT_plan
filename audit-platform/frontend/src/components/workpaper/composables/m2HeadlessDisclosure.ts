/**
 * M2 实收资本（股本）披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：Tab 的 `useM2FormData` 只负责取 / 存本底稿 `M2-` 回复（框架按同一前缀取，离屏不存），
 * 表格与三段说明由 `m2DisclosureForm` 的默认状态 + 读回（Tab onMounted 同一函数，含旧字段兼容与期末 / 占比重算）得到
 * → 同一个快照 + `buildM2ListedSyncPayload`（上市 五、53）/ `buildM2SoeSyncPayload`（国企 八、58）。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import {
  buildM2ListedTabSyncPayload,
  buildM2SoeTabSyncPayload,
  loadM2ListedDisclosure,
  loadM2SoeDisclosure,
  type M2ListedDisclosureState,
  type M2SoeDisclosureState,
} from './m2DisclosureForm'

type M2HeadlessInstance =
  | { variant: 'listed'; state: M2ListedDisclosureState }
  | { variant: 'soe'; state: M2SoeDisclosureState }

export const m2HeadlessProvider = defineHeadlessProvider<M2HeadlessInstance>({
  // 与 useM2FormData 的 ITEM_PREFIX 同口径
  prefix: 'M2-',
  setup: ({ ctx, responses }) => (ctx.variant === 'listed'
    ? { variant: 'listed', state: loadM2ListedDisclosure(responses) }
    : { variant: 'soe', state: loadM2SoeDisclosure(responses) }),
  build: (inst, { ctx }) => (inst.variant === 'listed'
    ? buildM2ListedTabSyncPayload(ctx.wpId, inst.state)
    : buildM2SoeTabSyncPayload(ctx.wpId, inst.state)),
})
