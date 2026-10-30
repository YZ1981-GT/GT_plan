/**
 * I4 长期待摊费用披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：`useI4Disclosure`（由 checklist 响应现算披露行）→ 同一个 `buildSyncPayloads`
 * （Tab 的 `syncToNotes` 也调它：快照 + 本版本 builder）。Tab 打开时只读已存披露行（「从 I4-2 同步」是按钮、
 * 审定事件只在 Tab 打开时监听），离屏同样不取数；Tab 在披露期末与 I4-2 明细有差额时先确认再同步，离屏没有
 * 确认框，按确认后的同一载荷写入。保存回调为空（离屏不改底稿）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useI4Disclosure } from './useI4Disclosure'

export const i4HeadlessProvider = defineHeadlessProvider({
  prefix: 'I4-',
  setup: ({ ctx, responses }) => useI4Disclosure(ref(ctx.wpId), ref(ctx.projectId), ref(responses), {
    variant: ctx.variant,
    applicableStandards: () => ctx.applicableStandards,
    onSave: () => {},
  }),
  build: (disc) => disc.buildSyncPayloads(),
})
