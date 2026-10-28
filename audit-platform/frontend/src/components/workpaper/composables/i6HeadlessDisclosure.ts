/**
 * I6 研发费用披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：`useI6Disclosure`（由 checklist 响应现算披露行）→ 同一个 `buildSyncPayloads`
 * （Tab 的 `syncToNotes` 也调它：快照 + 本版本 builder）。保存回调为空（离屏不改底稿）。
 *
 * 不跑「从 I6-2 静默刷新」：composable 监听 `I6-2-detail-rows` 的 watcher 不是 immediate，只在 Tab 已打开、
 * 明细又变化时才跑；外壳 `GtI6ResearchDevelopmentExpense` 在回复加载完之后才挂披露 Tab（`isLoading` 门），
 * I6-2 又在另一个 sheet 编辑 ⇒ Tab 打开时看到的就是已存披露行，离屏同此（`i6HeadlessDisclosure.spec.ts`
 * 钉住 watcher 仍非 immediate）。勾稽 / 分项差异时 Tab 先确认，离屏按确认后的同一载荷写入。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useI6Disclosure } from './useI6Disclosure'

export const i6HeadlessProvider = defineHeadlessProvider({
  prefix: 'I6-',
  setup: ({ ctx, responses }) => useI6Disclosure(ref(ctx.wpId), ref(ctx.projectId), ref(responses), {
    variant: ctx.variant,
    applicableStandards: () => ctx.applicableStandards,
    onSave: () => {},
  }),
  build: (disc) => disc.buildSyncPayloads(),
})
