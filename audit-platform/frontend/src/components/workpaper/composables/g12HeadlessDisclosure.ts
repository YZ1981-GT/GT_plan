/**
 * G12 净敞口套期收益披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（`G12TabDisclosureListed` / `G12TabDisclosureSOE`）同一套代码：`useG12Disclosure`（已存披露行 + 附注说明，立即读）
 * → prepare 做 Tab 挂载时的回填 `applyAdjudicationPatch`（由 G12-1 审定 / G12-2 明细重算各行；Tab 挂载时在此之后保存并广播，
 * 离屏只改内存）→ 同一个快照 `g12DisclosureSyncSnapshot` → 同一个 `buildG12SyncPayload`（上市 五、70 / 国企 八、71）。
 * 离屏不挂钩子、不订阅窗口事件，保存回调为空。前缀与底稿主入口 `useG12FormData` 同口径（`G12`）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useG12Disclosure } from './useG12Disclosure'
import { buildG12SyncPayload, g12DisclosureSyncSnapshot } from './g12DisclosureSyncPayload'

export const g12HeadlessProvider = defineHeadlessProvider({
  prefix: 'G12',
  setup: ({ ctx, responses }) => useG12Disclosure({
    variant: ctx.variant,
    allResponses: ref(responses),
    wpId: ref(ctx.wpId),
    isReadonly: ref(false),
    debouncedSave: () => {},
  }),
  prepare: (dis) => {
    dis.applyAdjudicationPatch()
  },
  build: (dis, { ctx }) =>
    buildG12SyncPayload(ctx.wpId, ctx.variant, ctx.applicableStandards, g12DisclosureSyncSnapshot(dis)),
})
