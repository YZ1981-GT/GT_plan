/**
 * H9 租赁负债披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：Tab 挂载即由 `useH9ListedDisclosure` / `useH9SoeDisclosure` 从 checklist 响应现算披露表
 * （immediate watcher），「同步到附注」以 `state` 调 `buildH9ListedSyncPayloads` / `buildH9SoeSyncPayloads`。离屏按附注口径
 * 实例化对应 composable、调同一个 builder；保存回调为空（离屏不改底稿）。「从审定/明细取数」是按钮动作，挂载时不跑，离屏也不跑。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useH9ListedDisclosure, useH9SoeDisclosure } from './useH9Disclosure'
import { buildH9ListedSyncPayloads, buildH9SoeSyncPayloads } from './h9DisclosureSyncPayload'

export const h9HeadlessProvider = defineHeadlessProvider({
  prefix: 'H9-',
  setup: ({ ctx, responses }) => {
    const allResponses = ref(responses)
    return ctx.variant === 'listed'
      ? { variant: 'listed' as const, note: useH9ListedDisclosure({ allResponses, onSave: () => {} }) }
      : { variant: 'soe' as const, note: useH9SoeDisclosure({ allResponses, onSave: () => {} }) }
  },
  build: (inst, { ctx }) => (inst.variant === 'listed'
    ? buildH9ListedSyncPayloads(ctx.wpId, ctx.applicableStandards, inst.note.state.value)
    : buildH9SoeSyncPayloads(ctx.wpId, ctx.applicableStandards, inst.note.state.value)),
})
