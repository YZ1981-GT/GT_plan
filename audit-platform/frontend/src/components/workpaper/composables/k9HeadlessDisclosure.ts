/**
 * K9 管理费用披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：Tab onMounted 的「读已保存行（缺失回费用性质清单）→ 按 K9-1 审定表回填」
 * （`loadK9DisclosureState` + `applyK9AutoFill`）→ 同步按钮的明细行 `k9DisclosureSyncRows` → 同一个 `buildK9SyncPayload`。
 * 回填只改内存里的行（Tab 挂载时也不写底稿）；行身份不进载荷。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildK9SyncPayload } from './k9NoteSectionMap'
import {
  applyK9AutoFill,
  K9_HEADLESS_ROW_IDENTITY,
  k9DisclosureSyncRows,
  loadK9DisclosureState,
} from './k9DisclosureSnapshot'

export const k9HeadlessProvider = defineHeadlessProvider({
  // 与宿主 GtK9AdminExpenses 的条目口径一致（K9-{sheet}-{field}）
  prefix: 'K9-',
  setup: ({ ctx, responses }) => loadK9DisclosureState(responses, ctx.variant, K9_HEADLESS_ROW_IDENTITY),
  prepare: (state, { responses }) => applyK9AutoFill(responses, state.rows),
  build: (state, { ctx }) =>
    buildK9SyncPayload(ctx.variant, ctx.wpId, k9DisclosureSyncRows(state.rows), state.narrativeText),
})
