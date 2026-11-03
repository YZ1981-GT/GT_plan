/** 离屏同步 provider 登记：D 销售收入 / E 货币资金（spec note-pull-followup-closure R1；只登记本组编码）。 */
import type { HeadlessProviderLoader } from '../headlessFramework'

export const DE_HEADLESS: Record<string, HeadlessProviderLoader> = {
  D2: () => import('@/components/workpaper/composables/d2HeadlessDisclosure').then((m) => m.d2HeadlessProvider),
  D1: () => import('@/components/workpaper/composables/d1HeadlessDisclosure').then((m) => m.d1HeadlessProvider),
  D3: () => import('@/components/workpaper/composables/d3HeadlessDisclosure').then((m) => m.d3HeadlessProvider),
  D4: () => import('@/components/workpaper/composables/d4HeadlessDisclosure').then((m) => m.d4HeadlessProvider),
  D5: () => import('@/components/workpaper/composables/d5HeadlessDisclosure').then((m) => m.d5HeadlessProvider),
  D6: () => import('@/components/workpaper/composables/d6HeadlessDisclosure').then((m) => m.d6HeadlessProvider),
  D7: () => import('@/components/workpaper/composables/d7HeadlessDisclosure').then((m) => m.d7HeadlessProvider),
  E1: () => import('@/components/workpaper/composables/e1HeadlessDisclosure').then((m) => m.e1HeadlessProvider),
}
