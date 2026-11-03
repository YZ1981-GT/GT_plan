/**
 * G14 信用减值损失披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（`G14TabDisclosureListed` / `G14TabDisclosureSOE`）同一套代码：`useG14Disclosure`（已存披露行 / 附注说明，立即读）
 * → prepare 做 Tab 挂载时的回填 `pullLatestAdjudicated({ persist: false })`（审定数 + G14-2 明细本期 + G14-1 上期；Tab 挂载时两步回填
 * 各自保存，离屏只改内存）→ Tab 同一个快照 `getSyncSnapshot()` + 同一个 `buildG14SyncPayloads`（上市 五、76 / 国企 八、73）。
 * 离屏不挂钩子、不订阅窗口事件、不广播，保存回调为空。前缀与底稿主入口 `useG14FormData` 同口径（`G14`）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useG14Disclosure } from './useG14Disclosure'
import { buildG14SyncPayloads } from './g14DisclosureSyncPayload'

export const g14HeadlessProvider = defineHeadlessProvider({
  prefix: 'G14',
  setup: ({ ctx, responses }) => useG14Disclosure({
    variant: ctx.variant,
    allResponses: ref(responses),
    wpId: ref(ctx.wpId),
    projectId: ref(ctx.projectId),
    isReadonly: ref(false),
    debouncedSave: () => {},
  }),
  prepare: (dis) => dis.pullLatestAdjudicated({ persist: false }),
  build: (dis, { ctx }) => buildG14SyncPayloads(ctx.wpId, ctx.variant, ctx.applicableStandards ?? [], dis.getSyncSnapshot()),
})
