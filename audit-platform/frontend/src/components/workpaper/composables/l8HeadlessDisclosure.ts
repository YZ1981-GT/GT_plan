/**
 * L8 财务费用披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（上市 `L8TabDisclosureListed` / 国企 `L8TabDisclosureSoe`）同一套代码：Tab 初值（两期 `createEmptyL8Period()`、
 * 说明空串）→ Tab onMounted 的 `loadData()` + _restoreData（Tab 自建 `useL8FormData` 读本底稿 L8- 回复，与框架同口径；读回走
 * `restoreL8Disclosure`，只改内存）→「同步到附注」同一个快照 `buildL8DisclosureSnapshot` → 同一个 `buildL8SyncPayload`（上市 五、67 /
 * 国企 八、68，一个章节；Tab 不传适用准则，builder 不判口径）。上市带利息资本化说明；国企专项事项不进附注（Tab 也不推）。
 * 离屏不写底稿、不取试算表发生额（Tab 的披露表不用它）、不订阅审定事件、不触发 AI / 提示。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildL8SyncPayload, createEmptyL8Period, type L8PeriodValues } from './l8NoteSectionMap'
import { buildL8DisclosureSnapshot, restoreL8Disclosure } from './l8DisclosureTabState'

interface L8HeadlessState {
  current: L8PeriodValues
  prior: L8PeriodValues
  capitalizationNote: string
}

export const l8HeadlessProvider = defineHeadlessProvider<L8HeadlessState>({
  // 与 useL8FormData.loadResponses 同前缀（L8-{sheet}-{field}）
  prefix: 'L8-',
  setup: () => ({ current: createEmptyL8Period(), prior: createEmptyL8Period(), capitalizationNote: '' }),
  // Tab onMounted：loadData() → _restoreData()（没有已存就保持初值）
  prepare: (state, { ctx, responses }) => {
    const saved = restoreL8Disclosure(ctx.variant, responses)
    if (saved.periods) {
      state.current = saved.periods.current
      state.prior = saved.periods.prior
    }
    if (saved.capitalizationNote) state.capitalizationNote = saved.capitalizationNote
  },
  build: (state, { ctx }) => buildL8SyncPayload(ctx.wpId, buildL8DisclosureSnapshot(ctx.variant, state)),
})
