/**
 * F3 应付票据披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：上市 `useF3DisclosureListed` / 国企 `useF3DisclosureSoe`（由 F3-1 审定表 + F3-2 明细按类别
 * 现算分类行，参数照 Tab 传）→ Tab「同步到附注」同一个载荷函数 `buildF3SyncPayloadFromDisclosure`。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useF3DisclosureListed } from './useF3DisclosureListed'
import { useF3DisclosureSoe } from './useF3DisclosureSoe'
import { buildF3SyncPayloadFromDisclosure } from './f3NoteSectionMap'

export const f3HeadlessProvider = defineHeadlessProvider({
  // 与主入口 useF3FormData 同口径（`F3-note-` 已含在 `F3-` 里）
  prefix: ['F3-', 'F3A'],
  setup: ({ ctx, responses }) => {
    const options = {
      allResponses: ref(responses),
      isReadonly: ref(false),
      applicableStandards: ref([...ctx.applicableStandards]),
    }
    return ctx.variant === 'listed' ? useF3DisclosureListed(options) : useF3DisclosureSoe(options)
  },
  build: (disclosure, { ctx }) =>
    buildF3SyncPayloadFromDisclosure(ctx.variant, ctx.wpId, ctx.applicableStandards, disclosure),
})
