/**
 * N1 递延所得税资产披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：四表预填（`adjudication_prefill` / `liability_prefill`）按 `useN1FormData.selfLoad` 同一取法
 * `extractN1RenderSeeds` 从渲染配置取 → `useN1DisclosureTables`（审计年度、预填照 Tab 传）→ Tab onMounted 的 `restore()` →
 * 同一个 `buildPayload`（ctx 同样只带 wpId / year）。已同步表名只读不写（离屏不改底稿）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useN1DisclosureTables } from './useN1DisclosureTables'
import { extractN1RenderSeeds } from './useN1FormData'

export const n1HeadlessProvider = defineHeadlessProvider({
  // 与 useN1FormData.loadResponses 同口径
  prefix: 'N1-',
  needs: { renderConfig: true },
  setup: ({ ctx, responses, renderConfig }) => {
    const seeds = extractN1RenderSeeds(renderConfig)
    return useN1DisclosureTables({
      variant: ctx.variant,
      allResponses: ref(responses),
      auditYear: ref<number | null>(ctx.year),
      adjudicationPrefill: ref(seeds?.adjudicationPrefill ?? {}),
      liabilityPrefill: ref(seeds?.liabilityPrefill ?? {}),
    })
  },
  prepare: (tables) => tables.restore(),
  build: (tables, { ctx }) => tables.buildPayload({ wpId: ctx.wpId, year: ctx.year }),
})
