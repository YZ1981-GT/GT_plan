/**
 * K2 其他流动资产披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（上市 `K2TabDisclosureListed` / 国企 `K2TabDisclosureSoe`）同一套代码：初值
 * `createK2ListedDisclosureState` / `k2SoeDefaultMainRows` → Tab onMounted 的读回 `loadK2ListedDisclosureState` /
 * `loadK2SoeDisclosureState` → 同步快照 `buildK2ListedDisclosureSnapshot` / `buildK2SoeDisclosureSnapshot` → 同一个
 * `buildK2SyncPayload`（上市 五、13 / 国企 八、14）。Tab 挂载时只读回已存表单、不取数、不写底稿，离屏同样。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildK2SyncPayload } from './k2NoteSectionMap'
import {
  buildK2ListedDisclosureSnapshot,
  buildK2SoeDisclosureSnapshot,
  createK2ListedDisclosureState,
  k2SoeDefaultMainRows,
  loadK2ListedDisclosureState,
  loadK2SoeDisclosureState,
  type K2DisclosureMainRow,
  type K2ListedDisclosureState,
} from './k2DisclosureTabState'

type K2HeadlessState =
  | { variant: 'listed'; listed: K2ListedDisclosureState }
  | { variant: 'soe'; mainRows: K2DisclosureMainRow[]; noteText: string }

export const k2HeadlessProvider = defineHeadlessProvider<K2HeadlessState>({
  // 与宿主的条目口径一致（K2-{sheet}-{field}）
  prefix: 'K2-',
  setup: ({ ctx }) => (ctx.variant === 'listed'
    ? { variant: 'listed', listed: createK2ListedDisclosureState() }
    : { variant: 'soe', mainRows: k2SoeDefaultMainRows(), noteText: '' }),
  // Tab onMounted：loadSavedData()
  prepare: (state, { responses }) => {
    if (state.variant === 'listed') {
      loadK2ListedDisclosureState(responses, state.listed)
      return
    }
    const savedText = loadK2SoeDisclosureState(responses, state.mainRows)
    if (savedText != null) state.noteText = savedText
  },
  build: (state, { ctx }) => (state.variant === 'listed'
    ? buildK2SyncPayload('listed', ctx.wpId, buildK2ListedDisclosureSnapshot(state.listed))
    : buildK2SyncPayload('soe', ctx.wpId, buildK2SoeDisclosureSnapshot(state.mainRows, state.noteText))),
})
