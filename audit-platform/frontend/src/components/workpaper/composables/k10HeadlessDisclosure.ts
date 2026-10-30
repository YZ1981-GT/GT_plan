/**
 * K10 其他收益披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：Tab onMounted 的 `loadK10DisclosureState`（默认分类行 → 已保存行覆盖 → 动态追加行 → 说明）→
 * 同步按钮的快照 `buildK10DisclosureSnapshot`（国企另汇总「其中：政府补助」）→ 同一个 `buildK10SyncPayload`。
 * 「从审定表取数」是按钮 / 事件动作（有提示、逐行写底稿），Tab 挂载时不跑，离屏也不跑。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildK10SyncPayload } from './k10NoteSectionMap'
import { buildK10DisclosureSnapshot, loadK10DisclosureState } from './k10DisclosureSnapshot'

export const k10HeadlessProvider = defineHeadlessProvider({
  // 与宿主 GtK10OtherIncome 的条目口径一致（K10-{sheet}-{field}）
  prefix: 'K10-',
  setup: ({ ctx, responses }) => loadK10DisclosureState(responses, ctx.variant),
  build: (state, { ctx }) => {
    const snapshot = buildK10DisclosureSnapshot(ctx.variant, state.rows)
    return buildK10SyncPayload(ctx.variant, ctx.wpId, snapshot.rows, state.narrativeText, snapshot.govGrantRow)
  },
})
