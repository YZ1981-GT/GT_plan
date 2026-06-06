/**
 * Sprint C.3 — useNoteSectionNumbering composable (C.3.1)
 * 
 * Manages section numbering state and real-time rendering (D13).
 */
import { ref, computed } from 'vue'
import { api } from '@/services/apiProxy'

export interface NumberingState {
  renderedNumbers: Record<string, string>
  scope: 'standalone' | 'consolidated' | 'both'
}

export function useNoteSectionNumbering(projectId: () => string, year: () => number) {
  const state = ref<NumberingState>({
    renderedNumbers: {},
    scope: 'both',
  })

  async function refreshNumbers(scope?: string) {
    try {
      const resp: any = await api.get(
        `/api/disclosure-notes/${projectId()}/${year()}/section-numbers`,
        { params: { scope: scope || state.value.scope }, _silent: true } as any
      )
      state.value.renderedNumbers = resp || {}
    } catch {
      // Graceful degradation
    }
  }

  function getNumber(sectionId: string): string {
    return state.value.renderedNumbers[sectionId] || ''
  }

  function setScope(scope: 'standalone' | 'consolidated' | 'both') {
    state.value.scope = scope
    refreshNumbers(scope)
  }

  return { state, refreshNumbers, getNumber, setScope }
}
