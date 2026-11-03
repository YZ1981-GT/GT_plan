/**
 * I5 其他非流动资产披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：`useI5Disclosure`（由 checklist 响应现算披露行，含旧矩阵键迁移读）→ 同一个
 * `buildSyncPayloads`（Tab 的 `syncToNotes` 也调它：快照 + 本版本 builder）。Tab 打开时只读已存披露行
 * （「从 I5-2 同步」是按钮），离屏同样不取数；与 I5-2 明细有差额时 Tab 先确认，离屏按确认后的同一载荷写入。
 * 保存回调为空（离屏不改底稿）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useI5Disclosure } from './useI5Disclosure'

export const i5HeadlessProvider = defineHeadlessProvider({
  prefix: 'I5-',
  setup: ({ ctx, responses }) => useI5Disclosure(ref(ctx.wpId), ref(ctx.projectId), ref(responses), {
    variant: ctx.variant,
    applicableStandards: () => ctx.applicableStandards,
    onSave: () => {},
  }),
  build: (disc) => disc.buildSyncPayloads(),
})
