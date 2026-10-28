/**
 * G8 其他权益工具投资披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（`G8TabDisclosureBase`，上市 / 国企两个薄壳共用）同一套代码：`useG8Disclosure`（已存余额表 / OCI 或期末明细 /
 * 指定原因 / 审计说明，立即读）→ 同一个快照 `g8DisclosureSyncSnapshot` → 同一个 `buildG8SyncPayload`（上市 五、19 / 国企 八、19）。
 * Tab 挂载时只读审定数、订阅审定事件、广播说明（都不进载荷），离屏不挂钩子，所以没有 prepare；「从 G8-2 带入」「指定原因草稿」
 * 是按钮动作（带确认框），离屏不做。保存回调为空（离屏不改底稿）。前缀与底稿主入口 `useG8FormData` 同口径（`G8`）。
 */
import { computed, ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useG8Disclosure } from './useG8Disclosure'
import { buildG8SyncPayload, g8DisclosureSyncSnapshot } from './g8DisclosureSyncPayload'

export const g8HeadlessProvider = defineHeadlessProvider({
  prefix: 'G8',
  setup: ({ ctx, responses }) => useG8Disclosure({
    variant: ctx.variant,
    wpId: ref(ctx.wpId),
    allResponses: computed(() => responses),
    debouncedSave: () => {},
    isReadonly: computed(() => false),
  }),
  build: (disc, { ctx }) =>
    buildG8SyncPayload(ctx.wpId, ctx.variant, ctx.applicableStandards, g8DisclosureSyncSnapshot(ctx.variant, disc)),
})
