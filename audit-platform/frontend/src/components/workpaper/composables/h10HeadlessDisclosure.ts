/**
 * H10 资产处置损益披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（`H10TabDisclosureBase`，上市 / 国企同一组件按 variant 分）同一套代码：`useH10Disclosure`
 * （immediate watcher 从 checklist 响应现算主表 / 试运行明细 / 附注文本）→ 挂载时的 `pullLatestAdjudicated`
 * → Tab「同步到附注」同参调 `buildH10SyncPayloads(wpId, variant, applicableStandards, getSyncSnapshot())`。
 * 只取 `H10` 开头的条目（与宿主 `useH10FormData` 同口径）；保存回调为空（离屏不改底稿）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useH10Disclosure } from './useH10Disclosure'
import { buildH10SyncPayloads } from './h10DisclosureSyncPayload'

export const h10HeadlessProvider = defineHeadlessProvider({
  prefix: 'H10',
  setup: ({ ctx, responses }) => useH10Disclosure({
    variant: ctx.variant,
    allResponses: ref(responses),
    debouncedSave: () => {},
    wpId: ref(ctx.wpId),
    projectId: ref(ctx.projectId),
    isReadonly: ref(false),
  }),
  prepare: (dis) => dis.pullLatestAdjudicated(),
  build: (dis, { ctx }) => buildH10SyncPayloads(ctx.wpId, ctx.variant, ctx.applicableStandards, dis.getSyncSnapshot()),
})
