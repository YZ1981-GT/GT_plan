/**
 * G10 交易性金融负债披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（`G10TabDisclosureBase`，上市 / 国企两个薄壳共用）同一套代码：`useG10Disclosure`（已存变动表 / 余额表 / 指定明细 /
 * 信用风险拆分 / 衍生负债，立即读）+ Tab 挂载时读的审计说明 `readG10DisclosureAuditNote` → 同一个 `buildG10TabSyncPayloads`
 * （上市 五、34，有衍生负债数据时另发 五、35；国企 八、34，逐章节回报）。
 *
 * 审计年度（列头「{年度}年度…」与按年度拼的旧表名清理都用它）在 Tab 里由 Runtime Boundary 注入，离屏没有组件实例、inject 不到，
 * 由 `ctx.year` 显式传入。Tab 挂载时只读审定数、订阅窗口事件（都不进载荷），离屏不挂钩子，所以没有 prepare；保存回调为空。
 * 前缀与底稿主入口 `useG10FormData` 同口径（`G10`）。
 */
import { computed, ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useG10Disclosure } from './useG10Disclosure'
import { buildG10TabSyncPayloads, readG10DisclosureAuditNote } from './g10DisclosureSyncPayload'

export const g10HeadlessProvider = defineHeadlessProvider({
  prefix: 'G10',
  setup: ({ ctx, responses }) => useG10Disclosure({
    variant: ctx.variant,
    allResponses: ref(responses),
    debouncedSave: () => {},
    wpId: ref(ctx.wpId),
    projectId: computed(() => ctx.projectId),
    isReadonly: ref(false),
    auditYear: ref<number | null>(ctx.year),
  }),
  build: (dis, { ctx, responses }) => buildG10TabSyncPayloads(
    ctx.wpId, ctx.variant, ctx.applicableStandards, dis, readG10DisclosureAuditNote(responses, ctx.variant),
  ),
})
