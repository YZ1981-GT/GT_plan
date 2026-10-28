/**
 * N5 所得税费用披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（`N5DisclosureBody`，两版共用）同一套代码：`useN5DisclosureTables`（Tab 在 onMounted 里 loadData 后
 * `restore()`）→ 同一个 `buildPayload`（快照 + `buildN5SyncPayload`，ctx 同样只带 wpId / year）。已同步表名只读不写。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useN5DisclosureTables } from './useN5DisclosureTables'

export const n5HeadlessProvider = defineHeadlessProvider({
  // 与 useN5FormData.loadResponses 同口径
  prefix: 'N5-',
  setup: ({ ctx, responses }) => useN5DisclosureTables({ variant: ctx.variant, allResponses: ref(responses) }),
  prepare: (tables) => tables.restore(),
  build: (tables, { ctx }) => tables.buildPayload({ wpId: ctx.wpId, year: ctx.year }),
})
