/** M6 未分配利润离屏同步：两版按附注模板固定行恢复并构建。 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildM6SyncPayload } from './m6NoteSectionMap'
import { m6NoteText, m6WireRows, restoreM6ListedRows, restoreM6SoeRows } from './m6DisclosureForm'

export const m6HeadlessProvider = defineHeadlessProvider({
  prefix: 'M6-',
  setup: ({ ctx, responses }) => {
    const rows = ctx.variant === 'listed' ? restoreM6ListedRows(responses) : restoreM6SoeRows(responses)
    return { rows, noteText: m6NoteText(responses, ctx.variant) }
  },
  build: ({ rows, noteText }, { ctx }) => buildM6SyncPayload(
    ctx.wpId,
    ctx.variant,
    m6WireRows(ctx.variant, rows),
    noteText,
  ),
})
