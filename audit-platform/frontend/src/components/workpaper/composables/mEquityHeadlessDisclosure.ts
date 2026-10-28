/**
 * M 循环权益类「变动表」披露离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）：
 * M4 资本公积（上市 五、55 / 国企 八、60）、M5 盈余公积（五、59 / 八、62）、M7 专项储备（五、58 / 八、61）。
 *
 * 与底稿披露 Tab 同一套代码：Tab 的 `useM{n}FormData` 只负责取 / 存本底稿 `M{n}-` 回复（框架按同一前缀取，离屏不存），
 * 表格与说明由 `mEquityDisclosureForm` 的默认行 + 读回（Tab onMounted / 审定刷新同一函数）得到 → 同一个快照 +
 * `buildMEquitySyncPayload`（`buildMEquityTabSyncPayload`，Tab 的同步函数调的也是它）。
 *
 * 口径：Tab 由外壳按披露 sheet 分发（上市 / 国企各一个），离屏按项目口径选同一份表格声明；Tab 不传适用准则给 builder，
 * 这里同样不传（载荷逐字节相同）。各编码章节独占，载荷不带 `_removed_table_keys`。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import {
  applyM7AutoFill,
  buildM7TabSyncPayload,
  buildM8TabSyncPayload,
  buildMEquityTabSyncPayload,
  createM7ListedDisclosureRows,
  createM7SoeDisclosureRows,
  createM8DisclosureRows,
  loadMEquityDisclosure,
  M4_DISCLOSURE_FORM,
  M5_DISCLOSURE_FORM,
  M7_AUTO_FILL_SOURCES,
  readM8FieldValue,
  restoreM7Disclosure,
  restoreM8Disclosure,
} from './mEquityDisclosureForm'
import { readNoteAutoFillValues } from './useNoteAutoFill'

export const m4HeadlessProvider = defineHeadlessProvider({
  // 与 useM4FormData 的 ITEM_PREFIX 同口径
  prefix: 'M4-',
  setup: ({ ctx, responses }) => loadMEquityDisclosure(responses, M4_DISCLOSURE_FORM[ctx.variant]),
  build: (state, { ctx }) => buildMEquityTabSyncPayload(ctx.wpId, M4_DISCLOSURE_FORM[ctx.variant], state),
})

/**
 * M7 专项储备（上市 五、58 / 国企 八、61 带备注列）：Tab 挂载 = 默认四行 → 读回原因 / 计提依据与说明 → useNoteAutoFill
 * 按 M7-1 小计改期末；离屏用同一个取数函数 `readNoteAutoFillValues`（不实例化 useNoteAutoFill：它订阅审定 / 试算表事件）。
 */
export const m7HeadlessProvider = defineHeadlessProvider({
  // 与 useM7FormData 的 ITEM_PREFIX 同口径
  prefix: 'M7-',
  setup: ({ ctx, responses }) => {
    const rows = ctx.variant === 'listed' ? createM7ListedDisclosureRows() : createM7SoeDisclosureRows()
    const note = restoreM7Disclosure(responses, ctx.variant, rows) ?? ''
    applyM7AutoFill(rows, readNoteAutoFillValues(responses, M7_AUTO_FILL_SOURCES).values)
    return { rows, note }
  },
  build: (state, { ctx }) => buildM7TabSyncPayload(ctx.wpId, ctx.variant, state.rows, state.note),
})

/**
 * M8 一般风险准备（上市 五、60 / 国企 八、94）：Tab 挂载 = 默认三行 → 逐格读回 + 期初为 0 时取 M8-2 明细期初合计
 * （同一个 `readM8FieldValue`，即 useM8FormData.getField 的取值口径）+ 说明 → 同一个载荷函数。
 */
export const m8HeadlessProvider = defineHeadlessProvider({
  // 与 useM8FormData 的 ITEM_PREFIX 同口径
  prefix: 'M8-',
  setup: ({ ctx, responses }) => {
    const rows = createM8DisclosureRows()
    const { note } = restoreM8Disclosure(responses, ctx.variant, rows, readM8FieldValue(responses.get('M8-2-total-beginBalance')))
    return { rows, note: note ?? '' }
  },
  build: (state, { ctx }) => buildM8TabSyncPayload(ctx.wpId, ctx.variant, state.rows, state.note),
})

/** M5 盈余公积（上市 五、59 / 国企 八、62；国企多一段「国有企业专项披露」说明） */
export const m5HeadlessProvider = defineHeadlessProvider({
  // 与 useM5FormData 的 ITEM_PREFIX 同口径
  prefix: 'M5-',
  setup: ({ ctx, responses }) => loadMEquityDisclosure(responses, M5_DISCLOSURE_FORM[ctx.variant]),
  build: (state, { ctx }) => buildMEquityTabSyncPayload(ctx.wpId, M5_DISCLOSURE_FORM[ctx.variant], state),
})
