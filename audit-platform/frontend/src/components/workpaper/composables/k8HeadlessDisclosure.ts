/**
 * K8 销售费用披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：Tab onMounted 的「读已保存行（无保存时按 K8-1 审定表项目建行 / 默认清单）→ 按 K8-1 回填并追加
 * 新费用项目」（`loadK8DisclosureState` + `applyK8AutoFill`）→ 同步按钮的明细行 `k8DisclosureSyncRows` → 同一个
 * `buildK8SyncPayload`。Tab 自动取数后会保存披露行，离屏只改内存（不写底稿）；行身份不进载荷。
 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildK8SyncPayload } from './k8NoteSectionMap'
import {
  applyK8AutoFill,
  K8_HEADLESS_ROW_IDENTITY,
  k8DisclosureSyncRows,
  loadK8DisclosureState,
  readK81AuditedMap,
} from './k8DisclosureSnapshot'

export const k8HeadlessProvider = defineHeadlessProvider({
  // 与宿主 GtK8SellingExpenses 的条目口径一致（K8-{sheet}-{field}）
  prefix: 'K8-',
  setup: ({ ctx, responses }) => loadK8DisclosureState(responses, ctx.variant, K8_HEADLESS_ROW_IDENTITY),
  prepare: (state, { ctx, responses }) =>
    applyK8AutoFill(readK81AuditedMap(responses), state.rows, ctx.variant, K8_HEADLESS_ROW_IDENTITY),
  build: (state, { ctx }) =>
    buildK8SyncPayload(ctx.variant, ctx.wpId, k8DisclosureSyncRows(state.rows), state.narrativeText),
})
