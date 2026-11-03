/**
 * N2 应交税费披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：四表预填取外壳传给 Tab 的同一份 `htmlData.adjudication_prefill` —— 外壳
 * （GtWpRenderer → GtN2TaxesPayable）传的是本口径披露 sheet 的 `html_data`，这里用外壳同一个 `resolveRenderSheet` 在渲染
 * 配置里定位它 → `useN2DisclosureTables` → Tab onMounted 的 `restore()` → 同一个 `buildPayload`（ctx 同样只带 wpId / year）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { resolveRenderSheet } from '@/composables/useWpRenderer'
import { useN2DisclosureTables } from './useN2DisclosureTables'
import { N2_DISCLOSURE_SHEET_NAME } from './n2NoteSectionMap'

export const n2HeadlessProvider = defineHeadlessProvider({
  // 与 useN2FormData.loadResponses 同口径
  prefix: 'N2-',
  needs: { renderConfig: true },
  setup: ({ ctx, responses, renderConfig }) => {
    const sheets = Array.isArray(renderConfig?.sheets) ? renderConfig.sheets : []
    const htmlData = resolveRenderSheet(sheets, N2_DISCLOSURE_SHEET_NAME[ctx.variant])?.html_data
    return useN2DisclosureTables({
      variant: ctx.variant,
      allResponses: ref(responses),
      renderPrefill: ref(htmlData?.adjudication_prefill),
    })
  },
  prepare: (tables) => tables.restore(),
  build: (tables, { ctx }) => tables.buildPayload({ wpId: ctx.wpId, year: ctx.year }),
})
