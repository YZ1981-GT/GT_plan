/**
 * useJ2DualMode — J2 HTML/OnlyOffice 双模式切换
 *
 * 所有D~N HTML 专属组件必须支持 HTML ↔ OO 切换。
 * 默认 HTML 模式（结构化交互），OO 为降级/偏好切换。
 *
 * Spec: .kiro/specs/j2-defined-benefit-plan/
 * Requirements: 6.5 双模式
 */
import { ref, computed } from 'vue'

export type RenderMode = 'html' | 'onlyoffice'

export function useJ2DualMode() {
  const mode = ref<RenderMode>('html')

  const isHtmlMode = computed(() => mode.value === 'html')
  const isOOMode = computed(() => mode.value === 'onlyoffice')

  function switchMode(newMode: RenderMode) {
    mode.value = newMode
  }

  function toggleMode() {
    mode.value = mode.value === 'html' ? 'onlyoffice' : 'html'
  }

  return {
    mode,
    isHtmlMode,
    isOOMode,
    switchMode,
    toggleMode,
  }
}
