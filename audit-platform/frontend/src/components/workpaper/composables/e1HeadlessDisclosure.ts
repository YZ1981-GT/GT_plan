/** E1 货币资金离屏同步：只写非公式 owner，状态恢复与真实 Tab 共用。 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { resolveRenderSheet } from '@/composables/useWpRenderer'
import { E1_DISCLOSURE_SHEET_NAME } from './e1NoteSectionMap'
import { e1NoteTexts } from './e1DisclosureScope'
import {
  resolveE1ManagedRestrictedRows,
  restoreE1ForeignCurrency,
  restoreE1NoteTexts,
  restoreE1RestrictedState,
} from './e1DisclosureTabState'
import { buildE1DisclosureSyncPlan } from './e1DisclosureSyncPlan'

export const e1HeadlessProvider = defineHeadlessProvider({
  prefix: 'E1-',
  needs: { renderConfig: true },
  setup: ({ ctx, responses, renderConfig }) => {
    const sheets = Array.isArray(renderConfig?.sheets) ? renderConfig.sheets : []
    const htmlData = resolveRenderSheet(sheets, E1_DISCLOSURE_SHEET_NAME[ctx.variant])?.html_data
    const foreign = restoreE1ForeignCurrency(responses, ctx.variant)
    const notes = restoreE1NoteTexts(responses, ctx.variant)
    const restrictedState = restoreE1RestrictedState(responses, ctx.variant)
    const restricted = resolveE1ManagedRestrictedRows({
      rawPrefill: htmlData?.restricted_prefill,
      restored: restrictedState,
    })
    const hasSource = notes.hasSource || foreign.hasSource || restricted.managedRows !== undefined
    return {
      payloads: hasSource
        ? buildE1DisclosureSyncPlan({
            variant: ctx.variant,
            wpId: ctx.wpId,
            year: ctx.year,
            applicableStandards: ctx.applicableStandards,
            restrictedRows: restricted.managedRows,
            noteSections: e1NoteTexts(ctx.variant).map(def => ({
              key: def.key,
              title: def.title,
              text: notes.texts[def.key] || '',
            })),
            foreignCurrencyRows: foreign.hasSource
              ? (foreign.mode === 'detailed' ? foreign.detailedRows : foreign.simpleRows)
              : [],
          }).map(item => item.payload)
        : [],
    }
  },
  build: instance => instance.payloads,
})
