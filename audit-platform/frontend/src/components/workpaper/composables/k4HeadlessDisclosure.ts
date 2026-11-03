/**
 * K4 其他流动负债披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（上市 `K4TabDisclosureListed` / 国企 `K4TabDisclosureSoe`）同一套代码：Tab 的表单初值
 * （`createK4ListedSummaryRows` / `createK4SoeDisclosureSections`）→ Tab onMounted 的 loadSavedData + applyAutoFill
 * （`loadK4ListedDisclosureState` + `applyK4ListedAutoFill` / `loadK4SoeDisclosureState` + `applyK4SoeAutoFill`，只改内存）→
 * 「同步到附注」同一个快照（`buildK4ListedDisclosureSnapshot` / `buildK4SoeDisclosureSnapshot`）→ 同一个 `buildK4SyncPayload`
 * （上市 五、44 / 国企 八、48；builder 不判口径，Tab 也不判）。离屏不写底稿、不订阅审定事件、不触发 AI / 提示。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildK4SyncPayload } from './k4NoteSectionMap'
import {
  applyK4ListedAutoFill,
  applyK4SoeAutoFill,
  buildK4ListedDisclosureSnapshot,
  buildK4SoeDisclosureSnapshot,
  createK4ListedSummaryRows,
  createK4SoeDisclosureSections,
  loadK4ListedDisclosureState,
  loadK4SoeDisclosureState,
  type K4ListedBondContRow,
  type K4ListedBondRow,
  type K4ListedSummaryRow,
  type K4SoeDisclosureSection,
} from './k4DisclosureTabState'

/** 上市：汇总表 + 两张债券条件表 + 说明（政府补助表不进载荷）；国企：四段 */
type K4HeadlessState =
  | {
      variant: 'listed'
      summaryRows: K4ListedSummaryRow[]
      bondRows: K4ListedBondRow[]
      bondContRows: K4ListedBondContRow[]
      noteText: string
    }
  | { variant: 'soe'; sections: K4SoeDisclosureSection[] }

export const k4HeadlessProvider = defineHeadlessProvider<K4HeadlessState>({
  // 与宿主 GtK4OtherCurrentLiabilities 的条目口径一致（K4-{sheet}-{field}）
  prefix: 'K4-',
  setup: ({ ctx }) => (ctx.variant === 'soe'
    ? { variant: 'soe', sections: createK4SoeDisclosureSections() }
    : { variant: 'listed', summaryRows: createK4ListedSummaryRows(), bondRows: [], bondContRows: [], noteText: '' }),
  // Tab onMounted：loadSavedData() → applyAutoFill()
  prepare: (state, { responses }) => {
    if (state.variant === 'soe') {
      loadK4SoeDisclosureState(responses, state.sections)
      applyK4SoeAutoFill(responses, state.sections)
      return
    }
    const saved = loadK4ListedDisclosureState(responses, state.summaryRows)
    if (saved.bondRows) state.bondRows = saved.bondRows
    if (saved.bondContRows) state.bondContRows = saved.bondContRows
    state.noteText = saved.noteText
    applyK4ListedAutoFill(responses, state.summaryRows)
  },
  build: (state, { ctx }) => {
    if (state.variant === 'soe') {
      const snapshot = buildK4SoeDisclosureSnapshot(state.sections)
      return buildK4SyncPayload('soe', ctx.wpId, snapshot.rows, snapshot.narrative)
    }
    const snapshot = buildK4ListedDisclosureSnapshot(state)
    return buildK4SyncPayload('listed', ctx.wpId, snapshot.rows, snapshot.narrative, snapshot.extras)
  },
})
