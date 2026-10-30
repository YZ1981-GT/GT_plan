/**
 * N4 税金及附加披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：`useN4DisclosureTables`（Tab 在 onMounted 里 selfLoad 后 `restore()`）→ 同一个快照
 * `buildSnapshot` → 同一个 `buildN4SyncPayload`（Tab 的 `buildPayload` 就是这两步，ctx 同样只带 wpId / year）。
 * 国企版源模板不披露税金及附加，builder 恒回 null ⇒ 本口径没有章节。已同步表名只读不写（离屏不改底稿）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useN4DisclosureTables } from './useN4DisclosureTables'
import { buildN4SyncPayload } from './n4NoteSectionMap'

export const n4HeadlessProvider = defineHeadlessProvider({
  // 与 useN4FormData.selfLoad 同口径
  prefix: ['N4-', 'N4A-'],
  setup: ({ responses }) => useN4DisclosureTables({ allResponses: ref(responses) }),
  prepare: (tables) => tables.restore(),
  build: (tables, { ctx }) =>
    buildN4SyncPayload(ctx.variant, tables.buildSnapshot(), { wpId: ctx.wpId, year: ctx.year }),
})
