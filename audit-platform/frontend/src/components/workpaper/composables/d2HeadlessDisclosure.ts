/**
 * D2 应收账款披露表离屏同步（附注页「刷新」用，spec note-pull-header-formula-closure R2.3 / note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：`useD2DisclosureNote`（由 checklist 响应 + 项目账龄配置现算披露表）→ 同一个孤儿表基线播种
 * `seedD2SyncBaseline` → 同一个 `buildD2SyncPayload`（Tab 经 `postD2DisclosureSync` 走同样三步）。账龄配置由框架先预取进缓存
 * （`useAgingConfig` 离屏时只套用缓存），保存回调为空（离屏不改底稿；已同步表名只在本次内存里用）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useD2DisclosureNote } from './useD2DisclosureNote'
import { buildD2SyncPayload } from './d2NoteSectionMap'
import { seedD2SyncBaseline } from './d2DisclosureSync'

export const d2HeadlessProvider = defineHeadlessProvider({
  prefix: 'D2-',
  needs: { aging: true },
  setup: ({ ctx, responses }) => useD2DisclosureNote({
    allResponses: ref(responses),
    wpId: ref(ctx.wpId),
    projectId: ref(ctx.projectId),
    variant: ctx.variant,
    save: () => {},
    isReadonly: ref(false),
  }),
  prepare: (note, { ctx }) => seedD2SyncBaseline(note, ctx),
  build: (note, { ctx }) => buildD2SyncPayload(ctx.variant, ctx.wpId, ctx.applicableStandards, note.buildSnapshot()),
})
