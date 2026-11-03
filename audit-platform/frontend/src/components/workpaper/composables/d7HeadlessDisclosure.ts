/**
 * D7 合同负债披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：外壳同款 `useD7CrossSheet`（本底稿回复 + 项目账龄配置段，subject='D7'）→ Tab 同款
 * `useD7Disclosure` → 同一个快照函数 `buildD7DisclosureSnapshot` → 同一个 `buildD7SyncPayload`（适用准则照 Tab 传 null）。
 * 账龄配置由框架先预取进缓存（`useAgingConfig` 离屏只套用缓存）；取不到时与组件内加载失败同一兜底 = 本科目默认预设段。
 * 保存回调为空（离屏不改底稿）。
 */
import { computed, ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { DEFAULT_SUBJECT_PRESETS, PRESET_SEGMENTS, useAgingConfig } from '@/composables/useAgingConfig'
import { useD7CrossSheet } from './useD7CrossSheet'
import { useD7Disclosure } from './useD7Disclosure'
import { buildD7SyncPayload } from './d7NoteSectionMap'
import { buildD7DisclosureSnapshot } from './d7DisclosureSnapshot'

export const d7HeadlessProvider = defineHeadlessProvider({
  prefix: ['D7-', 'D7A-'],
  needs: { aging: true },
  setup: ({ ctx, responses }) => {
    const allResponses = ref(responses)
    const projectId = ref(ctx.projectId)
    const { segments } = useAgingConfig(projectId, 'D7')
    const effective = computed(() => (segments.value.length ? segments.value : PRESET_SEGMENTS[DEFAULT_SUBJECT_PRESETS.D7]))
    return useD7Disclosure({
      allResponses,
      crossSheet: useD7CrossSheet({ allResponses, segments: effective }),
      wpId: ref(ctx.wpId),
      projectId,
      saveImmediate: async () => {},
      debouncedSave: () => {},
    })
  },
  build: (d7, { ctx }) => buildD7SyncPayload(ctx.variant, ctx.wpId, null, buildD7DisclosureSnapshot(ctx.variant, {
    listedSections: d7.listedSections.value,
    soeSections: d7.soeSections.value,
    noteTexts: d7.noteTexts.value,
  })),
})
