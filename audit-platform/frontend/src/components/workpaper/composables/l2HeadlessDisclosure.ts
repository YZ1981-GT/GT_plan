/**
 * L2 应付利息披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：Tab 由 `useL2FormData.loadData()` 读本底稿 L2- 回复（与框架同口径），`useL2Disclosure`
 * 从 L2-2 明细按类别聚合分类表与逾期表 → `buildL2DisclosureSnapshot` → `buildL2SyncPayload` → `buildL2SyncRequestBody`
 * （Tab 的同步函数走同样三步）。只读计算，不写底稿。
 *
 * 写入章节与 K3 / M1 共用（五、42 / 八、42）：只推「应付利息」+ 逾期利息两张子表，载荷不带 `_removed_table_keys`。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useL2Disclosure } from './useL2Disclosure'
import { buildL2SyncPayload } from './l2NoteSectionMap'
import { buildL2DisclosureSnapshot, buildL2SyncRequestBody } from './l2DisclosureSync'

export const l2HeadlessProvider = defineHeadlessProvider({
  // 与 useL2FormData.loadResponses 同前缀（L2-{sheet}-{field}）
  prefix: 'L2-',
  setup: ({ responses }) => useL2Disclosure(ref(responses)),
  build: (disclosure, { ctx }) => {
    const snap = buildL2DisclosureSnapshot(disclosure.disclosureTableData.value, disclosure.overdueRows.value)
    return buildL2SyncRequestBody(ctx.variant, ctx.wpId, buildL2SyncPayload(ctx.variant, snap.interestRows, snap.overdueRows))
  },
})
