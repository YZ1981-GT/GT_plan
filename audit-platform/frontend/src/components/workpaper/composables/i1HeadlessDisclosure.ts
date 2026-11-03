/**
 * I1 无形资产披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：上市 / 国企两版 Tab 各用 `useI1ListedDisclosure` / `useI1SoeDisclosure`（由 checklist
 * 响应现算披露表），同一个 `buildSyncSnapshot` → 同一个 `buildI1ListedSyncPayloads` / `buildI1SoeSyncPayloads`。
 * Tab 打开时只读已存披露数据（「从 I1-2/检查表取数」是按钮），离屏同样不取数；保存回调为空（离屏不改底稿，Tab 同步前的
 * 落库在离屏没有意义）。
 *
 * 同步前校验（`prepValidation`）：有阻断项（如期末账面价值为负）时 Tab 拒绝同步 ⇒ 离屏同样不写，逐章节回报原因；
 * 只有编制提示时 Tab 先确认再同步 ⇒ 离屏按确认后的同一载荷写入。受限资产段由 Tab 同步，不在离屏同步里。
 */
import { ref } from 'vue'
import { defineHeadlessProvider, postHeadlessSyncPayload } from '@/components/workpaper/headless/headlessFramework'
import { useI1ListedDisclosure, useI1SoeDisclosure } from './useI1Disclosure'
import { buildI1ListedSyncPayloads, buildI1SoeSyncPayloads } from './i1DisclosureSyncPayload'

export const i1HeadlessProvider = defineHeadlessProvider({
  prefix: 'I1-',
  setup: ({ ctx, responses }) => {
    const params = { allResponses: ref(responses), onSave: () => {} }
    return ctx.variant === 'listed'
      ? { variant: 'listed' as const, disc: useI1ListedDisclosure(params) }
      : { variant: 'soe' as const, disc: useI1SoeDisclosure(params) }
  },
  build: (inst, { ctx }) => (inst.variant === 'listed'
    ? buildI1ListedSyncPayloads(ctx.wpId, ctx.applicableStandards, inst.disc.buildSyncSnapshot())
    : buildI1SoeSyncPayloads(ctx.wpId, ctx.applicableStandards, inst.disc.buildSyncSnapshot())),
  post: async (inst, payload, { ctx }) => {
    const blocked = inst.disc.prepValidation.value.blocking[0]
    if (blocked) {
      return { section: payload.section_id, rows: 0, skipped: `底稿披露表校验未通过：${blocked}，未写入（请在底稿附注披露页修正后同步）` }
    }
    return postHeadlessSyncPayload(ctx.projectId, payload)
  },
})
