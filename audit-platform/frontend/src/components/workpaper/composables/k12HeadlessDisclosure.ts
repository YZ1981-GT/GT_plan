/**
 * K12 营业外收入披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（上市 `K12TabDisclosureListed` / 国企 `K12TabDisclosureSoe`）同一套代码：Tab 挂载时的
 * `loadK12DisclosureState`（按分类逐行读回 + 附注说明）+ `applyK12AutoFill`（从 K12-1 审定表按名称取数；Tab 在这里逐行
 * 保存，离屏不传保存回调 ⇒ 只改内存）→「同步到附注」同一个 `k12DisclosureSyncRows` → 同一个 `buildK12SyncPayload`
 * （上市 五、79 / 国企 八、76，四列含「计入当期非经常性损益的金额」）。国企政府补助明细子表不进载荷，离屏也不读。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildK12SyncPayload } from './k12NoteSectionMap'
import {
  applyK12AutoFill,
  k12DisclosureSyncRows,
  loadK12DisclosureState,
  type K12DisclosureTabRow,
} from './k12DisclosureTabState'

interface K12HeadlessState {
  rows: K12DisclosureTabRow[]
  narrative: string
}

export const k12HeadlessProvider = defineHeadlessProvider<K12HeadlessState>({
  prefix: 'K12-',
  setup: () => ({ rows: [], narrative: '' }),
  // Tab onMounted：loadSavedData() → applyAutoFill(true)
  prepare: (state, { ctx, responses }) => {
    const saved = loadK12DisclosureState(responses, ctx.variant)
    state.rows = saved.rows
    if (saved.narrative != null) state.narrative = saved.narrative
    applyK12AutoFill(state.rows, responses)
  },
  build: (state, { ctx }) =>
    buildK12SyncPayload(ctx.variant, ctx.wpId, k12DisclosureSyncRows(state.rows), state.narrative),
})
