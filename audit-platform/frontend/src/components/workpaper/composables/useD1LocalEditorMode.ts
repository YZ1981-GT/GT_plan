/**
 * useD1LocalEditorMode — Tab 内 HTML/OO 切换（入口双模式时 suppress 本地 OO）
 */
import { ref, computed, inject } from 'vue'

export function useD1LocalEditorMode() {
  const suppressLocalOo = inject('d1SuppressLocalOo', false)
  const editorMode = ref<'html' | 'oo'>('html')
  const modeOptions = [
    { label: 'HTML', value: 'html' },
    { label: 'OnlyOffice', value: 'oo' },
  ] as const
  const showModeToggle = computed(() => !suppressLocalOo)
  const isOoMode = computed(() => !suppressLocalOo && editorMode.value === 'oo')
  const isHtmlMode = computed(() => suppressLocalOo || editorMode.value === 'html')
  return { suppressLocalOo, editorMode, modeOptions, showModeToggle, isOoMode, isHtmlMode }
}

export default useD1LocalEditorMode
