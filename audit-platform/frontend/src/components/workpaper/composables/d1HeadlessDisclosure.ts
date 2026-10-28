/**
 * D1 应收票据披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：Tab 同款 `useD1Disclosure`（主表取审定表共享模型，只读本底稿回复）→ 同一组展开行 /
 * 说明加载 / 快照函数（`d1DisclosureSnapshot`）→ 同一个 `buildD1SyncPayload`（适用准则 = 与 render-config 同源的项目适用
 * 准则，Tab 取宿主真源）。受限资产段（D1 → 五、32 / 八、93）只由底稿披露 Tab 推送，离屏不接。保存回调为空（离屏不改底稿）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useD1Disclosure } from './useD1Disclosure'
import { buildD1SyncPayload } from './d1NoteSectionMap'
import { buildD1DisclosureSnapshot, readD1SectionNotes } from './d1DisclosureSnapshot'

export const d1HeadlessProvider = defineHeadlessProvider({
  prefix: 'D1-',
  setup: ({ ctx, responses }) => useD1Disclosure({
    allResponses: ref(responses),
    wpId: ref(ctx.wpId),
    projectId: ref(ctx.projectId),
    variant: ctx.variant,
    saveImmediate: async () => {},
    isReadonly: ref(false),
  }),
  build: (d1, { ctx, responses }) => buildD1SyncPayload(
    ctx.variant,
    ctx.wpId,
    ctx.applicableStandards,
    buildD1DisclosureSnapshot(ctx.variant, d1, readD1SectionNotes(responses, ctx.variant)),
  ),
})
