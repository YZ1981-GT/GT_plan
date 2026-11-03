/** M10 其他权益工具离屏同步：仅发送本底稿真实拥有的变动表与说明。 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import {
  buildM10DisclosurePayload,
  m10NoteText,
  restoreM10Rows,
} from './m10DisclosureForm'

export const m10HeadlessProvider = defineHeadlessProvider({
  prefix: 'M10-',
  setup: ({ ctx, responses }) => ({
    variant: ctx.variant,
    rows: restoreM10Rows(responses, ctx.variant),
    noteText: m10NoteText(responses, ctx.variant),
  }),
  build: (state, { ctx }) => buildM10DisclosurePayload({ wpId: ctx.wpId, ...state }),
})
