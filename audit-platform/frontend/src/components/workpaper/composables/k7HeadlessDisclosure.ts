/**
 * K7 递延收益披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：Tab onMounted 的「读已保存行（缺失回默认行）→ 从 K7-1 审定表自动取数」
 * （`loadK7DisclosureState` + `applyK7AutoFill`）→ 同步按钮的快照 `buildK7DisclosureSnapshot` → 同一个
 * `buildK7SyncPayload`。行身份不进载荷，离屏用 `K7_HEADLESS_ROW_IDENTITY`；自动取数只改内存里的行（Tab 挂载时
 * 也不写底稿），离屏不改底稿。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildK7SyncPayload } from './k7NoteSectionMap'
import {
  applyK7AutoFill,
  buildK7DisclosureSnapshot,
  K7_HEADLESS_ROW_IDENTITY,
  loadK7DisclosureState,
} from './k7DisclosureSnapshot'

export const k7HeadlessProvider = defineHeadlessProvider({
  // 与宿主 GtK7DeferredIncome 的条目口径一致（K7-{sheet}-{field}）
  prefix: 'K7-',
  setup: ({ ctx, responses }) => loadK7DisclosureState(responses, ctx.variant, K7_HEADLESS_ROW_IDENTITY),
  prepare: (state, { responses }) => applyK7AutoFill(responses, state.assetRows, state.incomeRows),
  build: (state, { ctx }) => {
    const snapshot = buildK7DisclosureSnapshot(ctx.variant, state)
    return buildK7SyncPayload(ctx.variant, ctx.wpId, snapshot.rows, state.narrativeText, snapshot.grantRows)
  },
})
