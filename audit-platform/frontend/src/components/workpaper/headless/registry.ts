/**
 * 离屏同步 provider 总登记（spec note-pull-followup-closure R1）：各组一份登记文件，按组接入互不改同一文件。
 * 同一编码只许出现在一组（`noteHeadlessProviders.spec.ts` 钉住）。
 */
import type { HeadlessProviderLoader } from './headlessFramework'
import { DE_HEADLESS } from './providers/de'
import { FJN_HEADLESS } from './providers/fjn'
import { G1_HEADLESS } from './providers/g1'
import { G2_HEADLESS } from './providers/g2'
import { H_HEADLESS } from './providers/h'
import { I_HEADLESS } from './providers/i'
import { K1_HEADLESS } from './providers/k1'
import { K2_HEADLESS } from './providers/k2'
import { L_HEADLESS } from './providers/l'
import { M_HEADLESS } from './providers/m'

export const HEADLESS_PROVIDER_GROUPS: Readonly<Record<string, Readonly<Record<string, HeadlessProviderLoader>>>> = {
  de: DE_HEADLESS,
  fjn: FJN_HEADLESS,
  g1: G1_HEADLESS,
  g2: G2_HEADLESS,
  h: H_HEADLESS,
  i: I_HEADLESS,
  k1: K1_HEADLESS,
  k2: K2_HEADLESS,
  l: L_HEADLESS,
  m: M_HEADLESS,
}

export const HEADLESS_PROVIDERS: Readonly<Record<string, HeadlessProviderLoader>> = Object.freeze(
  Object.assign({}, ...Object.values(HEADLESS_PROVIDER_GROUPS)),
)
