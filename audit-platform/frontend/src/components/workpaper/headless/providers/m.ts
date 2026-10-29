/** 离屏同步 provider 登记：M 股东权益（spec note-pull-followup-closure R1；只登记本组编码）。 */
import type { HeadlessProviderLoader } from '../headlessFramework'

export const M_HEADLESS: Record<string, HeadlessProviderLoader> = {
  M1: () => import('@/components/workpaper/composables/m1HeadlessDisclosure').then((m) => m.m1HeadlessProvider),
  M2: () => import('@/components/workpaper/composables/m2HeadlessDisclosure').then((m) => m.m2HeadlessProvider),
  M3: () => import('@/components/workpaper/composables/m3HeadlessDisclosure').then((m) => m.m3HeadlessProvider),
  M4: () => import('@/components/workpaper/composables/mEquityHeadlessDisclosure').then((m) => m.m4HeadlessProvider),
  M5: () => import('@/components/workpaper/composables/mEquityHeadlessDisclosure').then((m) => m.m5HeadlessProvider),
  M6: () => import('@/components/workpaper/composables/m6HeadlessDisclosure').then((m) => m.m6HeadlessProvider),
  M7: () => import('@/components/workpaper/composables/mEquityHeadlessDisclosure').then((m) => m.m7HeadlessProvider),
  M8: () => import('@/components/workpaper/composables/mEquityHeadlessDisclosure').then((m) => m.m8HeadlessProvider),
  M9: () => import('@/components/workpaper/composables/m9HeadlessDisclosure').then((m) => m.m9HeadlessProvider),
  M10: () => import('@/components/workpaper/composables/m10HeadlessDisclosure').then((m) => m.m10HeadlessProvider),
}
