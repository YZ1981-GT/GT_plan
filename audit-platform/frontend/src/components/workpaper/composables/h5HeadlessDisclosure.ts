/**
 * H5 油气资产披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 只有国企口径（八、25）；上市准则下油气资产不单独设附注章节 ⇒ 上市回空。与国企披露 Tab 同一套代码：
 * 汇总四行 `buildH5SoeSummaryRows`（审定事件只在 Tab 挂载期间才有，离屏按 H5-1 明细审定数合计，即 Tab 刚打开时的口径）
 * → 全 0 不同步（`h5SoeSummaryIsEmpty`）→ `h5SoeLayerTotals` + 已保存的补充披露文本 → `buildH5SyncPayload`（年度取附注页年度）。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildH5SyncPayload } from './h5NoteSectionMap'
import {
  buildH5SoeSummaryRows,
  h5SoeLayerTotals,
  h5SoeSummaryIsEmpty,
  readH5SoeDisclosureText,
} from './h5SoeDisclosureForm'

export const h5HeadlessProvider = defineHeadlessProvider({
  prefix: 'H5-',
  setup: ({ responses }) => ({
    rows: buildH5SoeSummaryRows(null, responses),
    text: readH5SoeDisclosureText(responses),
  }),
  build: ({ rows, text }, { ctx }) => {
    if (ctx.variant !== 'soe' || h5SoeSummaryIsEmpty(rows)) return null
    return buildH5SyncPayload({
      wpId: ctx.wpId,
      projectId: ctx.projectId,
      year: ctx.year,
      layerTotals: h5SoeLayerTotals(rows),
      soeDisclosureText: text,
    })
  },
})
