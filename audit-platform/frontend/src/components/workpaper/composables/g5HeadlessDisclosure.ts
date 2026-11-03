/**
 * G5 长期应收款披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码（保存回调为空 —— 离屏不改底稿）：`useG5DisclosureListed` / `useG5DisclosureSoe` →
 * Tab 挂载时的 `loadPersisted` → 同一个快照 / 载荷函数（`g5DisclosureTabSync`，由两个 Tab 原样抽出）：
 * - 上市 五、16：组合计提表按「上次同步成功推送的表名」清理旧组合表；离屏不记账，下次照同一基线再算；
 * - 国企 八、17：性质 / 终止确认 / 继续涉入 3 张表。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useG5DisclosureListed } from './useG5DisclosureListed'
import { useG5DisclosureSoe } from './useG5DisclosureSoe'
import { buildG5ListedTabSyncPayload, buildG5SoeTabSyncPayload } from './g5DisclosureTabSync'

type G5HeadlessInstance =
  | { variant: 'soe'; dis: ReturnType<typeof useG5DisclosureSoe> }
  | { variant: 'listed'; dis: ReturnType<typeof useG5DisclosureListed> }

export const g5HeadlessProvider = defineHeadlessProvider<G5HeadlessInstance>({
  prefix: 'G5-',
  setup: ({ ctx, responses }) => {
    const opts = { allResponses: ref(responses), debouncedSave: () => {}, isReadonly: ref(false) }
    return ctx.variant === 'soe'
      ? { variant: 'soe', dis: useG5DisclosureSoe(opts) }
      : { variant: 'listed', dis: useG5DisclosureListed(opts) }
  },
  prepare: (inst) => inst.dis.loadPersisted(),
  build: (inst, { ctx, responses }) => (inst.variant === 'soe'
    ? buildG5SoeTabSyncPayload(ctx.wpId, ctx.applicableStandards, inst.dis)
    : buildG5ListedTabSyncPayload(ctx.wpId, ctx.applicableStandards, inst.dis, responses).payload),
})
