/** L5 长期应付款离屏同步：从持久化明细恢复主章节与一年内到期章节。 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildL5DisclosureSyncBodies, restoreL5DisclosureState } from './l5DisclosureTabState'

export const l5HeadlessProvider = defineHeadlessProvider({
  prefix: 'L5-',
  setup: ({ ctx, responses }) => ({
    bodies: buildL5DisclosureSyncBodies({
      variant: ctx.variant,
      wpId: ctx.wpId,
      applicableStandards: ctx.applicableStandards,
      state: restoreL5DisclosureState(responses, ctx.variant),
    }),
  }),
  build: ({ bodies }) => bodies,
})
