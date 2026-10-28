/**
 * F2 存货披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：上市 `useF2DisclosureListed` / 国企 `useF2DisclosureSoe`（由 F2-1 审定表等 checklist 响应
 * 现算各表，参数照 Tab 传）→ 同一个快照 `getSyncSnapshot` → 同一个子表 builder（上市 `buildF2ListedSubTableData` /
 * 国企 `buildF2SoeSubTableData`）→ 同一个 `buildF2SyncPayload`（口径不适用回 null ⇒ 本口径没有章节）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useF2DisclosureListed } from './useF2DisclosureListed'
import { useF2DisclosureSoe } from './useF2DisclosureSoe'
import {
  buildF2ListedSubTableData,
  buildF2SoeSubTableData,
  buildF2SyncPayload,
} from './f2DisclosureSyncPayload'

export const f2HeadlessProvider = defineHeadlessProvider({
  // 与主入口 useF2FormData 同口径（`F2-note-` 已含在 `F2-` 里）
  prefix: ['F2-', 'F2A'],
  setup: ({ ctx, responses }) => {
    const options = {
      allResponses: ref(responses),
      isReadonly: ref(false),
      applicableStandards: ref([...ctx.applicableStandards]),
    }
    return ctx.variant === 'listed'
      ? { variant: 'listed' as const, disclosure: useF2DisclosureListed(options) }
      : { variant: 'soe' as const, disclosure: useF2DisclosureSoe(options) }
  },
  build: (instance, { ctx }) => buildF2SyncPayload(
    instance.variant,
    ctx.wpId,
    ctx.applicableStandards,
    instance.variant === 'listed'
      ? buildF2ListedSubTableData(instance.disclosure.getSyncSnapshot())
      : buildF2SoeSubTableData(instance.disclosure.getSyncSnapshot()),
  ),
})
