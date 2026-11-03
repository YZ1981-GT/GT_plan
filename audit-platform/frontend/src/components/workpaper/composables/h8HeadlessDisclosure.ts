/**
 * H8 使用权资产披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：Tab 挂载即由 `useH8ListedDisclosure` / `useH8SoeDisclosure` 从 checklist 响应现算披露表
 * （immediate watcher，只读本底稿 `H8-listed-*` / `H8-soe-*` 键；外壳注入的 TB 核对种子与明细预填只供「从 H8-1/H8-2 带入」按钮用，
 * 挂载时不读），「同步到附注」以同一个快照函数 `h8ListedSyncSnapshot` / `h8SoeSyncSnapshot` 调同一个 builder。
 * 保存回调为空（离屏不改底稿）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { h8ListedSyncSnapshot, h8SoeSyncSnapshot, useH8ListedDisclosure, useH8SoeDisclosure } from './useH8Disclosure'
import { buildH8ListedSyncPayloads, buildH8SoeSyncPayloads } from './h8DisclosureSyncPayload'

export const h8HeadlessProvider = defineHeadlessProvider({
  prefix: 'H8-',
  setup: ({ ctx, responses }) => {
    const allResponses = ref(responses)
    return ctx.variant === 'listed'
      ? { variant: 'listed' as const, note: useH8ListedDisclosure({ allResponses, onSave: () => {} }) }
      : { variant: 'soe' as const, note: useH8SoeDisclosure({ allResponses, onSave: () => {} }) }
  },
  build: (inst, { ctx }) => (inst.variant === 'listed'
    ? buildH8ListedSyncPayloads(ctx.wpId, ctx.applicableStandards, h8ListedSyncSnapshot(inst.note))
    : buildH8SoeSyncPayloads(ctx.wpId, ctx.applicableStandards, h8SoeSyncSnapshot(inst.note))),
})
