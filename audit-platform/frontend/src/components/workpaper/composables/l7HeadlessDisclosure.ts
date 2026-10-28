/**
 * L7 其他非流动负债披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（上市 `L7TabDisclosureListed` / 国企 `L7TabDisclosureSoe`）同一套代码：Tab 的默认行
 * （`createL7ListedDisclosureRows` / `createL7SoeDisclosureRows`）→ Tab onMounted 的 `loadData()` + restoreRows（Tab 自建
 * `useL7FormData` 读本底稿 L7- 回复，与框架同口径；读回走 `restoreL7ListedDisclosure` / `restoreL7SoeDisclosure`，只改内存）→
 * 「同步到附注」同一个快照（`buildL7ListedDisclosureSnapshot` / `buildL7SoeDisclosureSnapshot`）→ 同一个 `buildL7SyncPayload`
 * （上市 五、52 / 国企 八、57，一个章节；Tab 不传适用准则，builder 不判口径）。离屏不写底稿、不订阅审定事件、不触发 AI / 提示。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildL7SyncPayload } from './l7NoteSectionMap'
import {
  buildL7ListedDisclosureSnapshot,
  buildL7SoeDisclosureSnapshot,
  createL7ListedDisclosureRows,
  createL7SoeDisclosureRows,
  restoreL7ListedDisclosure,
  restoreL7SoeDisclosure,
  type L7ListedDisclosureRow,
  type L7SoeDisclosureRow,
} from './l7DisclosureTabState'

type L7HeadlessState =
  | { variant: 'listed'; rows: L7ListedDisclosureRow[] }
  | { variant: 'soe'; rows: L7SoeDisclosureRow[] }

export const l7HeadlessProvider = defineHeadlessProvider<L7HeadlessState>({
  // 与 useL7FormData.loadResponses 同前缀（L7-{sheet}-{field}）
  prefix: 'L7-',
  setup: ({ ctx }) => (ctx.variant === 'soe'
    ? { variant: 'soe', rows: createL7SoeDisclosureRows() }
    : { variant: 'listed', rows: createL7ListedDisclosureRows() }),
  // Tab onMounted：loadData() → restoreRows()（没有已存就保持默认行）
  prepare: (state, { responses }) => {
    if (state.variant === 'soe') {
      const restored = restoreL7SoeDisclosure(responses)
      if (restored.rows) state.rows = restored.rows
      return
    }
    const restored = restoreL7ListedDisclosure(responses)
    if (restored.rows) state.rows = restored.rows
  },
  build: (state, { ctx }) => buildL7SyncPayload(
    ctx.wpId,
    state.variant === 'soe' ? buildL7SoeDisclosureSnapshot(state.rows) : buildL7ListedDisclosureSnapshot(state.rows),
  ),
})
