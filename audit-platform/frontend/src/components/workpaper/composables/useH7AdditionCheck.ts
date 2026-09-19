/**
 * useH7AdditionCheck — H7 生产性生物资产 sheet-specific composable
 *
 * Spec: .kiro/specs/h7-biological-assets/ Task 3.4
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'

export function useH7AdditionCheck(allResponses: Ref<Map<string, any>>, opts?: { wpId?: Ref<string>; projectId?: Ref<string> }) {
  const isReady = ref(false)

  function getNum(key: string): number {
    const item = allResponses.value.get(key)
    if (!item) return 0
    const raw = item.remark ?? item.conclusion
    if (raw == null) return 0
    const n = Number(raw)
    return Number.isFinite(n) ? n : 0
  }

  function getString(key: string): string {
    const item = allResponses.value.get(key)
    return item?.remark ?? item?.conclusion ?? ''
  }

  return {
    isReady,
    getNum,
    getString,
  }
}

export default useH7AdditionCheck