/**
 * G2 应收利息披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码（保存回调为空 —— 离屏不改底稿）：`useG2DisclosureSoe` / `useG2DisclosureListed` →
 * 首次进入的初始化 `initFromResponses`（无已存披露行时按 G2-1 审定表 / G2-2 明细灌数，与 Tab 挂载同一步）→
 * `getSyncSnapshot` → `buildG2SoeSyncPayloads` / `buildG2ListedSyncPayloads`（国企 八、9 / 上市 五、8，与 G3、K1 共用章节，
 * 后端按子表名浅合并）。Tab 的「从 G2-6 取数」确认框等界面行为不在这里。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useG2DisclosureSoe } from './useG2DisclosureSoe'
import { useG2DisclosureListed } from './useG2DisclosureListed'
import { buildG2ListedSyncPayloads, buildG2SoeSyncPayloads } from './g2DisclosureSyncPayload'

type G2HeadlessInstance =
  | { variant: 'soe'; dis: ReturnType<typeof useG2DisclosureSoe> }
  | { variant: 'listed'; dis: ReturnType<typeof useG2DisclosureListed> }

export const g2HeadlessProvider = defineHeadlessProvider<G2HeadlessInstance>({
  prefix: 'G2-',
  setup: ({ ctx, responses }) => {
    const opts = { allResponses: ref(responses), debouncedSave: () => {}, isReadonly: ref(false) }
    return ctx.variant === 'soe'
      ? { variant: 'soe', dis: useG2DisclosureSoe(opts) }
      : { variant: 'listed', dis: useG2DisclosureListed(opts) }
  },
  prepare: (inst) => inst.dis.initFromResponses(),
  build: (inst, { ctx }) => (inst.variant === 'soe'
    ? buildG2SoeSyncPayloads(ctx.wpId, ctx.applicableStandards, inst.dis.getSyncSnapshot())
    : buildG2ListedSyncPayloads(ctx.wpId, ctx.applicableStandards, inst.dis.getSyncSnapshot())),
})
