/**
 * G3 应收股利披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：`useG3DisclosureState`（表格行 + 审计说明，由两个 Tab 原样抽出）→
 * `buildG3ListedSyncPayloads` / `buildG3SoeSyncPayloads`（上市 五、8 / 国企 八、9，与 G2、K1 共用章节，后端按子表名浅合并）。
 * Tab 挂载时只订阅审定事件（不取数），所以没有 prepare；从 G3-1 带入、提示等界面行为不在这里。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useG3DisclosureState, type G3DisclosureTabState } from './g3DisclosureTabState'
import { buildG3ListedSyncPayloads, buildG3SoeSyncPayloads } from './g3DisclosureSyncPayload'

type G3HeadlessInstance =
  | { variant: 'soe'; state: G3DisclosureTabState<'soe'> }
  | { variant: 'listed'; state: G3DisclosureTabState<'listed'> }

export const g3HeadlessProvider = defineHeadlessProvider<G3HeadlessInstance>({
  prefix: 'G3-',
  setup: ({ ctx, responses }) => (ctx.variant === 'soe'
    ? { variant: 'soe', state: useG3DisclosureState('soe', ref(responses)) }
    : { variant: 'listed', state: useG3DisclosureState('listed', ref(responses)) }),
  build: (inst, { ctx }) => (inst.variant === 'soe'
    ? buildG3SoeSyncPayloads(ctx.wpId, ctx.applicableStandards, inst.state.tableRows.value, inst.state.noteText.value)
    : buildG3ListedSyncPayloads(ctx.wpId, ctx.applicableStandards, inst.state.tableRows.value, inst.state.noteText.value)),
})
