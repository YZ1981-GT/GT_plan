/**
 * G1 交易性金融资产披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码（保存回调为空 —— 离屏不改底稿）：
 * - 国企：`useG1DisclosureSoe` → 首次进入的初始化 `initFromResponses`（无已存明细时按 G1-1 审定表灌数，与 Tab 挂载同一步）
 *   → `getSyncSnapshot` → `buildG1SoeSyncPayloads`：一次两个章节（八、2 交易性金融资产 / 八、3 衍生金融资产），逐章节发送、
 *   逐章节回报；
 * - 上市：`useG1DisclosureListed` → `buildG1ListedSubTableData(getSyncSnapshot())` → `buildG1SyncPayload('listed', …)`（五、2）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useG1DisclosureSoe } from './useG1DisclosureSoe'
import { useG1DisclosureListed } from './useG1DisclosureListed'
import { buildG1ListedSubTableData, buildG1SoeSyncPayloads, buildG1SyncPayload } from './g1DisclosureSyncPayload'

type G1HeadlessInstance =
  | { variant: 'soe'; dis: ReturnType<typeof useG1DisclosureSoe> }
  | { variant: 'listed'; dis: ReturnType<typeof useG1DisclosureListed> }

export const g1HeadlessProvider = defineHeadlessProvider<G1HeadlessInstance>({
  prefix: 'G1-',
  setup: ({ ctx, responses }) => {
    const opts = { allResponses: ref(responses), debouncedSave: () => {}, isReadonly: ref(false) }
    return ctx.variant === 'soe'
      ? { variant: 'soe', dis: useG1DisclosureSoe(opts) }
      : { variant: 'listed', dis: useG1DisclosureListed(opts) }
  },
  prepare: (inst) => {
    if (inst.variant === 'soe') inst.dis.initFromResponses()
  },
  build: (inst, { ctx }) => (inst.variant === 'soe'
    ? buildG1SoeSyncPayloads(ctx.wpId, ctx.applicableStandards, inst.dis.getSyncSnapshot())
    : buildG1SyncPayload('listed', ctx.wpId, ctx.applicableStandards, buildG1ListedSubTableData(inst.dis.getSyncSnapshot()))),
})
