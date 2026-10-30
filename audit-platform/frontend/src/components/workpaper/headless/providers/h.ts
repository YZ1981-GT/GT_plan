/** 离屏同步 provider 登记：H 固定资产（spec note-pull-followup-closure R1；只登记本组编码）。 */
import type { HeadlessProviderLoader } from '../headlessFramework'

export const H_HEADLESS: Record<string, HeadlessProviderLoader> = {
  H1: () => import('@/components/workpaper/composables/h1HeadlessDisclosure').then((m) => m.h1HeadlessProvider),
  H2: () => import('@/components/workpaper/composables/h2HeadlessDisclosure').then((m) => m.h2HeadlessProvider),
  H3: () => import('@/components/workpaper/composables/h3HeadlessDisclosure').then((m) => m.h3HeadlessProvider),
  H4: () => import('@/components/workpaper/composables/h4HeadlessDisclosure').then((m) => m.h4HeadlessProvider),
  H5: () => import('@/components/workpaper/composables/h5HeadlessDisclosure').then((m) => m.h5HeadlessProvider),
  H6: () => import('@/components/workpaper/composables/h6HeadlessDisclosure').then((m) => m.h6HeadlessProvider),
  H7: () => import('@/components/workpaper/composables/h7HeadlessDisclosure').then((m) => m.h7HeadlessProvider),
  H8: () => import('@/components/workpaper/composables/h8HeadlessDisclosure').then((m) => m.h8HeadlessProvider),
  H9: () => import('@/components/workpaper/composables/h9HeadlessDisclosure').then((m) => m.h9HeadlessProvider),
  H10: () => import('@/components/workpaper/composables/h10HeadlessDisclosure').then((m) => m.h10HeadlessProvider),
}
