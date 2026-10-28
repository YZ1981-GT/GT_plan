/**
 * G13 公允价值变动收益披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（`G13TabDisclosureListed` / `G13TabDisclosureSOE`）同一套代码：`useG13Disclosure`（已存披露行 / 附注说明，立即读）
 * → prepare 做 Tab 挂载时的回填 `pullLatestAdjudicated({ persist: false })`（审定数 + G13-2 明细本期 + G13-1 上期；Tab 挂载时明细回填
 * 后保存，离屏只改内存）→ Tab 同一个快照 `getSyncSnapshot()` + 同一个 `buildG13SyncPayloads`（上市 五、75 / 国企 八、72）。
 * 离屏不挂钩子、不订阅审定事件、不广播，保存回调为空。前缀与底稿主入口 `useG13FormData` 同口径（`G13`）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useG13Disclosure } from './useG13Disclosure'
import { buildG13SyncPayloads } from './g13DisclosureSyncPayload'

export const g13HeadlessProvider = defineHeadlessProvider({
  prefix: 'G13',
  setup: ({ ctx, responses }) => useG13Disclosure({
    variant: ctx.variant,
    allResponses: ref(responses),
    wpId: ref(ctx.wpId),
    projectId: ref(ctx.projectId),
    isReadonly: ref(false),
    debouncedSave: () => {},
  }),
  prepare: (dis) => dis.pullLatestAdjudicated({ persist: false }),
  build: (dis, { ctx }) => buildG13SyncPayloads(ctx.wpId, ctx.variant, ctx.applicableStandards ?? [], dis.getSyncSnapshot()),
})
