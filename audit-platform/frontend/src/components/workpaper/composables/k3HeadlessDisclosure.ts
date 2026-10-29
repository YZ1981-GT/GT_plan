/** K3 其他应付款离屏同步：只投影 K3 拥有的按性质与长期挂账表。 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { buildK3SyncPayload } from './k3NoteSectionMap'
import {
  K3_DISCLOSURE_RESPONSE_PREFIX,
  loadK3OwnerSnapshot,
} from './k3DisclosureTabState'

export const k3HeadlessProvider = defineHeadlessProvider({
  prefix: K3_DISCLOSURE_RESPONSE_PREFIX,
  setup: ({ ctx, responses }) => ({
    variant: ctx.variant,
    ...loadK3OwnerSnapshot(ctx.variant, responses),
  }),
  build: (state, { ctx }) => state.hasSource
    ? buildK3SyncPayload(state.variant, ctx.wpId, state.snapshot)
    : null,
})
