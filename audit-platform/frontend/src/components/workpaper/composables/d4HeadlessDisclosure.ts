/**
 * D4 营业收入 / 营业成本披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与两版底稿披露 Tab 同一套代码：Tab 同款 `useD4Disclosure`（审计年度显式传入 —— 离屏没有组件实例，inject 不到主入口
 * 提供的年度）→ Tab 挂载时同一步首载刷新 `initialRefresh()`（没有试算表缓存时取一次收入 / 成本审定数、从 D4-2 / D4-3
 * 带入分产品行；保存回调为空 ⇒ 只改内存，不写底稿）→ 同一个快照函数 `buildD4DisclosureSnapshot` →
 * 同一个 `buildD4SyncPayload`（适用准则照 Tab 传 null）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useD4Disclosure } from './useD4Disclosure'
import { buildD4SyncPayload } from './d4NoteSectionMap'
import { buildD4DisclosureSnapshot, readD4Section6Rows } from './d4DisclosureSnapshot'

export const d4HeadlessProvider = defineHeadlessProvider({
  prefix: 'D4-',
  setup: ({ ctx, responses }) => useD4Disclosure({
    allResponses: ref(responses),
    wpId: ref(ctx.wpId),
    projectId: ref(ctx.projectId),
    variant: ctx.variant,
    saveBatch: () => {},
    isReadonly: ref(false),
    auditYear: ref<number | null>(ctx.year),
  }),
  prepare: (d4) => d4.initialRefresh(),
  build: (d4, { ctx, responses }) => buildD4SyncPayload(ctx.variant, ctx.wpId, null, buildD4DisclosureSnapshot(d4, {
    section6Rows: readD4Section6Rows(responses, ctx.variant),
    auditYear: ctx.year,
  })),
})
