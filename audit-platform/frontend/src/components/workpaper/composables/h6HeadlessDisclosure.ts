/**
 * H6 固定资产清理披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（`H6TabDisclosure`，上市 / 国企同一组件按 variant 分）同一套代码：挂载时 `hydrateH6DisclosureState`
 * 读回状态、清理明细为空则 `seedH6ClearingFromLocal` 从本底稿 H6-1 / H6-2 带入（离屏不保存），「同步到附注」以
 * `h6DisclosureSyncSnapshot` 调 `buildH6ListedSyncPayloads` / `buildH6SoeSyncPayloads`（Tab 传空适用准则，这里同参）。
 * 「从 H1 带入固定资产行」是按钮动作（跨底稿取数），挂载时不跑，离屏也不跑。
 */
import { reactive, ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import {
  H6_LISTED_KEYS,
  H6_SOE_KEYS,
  createDefaultState,
  h6DisclosureSyncSnapshot,
  hydrateH6DisclosureState,
} from './h6DisclosureModel'
import { seedH6ClearingFromLocal, useH6Disclosure } from './useH6Disclosure'
import { buildH6ListedSyncPayloads, buildH6SoeSyncPayloads } from './h6DisclosureSyncPayload'

export const h6HeadlessProvider = defineHeadlessProvider({
  prefix: 'H6-',
  setup: ({ responses }) => ({
    disclosure: useH6Disclosure(ref(responses)),
    state: reactive(createDefaultState()),
  }),
  prepare: ({ disclosure, state }, { ctx, responses }) => {
    hydrateH6DisclosureState(state, responses, ctx.variant === 'listed' ? H6_LISTED_KEYS : H6_SOE_KEYS)
    seedH6ClearingFromLocal(state, disclosure.pullFromLocalSources)
  },
  build: ({ state }, { ctx }) => (ctx.variant === 'listed'
    ? buildH6ListedSyncPayloads(ctx.wpId, [], h6DisclosureSyncSnapshot(state))
    : buildH6SoeSyncPayloads(ctx.wpId, [], h6DisclosureSyncSnapshot(state))),
})
