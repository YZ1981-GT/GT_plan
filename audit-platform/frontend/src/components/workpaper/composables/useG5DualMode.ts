/**
 * useG5DualMode — G5 长期应收款 HTML↔OnlyOffice 双模式切换
 *
 * Spec: .kiro/specs/g5-long-term-receivable/
 * Task: 14.4
 *
 * localStorage 持久化用户偏好。
 */
import { ref, watch } from 'vue'

const STORAGE_KEY = 'g5-view-mode'

export function useG5DualMode() {
  const stored = localStorage.getItem(STORAGE_KEY)
  const viewMode = ref<'HTML' | 'OO'>(stored === 'OO' ? 'OO' : 'HTML')

  const viewModeOptions = [
    { label: 'HTML', value: 'HTML' },
    { label: 'OnlyOffice', value: 'OO' },
  ]

  watch(viewMode, (val) => {
    localStorage.setItem(STORAGE_KEY, val)
  })

  return { viewMode, viewModeOptions }
}

export default useG5DualMode
