/** M9 其他综合收益离屏同步：两版复用真实 Tab 的恢复与模板 payload。 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import {
  buildM9DisclosurePayload,
  m9NoteText,
  restoreM9ListedRows,
  restoreM9SoeRows,
} from './m9DisclosureForm'

export const m9HeadlessProvider = defineHeadlessProvider({
  prefix: 'M9-',
  setup: ({ ctx, responses }) => {
    if (ctx.variant === 'listed') {
      return {
        variant: 'listed' as const,
        bsNon: restoreM9ListedRows(responses, 'balanceSheet', 'nonReclass'),
        bsReclass: restoreM9ListedRows(responses, 'balanceSheet', 'reclass'),
        plNon: restoreM9ListedRows(responses, 'incomeStatement', 'nonReclass'),
        plReclass: restoreM9ListedRows(responses, 'incomeStatement', 'reclass'),
        noteText: m9NoteText(responses, 'listed'),
      }
    }
    return {
      variant: 'soe' as const,
      nonReclass: restoreM9SoeRows(responses, 'nonReclass'),
      reclass: restoreM9SoeRows(responses, 'reclass'),
      noteText: m9NoteText(responses, 'soe'),
    }
  },
  build: (state, { ctx }) => buildM9DisclosurePayload({ wpId: ctx.wpId, ...state }),
})
