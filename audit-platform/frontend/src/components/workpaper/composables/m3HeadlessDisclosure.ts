/**
 * M3 库存股披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：Tab 的 `useM3FormData` 只负责取 / 存本底稿 `M3-` 回复（框架按同一前缀取，离屏不存），
 * 表格与三段说明由 `m3DisclosureForm` 的默认状态 + 读回（Tab onMounted 同一函数，含期末重算）得到 → 同一个快照 +
 * `buildM3SyncPayload`（上市 五、56）。「从审定表 / 明细表带入」是 Tab 上的用户按钮（含覆盖确认），离屏不做。
 *
 * 只有上市口径有章节：国企附注模板没有库存股章节（`note_template_variant_matrix` 的 ku_cun_gu.soe_* 为 null，
 * 注册表 M3 只有上市 sheet），国企项目回空（不写）。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildM3TabSyncPayload, loadM3TreasuryDisclosure } from './m3DisclosureForm'

export const m3HeadlessProvider = defineHeadlessProvider({
  // 与 useM3FormData 的 ITEM_PREFIX 同口径
  prefix: 'M3-',
  setup: ({ responses }) => loadM3TreasuryDisclosure(responses),
  build: (state, { ctx }) => (ctx.variant === 'listed' ? buildM3TabSyncPayload(ctx.wpId, state) : null),
})
