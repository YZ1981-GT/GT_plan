import type { InjectionKey, Ref } from 'vue'
import type { CanonicalWorkpaperLocation } from '@/shared/contracts/gc0'
import type { WorkpaperCapabilitySnapshot } from './workpaperCapabilitySnapshot'

/** WorkpaperEditor 向所有嵌套 renderer 提供的真实公式能力与位置。 */
export interface FormulaManagerCapabilityContext {
  capability: Readonly<Ref<WorkpaperCapabilitySnapshot>>
  location: Readonly<Ref<CanonicalWorkpaperLocation | null>>
}

export const FORMULA_MANAGER_CAPABILITY_CONTEXT: InjectionKey<FormulaManagerCapabilityContext> =
  Symbol('formula-manager-capability-context')
