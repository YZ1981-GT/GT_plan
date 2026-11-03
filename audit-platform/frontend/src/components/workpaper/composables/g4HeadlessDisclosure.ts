/**
 * G4 债权投资披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：`useG4DisclosureTabState`（两个 Tab 原样抽出的段落默认行 + 打开时回显 + 同步快照）→
 * 同一个 `buildG4SyncPayload`（上市 五、14 / 国企 八、15：主表 + 三阶段表 + 说明段）。Tab 挂载时只订阅审定事件
 * （事件到达才改合计行）并回显，所以 prepare 只做回显；文本保存 / 广播 / AI / 提示不在这里，离屏不写底稿。
 *
 * 🔴 回显数据源：Tab 读 htmlData 的 `checklist_responses` / `responses`，render-config 下发的却是 `responses_snapshot`
 *    ⇒ Tab 打开时三阶段明细 / 说明恒为默认值（缺陷已登记）。离屏按回显函数支持的 `checklist_responses` 形态把本底稿
 *    `G4-` 回复喂进去（`g4ResponsesAsHtmlData`），推的是上次保存的三阶段明细 / 说明。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildG4SyncPayload } from './g4DisclosureSyncPayload'
import { g4ResponsesAsHtmlData, useG4DisclosureTabState } from './g4DisclosureTabState'

export const g4HeadlessProvider = defineHeadlessProvider({
  prefix: 'G4-',
  setup: ({ ctx, responses }) => {
    const htmlData = g4ResponsesAsHtmlData(responses)
    return useG4DisclosureTabState(ctx.variant, () => htmlData)
  },
  prepare: (state) => state.loadFromHtmlData(),
  build: (state, { ctx }) =>
    buildG4SyncPayload(ctx.wpId, ctx.variant, ctx.applicableStandards, state.buildSyncSnapshot()),
})
