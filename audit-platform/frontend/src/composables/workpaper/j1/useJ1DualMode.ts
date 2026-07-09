/**
 * useJ1DualMode — J1 双模式切换（HTML结构化 / OnlyOffice原始）
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 */
import { ref } from 'vue'

export type J1RenderMode = 'html' | 'onlyoffice'

export function useJ1DualMode() {
  const currentMode = ref<J1RenderMode>('html')

  function toggleMode() {
    currentMode.value = currentMode.value === 'html' ? 'onlyoffice' : 'html'
  }

  function setMode(mode: J1RenderMode) {
    currentMode.value = mode
  }

  return { currentMode, toggleMode, setMode }
}
