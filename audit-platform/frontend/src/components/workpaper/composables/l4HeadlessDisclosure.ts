/** L4 应付债券披露离屏同步：与真实 Tab 共用持久化恢复和 wire body。 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildL4DisclosureSyncBody, restoreL4DisclosureState } from './l4DisclosureTabState'

export const l4HeadlessProvider = defineHeadlessProvider({
  prefix: 'L4-',
  setup: ({ ctx, responses }) => ({
    body: buildL4DisclosureSyncBody({
      variant: ctx.variant,
      wpId: ctx.wpId,
      projectId: ctx.projectId,
      state: restoreL4DisclosureState(responses, ctx.variant),
    }),
  }),
  build: ({ body }) => body,
})
