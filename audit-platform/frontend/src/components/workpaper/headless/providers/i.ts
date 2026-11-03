/** 离屏同步 provider 登记：I 无形资产（spec note-pull-followup-closure R1；只登记本组编码）。 */
import type { HeadlessProviderLoader } from '../headlessFramework'

export const I_HEADLESS: Record<string, HeadlessProviderLoader> = {
  I1: () => import('@/components/workpaper/composables/i1HeadlessDisclosure').then((m) => m.i1HeadlessProvider),
  I2: () => import('@/components/workpaper/composables/i2HeadlessDisclosure').then((m) => m.i2HeadlessProvider),
  I3: () => import('@/components/workpaper/composables/i3HeadlessDisclosure').then((m) => m.i3HeadlessProvider),
  I4: () => import('@/components/workpaper/composables/i4HeadlessDisclosure').then((m) => m.i4HeadlessProvider),
  I5: () => import('@/components/workpaper/composables/i5HeadlessDisclosure').then((m) => m.i5HeadlessProvider),
  I6: () => import('@/components/workpaper/composables/i6HeadlessDisclosure').then((m) => m.i6HeadlessProvider),
}
