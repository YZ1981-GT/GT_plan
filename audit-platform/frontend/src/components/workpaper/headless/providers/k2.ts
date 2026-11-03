/** 离屏同步 provider 登记：K7 – K13 管理（spec note-pull-followup-closure R1；只登记本组编码）。 */
import type { HeadlessProviderLoader } from '../headlessFramework'

export const K2_HEADLESS: Record<string, HeadlessProviderLoader> = {
  K7: () => import('@/components/workpaper/composables/k7HeadlessDisclosure').then((m) => m.k7HeadlessProvider),
  K8: () => import('@/components/workpaper/composables/k8HeadlessDisclosure').then((m) => m.k8HeadlessProvider),
  K9: () => import('@/components/workpaper/composables/k9HeadlessDisclosure').then((m) => m.k9HeadlessProvider),
  K10: () => import('@/components/workpaper/composables/k10HeadlessDisclosure').then((m) => m.k10HeadlessProvider),
  K11: () => import('@/components/workpaper/composables/k11HeadlessDisclosure').then((m) => m.k11HeadlessProvider),
  K12: () => import('@/components/workpaper/composables/k12HeadlessDisclosure').then((m) => m.k12HeadlessProvider),
  K13: () => import('@/components/workpaper/composables/k13HeadlessDisclosure').then((m) => m.k13HeadlessProvider),
}
