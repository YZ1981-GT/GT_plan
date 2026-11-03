/**
 * H7 生产性生物资产披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：Tab 挂载时 `loadOwn` 读本底稿 `H7-disc-*` 条目、`hydrate` 解析（`readH7ListedForm` /
 * `readH7SoeForm`），「同步到附注」以同一个快照函数（`h7ListedSyncSnapshot` / `h7SoeSyncSnapshot`）调
 * `buildH7ListedSyncPayloads` / `buildH7SoeSyncPayloads`。两段原在 Tab 组件内联，已抽到 `h7DisclosureForm.ts` 共用。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { h7ListedSyncSnapshot, h7SoeSyncSnapshot, readH7ListedForm, readH7SoeForm } from './h7DisclosureForm'
import { buildH7ListedSyncPayloads, buildH7SoeSyncPayloads } from './h7DisclosureSyncPayload'

export const h7HeadlessProvider = defineHeadlessProvider({
  prefix: 'H7-disc-',
  setup: ({ ctx, responses }) => (ctx.variant === 'listed'
    ? { variant: 'listed' as const, form: readH7ListedForm(responses) }
    : { variant: 'soe' as const, form: readH7SoeForm(responses) }),
  build: (inst, { ctx }) => (inst.variant === 'listed'
    ? buildH7ListedSyncPayloads(ctx.wpId, ctx.applicableStandards, h7ListedSyncSnapshot(inst.form))
    : buildH7SoeSyncPayloads(ctx.wpId, ctx.applicableStandards, h7SoeSyncSnapshot(inst.form))),
})
