/**
 * K11 资产减值损失披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（上市 `K11TabDisclosureListed` / 国企 `K11TabDisclosureSoe`）同一套代码：Tab 挂载时的
 * `loadK11DisclosureState`（已保存行 → K11-1 审定表行 → 18 项默认分类；附注说明）+ `applyK11AutoFill`（按
 * `K11-1-audited-by-category` 自动取数，只改内存）→「同步到附注」同一个 `k11DisclosureSyncRows` → 同一个
 * `buildK11SyncPayload`（上市 五、77 / 国企 八、74，符号翻转在 builder 单点做）。离屏不写底稿、不订阅审定事件。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildK11SyncPayload } from './k11NoteSectionMap'
import {
  applyK11AutoFill,
  k11DisclosureSyncRows,
  loadK11DisclosureState,
  type K11DisclosureTabRow,
} from './k11DisclosureTabState'

interface K11HeadlessState {
  rows: K11DisclosureTabRow[]
  narrative: string
}

export const k11HeadlessProvider = defineHeadlessProvider<K11HeadlessState>({
  prefix: 'K11-',
  setup: () => ({ rows: [], narrative: '' }),
  // Tab onMounted：loadSavedData() → applyAutoFill()
  prepare: (state, { ctx, responses }) => {
    // 行身份不进载荷（k11DisclosureSyncRows 只取类别与金额），离屏也不落库 ⇒ 空串
    const saved = loadK11DisclosureState(responses, ctx.variant, () => '')
    state.rows = saved.rows
    if (saved.narrative != null) state.narrative = saved.narrative
    applyK11AutoFill(state.rows, responses)
  },
  build: (state, { ctx }) =>
    buildK11SyncPayload(ctx.variant, ctx.wpId, k11DisclosureSyncRows(state.rows), state.narrative),
})
