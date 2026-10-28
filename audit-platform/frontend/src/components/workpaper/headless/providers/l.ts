/** 离屏同步 provider 登记：L 筹资（spec note-pull-followup-closure R1；只登记本组编码）。 */
import type { HeadlessProviderLoader } from '../headlessFramework'

export const L_HEADLESS: Record<string, HeadlessProviderLoader> = {
  L1: () => import('@/components/workpaper/composables/l1HeadlessDisclosure').then((m) => m.l1HeadlessProvider),
  L2: () => import('@/components/workpaper/composables/l2HeadlessDisclosure').then((m) => m.l2HeadlessProvider),
  L3: () => import('@/components/workpaper/composables/l3HeadlessDisclosure').then((m) => m.l3HeadlessProvider),
  L7: () => import('@/components/workpaper/composables/l7HeadlessDisclosure').then((m) => m.l7HeadlessProvider),
  L8: () => import('@/components/workpaper/composables/l8HeadlessDisclosure').then((m) => m.l8HeadlessProvider),
}
