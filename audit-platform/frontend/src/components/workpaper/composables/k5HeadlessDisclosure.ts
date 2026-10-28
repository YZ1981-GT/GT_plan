/**
 * K5 预计负债披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（上市 `K5TabDisclosureListed` / 国企 `K5TabDisclosureSoe`）同一套代码：Tab 挂载时的
 * `loadK5DisclosureState`（已保存表 → 默认分类；附注说明）+ `applyK5ProvisionAutoFill`（按 `K5-1-audited-total` 取数，
 * 只改内存）→「同步到附注」同一个 `k5DisclosureSyncRows` → 同一个 `buildK5SyncPayload`（上市 五、50 / 国企 八、55）。
 * 离屏不写底稿、不读或有负债 / 分项明细（不进载荷）、不调 AI、不订阅审定事件。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildK5SyncPayload } from './k5NoteSectionMap'
import {
  applyK5ProvisionAutoFill,
  k5DisclosureSyncRows,
  loadK5DisclosureState,
  type K5ProvisionRow,
} from './k5DisclosureTabState'

interface K5HeadlessState {
  rows: K5ProvisionRow[]
  narrative: string
}

export const k5HeadlessProvider = defineHeadlessProvider<K5HeadlessState>({
  prefix: 'K5-',
  setup: () => ({ rows: [], narrative: '' }),
  // Tab onMounted：loadSavedData() → applyAutoFill()；行身份不进载荷、离屏不落库 ⇒ 空串
  prepare: (state, { ctx, responses }) => {
    const saved = loadK5DisclosureState(responses, ctx.variant, () => '')
    state.rows = saved.rows
    if (saved.narrative != null) state.narrative = saved.narrative
    applyK5ProvisionAutoFill(state.rows, responses)
  },
  build: (state, { ctx }) =>
    buildK5SyncPayload(ctx.variant, ctx.wpId, k5DisclosureSyncRows(state.rows, ctx.variant), state.narrative),
})
