/**
 * J1 应付职工薪酬披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：`useJ1DisclosureSections`（同一份默认骨架 `J1_DISCLOSURE_DEFAULTS`、同一组说明键）→
 * Tab onMounted 的 `hydrate()` → 同一个快照 `j1DisclosureSnapshotOf` → 同一个 `buildJ1SyncPayload`（年度取本次刷新的
 * 审计年度，Tab 取审计上下文的同一个年度）。保存回调为空（离屏不改底稿）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import {
  buildJ1SyncPayload,
  j1DisclosureSnapshotOf,
  j1NoteKeys,
} from '@/components/workpaper/composables/j1NoteSectionMap'
import { useJ1DisclosureSections } from './useJ1DisclosureSections'
import { J1_DISCLOSURE_DEFAULTS } from './j1DisclosureDefaults'

export const j1HeadlessProvider = defineHeadlessProvider({
  prefix: 'J1-',
  setup: ({ ctx, responses }) => useJ1DisclosureSections({
    variant: ctx.variant,
    defaults: J1_DISCLOSURE_DEFAULTS[ctx.variant],
    allResponses: ref(responses),
    saveImmediate: async () => {},
    isReadonly: ref(false),
    noteKeys: j1NoteKeys(ctx.variant),
  }),
  prepare: (sections) => sections.hydrate(),
  build: (sections, { ctx }) => buildJ1SyncPayload({
    variant: ctx.variant,
    wpId: ctx.wpId,
    year: ctx.year,
    snapshot: j1DisclosureSnapshotOf(sections),
  }).body,
})
