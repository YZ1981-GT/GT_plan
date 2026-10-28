/** 离屏同步 provider 登记：K1 – K6 管理（spec note-pull-followup-closure R1；只登记本组编码）。 */
import type { HeadlessProviderLoader } from '../headlessFramework'

export const K1_HEADLESS: Record<string, HeadlessProviderLoader> = {
  K1: () => import('@/components/workpaper/composables/k1HeadlessDisclosure').then((m) => m.k1HeadlessProvider),
  K2: () => import('@/components/workpaper/composables/k2HeadlessDisclosure').then((m) => m.k2HeadlessProvider),
  K4: () => import('@/components/workpaper/composables/k4HeadlessDisclosure').then((m) => m.k4HeadlessProvider),
  K5: () => import('@/components/workpaper/composables/k5HeadlessDisclosure').then((m) => m.k5HeadlessProvider),
  K6: () => import('@/components/workpaper/composables/k6HeadlessDisclosure').then((m) => m.k6HeadlessProvider),
}
