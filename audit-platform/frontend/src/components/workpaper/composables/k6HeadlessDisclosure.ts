/**
 * K6 持有待售披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（上市 `K6TabDisclosureListed` / 国企 `K6TabDisclosureSoe`）同一套代码：Tab 挂载时的
 * `loadK6DisclosureState`（已保存资产表 → 默认分类；附注说明）+ Tab 同一个 `useK6NoteBlocks` 的 `load()`（附注另外 4 个
 * 录入区块）+ `applyK6AssetAutoFill`（按 `K6-2-rows` 明细聚合，只改内存）→「同步到附注」同一个 `k6DisclosurePayloads`：
 * 上市 五、11 一条；国企 八、12 + 持有待售负债 八、43 各一条（八、43 空行也发清理载荷，与 Tab 一致）。
 * 离屏不写底稿（区块保存回调置空）、不读负债汇总表 / CAS42（不进载荷）、不调 AI、不订阅审定事件。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useK6NoteBlocks, type K6NoteBlocks } from './useK6NoteBlocks'
import {
  applyK6AssetAutoFill,
  k6DisclosurePayloads,
  loadK6DisclosureState,
  type K6AssetRow,
} from './k6DisclosureTabState'

interface K6HeadlessState {
  blocks: K6NoteBlocks
  assets: K6AssetRow[]
  narrative: string
}

export const k6HeadlessProvider = defineHeadlessProvider<K6HeadlessState>({
  prefix: 'K6-',
  setup: ({ ctx, responses }) => ({
    blocks: useK6NoteBlocks({
      variant: ctx.variant,
      wpId: () => ctx.wpId,
      responses: () => responses,
      save: () => {},
      onChanged: () => {},
    }),
    assets: [],
    narrative: '',
  }),
  // Tab onMounted：loadSavedData()（资产表 + 附注说明 + 区块 load）→ applyAutoFill()；行身份不进载荷 ⇒ 空串
  prepare: (state, { ctx, responses }) => {
    const saved = loadK6DisclosureState(responses, ctx.variant, () => '')
    state.assets = saved.assets
    if (saved.narrative != null) state.narrative = saved.narrative
    state.blocks.load()
    applyK6AssetAutoFill(state.assets, responses, ctx.variant)
  },
  build: (state, { ctx }) => {
    const { main, liability } = k6DisclosurePayloads(ctx.variant, ctx.wpId, state.assets, state.blocks, state.narrative)
    return liability ? [main, liability] : main
  },
})
