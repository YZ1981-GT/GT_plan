/**
 * F4 应付账款披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：上市 `useF4DisclosureListed` / 国企 `useF4DisclosureSOE`（由 checklist 响应现算两张表 +
 * 披露正文，参数照 Tab 传，适用准则同样传 getter）→ 同一个 `buildSyncPayload`（Tab 的 `syncToNotes` 发的就是它；
 * 这里不调 `syncToNotes`，那里有提示）。国企账龄段按项目账龄配置（主入口 provide 的同一份配置，离屏由框架预取进缓存）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useF4DisclosureListed } from './useF4DisclosureListed'
import { useF4DisclosureSOE } from './useF4DisclosureSOE'

export const f4HeadlessProvider = defineHeadlessProvider({
  // 与主入口 useF4FormData 同口径（`F4-note-` 已含在 `F4-` 里）
  prefix: ['F4-', 'F4A'],
  needs: { aging: true },
  setup: ({ ctx, responses }) => {
    const options = {
      wpId: ref(ctx.wpId),
      projectId: ref(ctx.projectId),
      allResponses: ref(responses),
      isReadonly: ref(false),
      applicableStandards: () => ctx.applicableStandards,
    }
    return ctx.variant === 'listed' ? useF4DisclosureListed(options) : useF4DisclosureSOE(options)
  },
  build: (disclosure) => disclosure.buildSyncPayload(),
})
