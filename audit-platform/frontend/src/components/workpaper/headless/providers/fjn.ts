/** 离屏同步 provider 登记：F 采购存货 / J 职工薪酬 / N 税费（spec note-pull-followup-closure R1；只登记本组编码）。 */
import type { HeadlessProviderLoader } from '../headlessFramework'

export const FJN_HEADLESS: Record<string, HeadlessProviderLoader> = {
  F1: () => import('@/components/workpaper/composables/f1HeadlessDisclosure').then((m) => m.f1HeadlessProvider),
  F2: () => import('@/components/workpaper/composables/f2HeadlessDisclosure').then((m) => m.f2HeadlessProvider),
  F3: () => import('@/components/workpaper/composables/f3HeadlessDisclosure').then((m) => m.f3HeadlessProvider),
  F4: () => import('@/components/workpaper/composables/f4HeadlessDisclosure').then((m) => m.f4HeadlessProvider),
  J1: () => import('@/composables/workpaper/j1/j1HeadlessDisclosure').then((m) => m.j1HeadlessProvider),
  J2: () => import('@/components/workpaper/composables/j2HeadlessDisclosure').then((m) => m.j2HeadlessProvider),
  N1: () => import('@/components/workpaper/composables/n1HeadlessDisclosure').then((m) => m.n1HeadlessProvider),
  N2: () => import('@/components/workpaper/composables/n2HeadlessDisclosure').then((m) => m.n2HeadlessProvider),
  N4: () => import('@/components/workpaper/composables/n4HeadlessDisclosure').then((m) => m.n4HeadlessProvider),
  N5: () => import('@/components/workpaper/composables/n5HeadlessDisclosure').then((m) => m.n5HeadlessProvider),
}
