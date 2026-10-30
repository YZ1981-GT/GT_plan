/**
 * I3 商誉披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：
 * - 外壳 `GtI3Goodwill` 用 `useI3CrossSheet(allResponses).disclosureAutoFill` 现算跨 sheet 取数传给披露 Tab
 *   （`crossSheetAutoFill`）⇒ 离屏用同一个 composable、同一批回复现算；
 * - Tab 用 `useI3Disclosure`，挂载时先 `applyAutoFill()`（没有已存矩阵时按 I3-2 明细取数，取不到补合计行）⇒ 离屏在
 *   `prepare` 里调同一个函数（保存回调为空，离屏不改底稿）；
 * - 同一个 `getSyncSnapshot` → 同一个 `buildI3ListedSyncPayloads` / `buildI3SoeSyncPayloads`。
 *
 * Tab「原值 / 减值矩阵都为空不同步」的拦截在 `applyAutoFill` 之后不会出现（跨 sheet 取数结果恒有键 ⇒ 两个矩阵都会补行），
 * 离屏不另设拦截。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useI3Disclosure } from './useI3Disclosure'
import { useI3CrossSheet } from './useI3CrossSheet'
import { buildI3ListedSyncPayloads, buildI3SoeSyncPayloads } from './i3DisclosureSyncPayload'

export const i3HeadlessProvider = defineHeadlessProvider({
  prefix: 'I3-',
  setup: ({ ctx, responses }) => {
    const allResponses = ref(responses)
    const crossSheet = useI3CrossSheet(allResponses)
    return useI3Disclosure(ref(ctx.wpId), ref(ctx.projectId), allResponses, {
      variant: ref(ctx.variant),
      crossSheetAutoFill: crossSheet.disclosureAutoFill,
      onSave: () => {},
    })
  },
  prepare: (disc) => disc.applyAutoFill(),
  build: (disc, { ctx }) => (ctx.variant === 'listed'
    ? buildI3ListedSyncPayloads(ctx.wpId, ctx.applicableStandards, disc.getSyncSnapshot())
    : buildI3SoeSyncPayloads(ctx.wpId, ctx.applicableStandards, disc.getSyncSnapshot())),
})
