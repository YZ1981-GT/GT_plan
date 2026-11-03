/** 离屏同步 provider 登记：G8 – G14 投资（spec note-pull-followup-closure R1；只登记本组编码）。 */
import type { HeadlessProviderLoader } from '../headlessFramework'

export const G2_HEADLESS: Record<string, HeadlessProviderLoader> = {
  G8: () => import('@/components/workpaper/composables/g8HeadlessDisclosure').then((m) => m.g8HeadlessProvider),
  G9: () => import('@/components/workpaper/composables/g9HeadlessDisclosure').then((m) => m.g9HeadlessProvider),
  G10: () => import('@/components/workpaper/composables/g10HeadlessDisclosure').then((m) => m.g10HeadlessProvider),
  G11: () => import('@/components/workpaper/composables/g11HeadlessDisclosure').then((m) => m.g11HeadlessProvider),
  G12: () => import('@/components/workpaper/composables/g12HeadlessDisclosure').then((m) => m.g12HeadlessProvider),
  G13: () => import('@/components/workpaper/composables/g13HeadlessDisclosure').then((m) => m.g13HeadlessProvider),
  G14: () => import('@/components/workpaper/composables/g14HeadlessDisclosure').then((m) => m.g14HeadlessProvider),
}
