/**
 * D3 预收账款披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿两版披露 Tab 同一套代码：外壳同款 `useD3CrossSheet`（本底稿回复 + 项目账龄配置段，subject='D3'）→ 本口径 Tab
 * 同款 composable（上市 `useD3DisclosureListed` / 国企 `useD3DisclosureSoe`）→ 同一个快照函数 → 同一个
 * `buildD3SyncPayload`（适用准则 = 与 render-config 同源的项目适用准则）。账龄配置由框架先预取进缓存（`useAgingConfig`
 * 离屏只套用缓存）；取不到时与组件内加载失败同一兜底 = 本科目默认预设段。保存回调为空（离屏不改底稿）。
 */
import { computed, ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { DEFAULT_SUBJECT_PRESETS, PRESET_SEGMENTS, useAgingConfig } from '@/composables/useAgingConfig'
import { useD3CrossSheet } from './useD3CrossSheet'
import { useD3DisclosureListed } from './useD3DisclosureListed'
import { useD3DisclosureSoe } from './useD3DisclosureSoe'
import { buildD3SyncPayload } from './d3NoteSectionMap'
import { buildD3ListedSnapshot, buildD3SoeSnapshot } from './d3DisclosureSnapshot'

export const d3HeadlessProvider = defineHeadlessProvider({
  prefix: 'D3-',
  needs: { aging: true },
  setup: ({ ctx, responses }) => {
    const allResponses = ref(responses)
    const projectId = ref(ctx.projectId)
    const { segments } = useAgingConfig(projectId, 'D3')
    const effective = computed(() => (segments.value.length ? segments.value : PRESET_SEGMENTS[DEFAULT_SUBJECT_PRESETS.D3]))
    const options = {
      allResponses,
      wpId: ref(ctx.wpId),
      projectId,
      saveImmediate: async () => {},
      debouncedSave: () => {},
      crossSheet: useD3CrossSheet({ allResponses, segments: effective }),
      isReadonly: ref(false),
      applicableStandards: ref([...ctx.applicableStandards]),
    }
    return ctx.variant === 'soe'
      ? { soe: useD3DisclosureSoe(options) }
      : { listed: useD3DisclosureListed(options) }
  },
  build: (d3, { ctx }) => {
    const standards = [...ctx.applicableStandards]
    if (d3.soe) {
      return buildD3SyncPayload('soe', ctx.wpId, standards, buildD3SoeSnapshot({
        section1Rows: d3.soe.section1Rows.value,
        section1Subtotal: d3.soe.section1Subtotal.value,
        section2Rows: d3.soe.section2Rows.value,
        section2Subtotal: d3.soe.section2Subtotal.value,
      }))
    }
    const l = d3.listed!
    return buildD3SyncPayload('listed', ctx.wpId, standards, buildD3ListedSnapshot({
      section1Rows: l.section1Rows.value,
      section1Subtotal: l.section1Subtotal.value,
      section2Rows: l.section2Rows.value,
      section2Subtotal: l.section2Subtotal.value,
      section3Rows: l.section3Rows.value,
      notes: { nature: l.note1.value, longTerm: l.note2.value, change: l.note3.value },
    }))
  },
})
