/**
 * G11 投资收益披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（`G11TabDisclosureBase`，上市 / 国企两个薄壳共用）同一套代码：`useG11Disclosure`（已存构成表 / 处置交易性子表 /
 * 汇回限制说明 / 附注文本，立即读）+ Tab 挂载时读的审计说明与结论 `readG11DisclosureAuditTexts` → 同一个 `buildG11TabSyncPayloads`
 * （即 Tab 调的 `buildG11SyncPayloads`；上市 五、69 / 国企 八、70）。Tab 挂载时只读审定数、订阅窗口事件、广播说明（都不进载荷），
 * 离屏不挂钩子，所以没有 prepare；保存回调为空。前缀与底稿主入口 `useG11FormData` 同口径（`G11`）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useG11Disclosure } from './useG11Disclosure'
import { buildG11TabSyncPayloads, readG11DisclosureAuditTexts } from './g11DisclosureTabSync'

export const g11HeadlessProvider = defineHeadlessProvider({
  prefix: 'G11',
  setup: ({ ctx, responses }) => useG11Disclosure({
    variant: ctx.variant,
    allResponses: ref(responses),
    debouncedSave: () => {},
    wpId: ref(ctx.wpId),
    isReadonly: ref(false),
  }),
  build: (dis, { ctx, responses }) => {
    const texts = readG11DisclosureAuditTexts(responses, ctx.variant)
    return buildG11TabSyncPayloads(ctx.wpId, ctx.variant, ctx.applicableStandards, dis, texts.note, texts.conclusion)
  },
})
