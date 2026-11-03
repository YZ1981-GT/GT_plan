/**
 * D5 应收款项融资披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：外壳同款 `useD5CrossSheet`（只读本底稿回复）→ Tab 同款 `useD5Disclosure` →
 * 同一个快照函数 `buildD5DisclosureSnapshot`（已质押 / 已背书两表按 Tab 同一默认行 + 持久化解析）→ 同一个
 * `buildD5SyncPayload`。适用准则照 Tab 传 null（Tab 现状，见报告）。保存回调为空（离屏不改底稿）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useD5CrossSheet } from './useD5CrossSheet'
import { useD5Disclosure } from './useD5Disclosure'
import { buildD5SyncPayload } from './d5NoteSectionMap'
import { buildD5DisclosureSnapshot, readD5EndorsedRows, readD5PledgedRows } from './d5DisclosureSnapshot'

export const d5HeadlessProvider = defineHeadlessProvider({
  prefix: 'D5-',
  setup: ({ ctx, responses }) => {
    const allResponses = ref(responses)
    return useD5Disclosure({
      allResponses,
      wpId: ref(ctx.wpId),
      projectId: ref(ctx.projectId),
      debouncedSave: () => {},
      isReadonly: ref(false),
      crossSheet: useD5CrossSheet({ allResponses }),
    })
  },
  build: (d5, { ctx, responses }) => buildD5SyncPayload(ctx.variant, ctx.wpId, null, buildD5DisclosureSnapshot(ctx.variant, {
    listedSections: d5.listedSections.value,
    soeSections: d5.soeSections.value,
    impairmentRows: d5.impairmentRows.value,
    pledgedRows: readD5PledgedRows(responses),
    endorsedRows: readD5EndorsedRows(responses),
    noteTexts: d5.noteTexts.value,
  })),
})
