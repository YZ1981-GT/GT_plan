/**
 * D6 合同资产披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：外壳同款 `useD6CrossSheet`（只读本底稿回复）→ Tab 同款 `useD6Disclosure` →
 * 同一个快照函数 `buildD6DisclosureSnapshot` → 同一个 `buildD6SyncPayload`（适用准则照 Tab 传 null）。
 * 保存回调为空（离屏不改底稿）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useD6CrossSheet } from './useD6CrossSheet'
import { useD6Disclosure } from './useD6Disclosure'
import { buildD6SyncPayload } from './d6NoteSectionMap'
import { buildD6DisclosureSnapshot } from './d6DisclosureSnapshot'

export const d6HeadlessProvider = defineHeadlessProvider({
  prefix: ['D6-', 'D6A-'],
  setup: ({ ctx, responses }) => {
    const allResponses = ref(responses)
    return useD6Disclosure({
      allResponses,
      crossSheet: useD6CrossSheet({ allResponses }),
      wpId: ref(ctx.wpId),
      projectId: ref(ctx.projectId),
      saveImmediate: async () => {},
      debouncedSave: () => {},
    })
  },
  build: (d6, { ctx }) => buildD6SyncPayload(ctx.variant, ctx.wpId, null, buildD6DisclosureSnapshot(ctx.variant, {
    listedSections: d6.listedSections.value,
    soeSections: d6.soeSections.value,
    majorChangeRows: d6.majorChangeRows.value,
    mainFormat: d6.mainFormat.value,
    impairmentPriorRows: d6.impairmentPriorRows.value,
    singlePriorRows: d6.singlePriorRows.value,
    groupedDetails: d6.groupedDetails.value,
    noteTexts: d6.noteTexts.value,
  })),
})
