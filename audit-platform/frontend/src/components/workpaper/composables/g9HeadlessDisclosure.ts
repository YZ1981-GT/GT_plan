/**
 * G9 其他非流动金融资产披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（`G9TabDisclosureBase`，上市 / 国企两个薄壳共用）同一套代码：`useG9Disclosure`（已存披露行 + 审计说明，
 * 立即读）→ 同一个快照 `g9DisclosureSyncSnapshot` → 同一个 `buildG9SyncPayload`（上市 五、20 / 国企 八、20）。
 * Tab 挂载时只读审定数、订阅审定事件、广播说明（都不进载荷），离屏不挂钩子，所以没有 prepare；保存回调为空（离屏不改底稿）。
 * 前缀与底稿主入口 `useG9FormData` 同口径（`G9`）。
 */
import { computed, ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useG9Disclosure } from './useG9Disclosure'
import { buildG9SyncPayload, g9DisclosureSyncSnapshot } from './g9DisclosureSyncPayload'

export const g9HeadlessProvider = defineHeadlessProvider({
  prefix: 'G9',
  setup: ({ ctx, responses }) => useG9Disclosure({
    variant: ctx.variant,
    wpId: ref(ctx.wpId),
    allResponses: computed(() => responses),
    debouncedSave: () => {},
    isReadonly: computed(() => false),
  }),
  build: (disc, { ctx }) => buildG9SyncPayload(ctx.wpId, ctx.variant, ctx.applicableStandards, g9DisclosureSyncSnapshot(disc)),
})
