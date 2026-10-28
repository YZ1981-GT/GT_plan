/**
 * K13 营业外支出披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（上市 `K13TabDisclosureListed` / 国企 `K13TabDisclosureSoe`）同一套代码：Tab 挂载时的
 * `loadK13DisclosureState`（按固定去向分类逐行读回 + 附注说明）→ `loadK13DynamicRows`（已保存的动态去向行）→
 * `applyK13AutoFill`（从 K13-1 审定表取数，未匹配的去向追加为动态行；Tab 在这里逐行 / 动态行保存，离屏不传保存回调 ⇒
 * 只改内存）→「同步到附注」同一个 `k13DisclosureSyncRows` → 同一个 `buildK13SyncPayload`（上市 五、80 / 国企 八、77）。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildK13SyncPayload } from './k13NoteSectionMap'
import {
  applyK13AutoFill,
  k13DisclosureSyncRows,
  loadK13DisclosureState,
  loadK13DynamicRows,
  type K13DisclosureTabRow,
} from './k13DisclosureTabState'

interface K13HeadlessState {
  rows: K13DisclosureTabRow[]
  narrative: string
}

export const k13HeadlessProvider = defineHeadlessProvider<K13HeadlessState>({
  prefix: 'K13-',
  setup: () => ({ rows: [], narrative: '' }),
  // Tab onMounted：loadSavedData() → loadDynamicRows() → applyAutoFill(true)
  prepare: (state, { ctx, responses }) => {
    const saved = loadK13DisclosureState(responses, ctx.variant)
    state.rows = saved.rows
    if (saved.narrative != null) state.narrative = saved.narrative
    loadK13DynamicRows(state.rows, responses, ctx.variant)
    applyK13AutoFill(state.rows, responses, ctx.variant)
  },
  build: (state, { ctx }) =>
    buildK13SyncPayload(ctx.variant, ctx.wpId, k13DisclosureSyncRows(state.rows), state.narrative),
})
