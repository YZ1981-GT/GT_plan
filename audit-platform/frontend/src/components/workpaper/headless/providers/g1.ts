/** 离屏同步 provider 登记：G1 – G7 投资（spec note-pull-followup-closure R1；只登记本组编码）。 */
import type { HeadlessProviderLoader } from '../headlessFramework'

export const G1_HEADLESS: Record<string, HeadlessProviderLoader> = {
  G1: () => import('@/components/workpaper/composables/g1HeadlessDisclosure').then((m) => m.g1HeadlessProvider),
  G2: () => import('@/components/workpaper/composables/g2HeadlessDisclosure').then((m) => m.g2HeadlessProvider),
  G3: () => import('@/components/workpaper/composables/g3HeadlessDisclosure').then((m) => m.g3HeadlessProvider),
  G4: () => import('@/components/workpaper/composables/g4HeadlessDisclosure').then((m) => m.g4HeadlessProvider),
  G5: () => import('@/components/workpaper/composables/g5HeadlessDisclosure').then((m) => m.g5HeadlessProvider),
  G6: () => import('@/components/workpaper/composables/g6HeadlessDisclosure').then((m) => m.g6HeadlessProvider),
  G7: () => import('@/components/workpaper/composables/g7HeadlessDisclosure').then((m) => m.g7HeadlessProvider),
}
