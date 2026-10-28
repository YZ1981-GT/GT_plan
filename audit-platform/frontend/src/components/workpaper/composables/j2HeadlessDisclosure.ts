/**
 * J2 长期应付职工薪酬披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（上市 `J2TabDisclosureListed` 五、49 / 国企 `J2TabDisclosureSoe` 八、54）同一套代码（`j2DisclosureTabState`）：
 * Tab 挂载时的 `load`（读回已保存的各区块，国企还原动态行；汇总表全 0 时按 J2-1 审定表带数）→「同步到附注」同一个
 * `syncRequests`（上市净负债期末为负另推 五、17）。年度取本次刷新的审计年度（Tab 取审计上下文的同一个年度）。
 * 离屏不写底稿、不弹提示、不调 AI、不订阅事件。
 */
import {
  defineHeadlessProvider,
  type HeadlessSyncPayload,
} from '@/components/workpaper/headless/headlessFramework'
import { useJ2ListedDisclosureState, useJ2SoeDisclosureState } from './j2DisclosureTabState'

export const j2HeadlessProvider = defineHeadlessProvider({
  // 宿主 GtJ2DefinedBenefitPlan 取本底稿全部回复；披露 Tab 只读 J2-listed-* / J2-soe-* / J2-1-main
  prefix: 'J2-',
  setup: ({ ctx }) => (ctx.variant === 'listed' ? useJ2ListedDisclosureState() : useJ2SoeDisclosureState()),
  // Tab onMounted：load()
  prepare: (state, { responses }) => state.load(responses),
  build: (state, { ctx }) => state.syncRequests(ctx.wpId, ctx.year) as unknown as HeadlessSyncPayload[],
})
