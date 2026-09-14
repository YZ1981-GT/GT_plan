/**
 * useViewMode — 视图模式切换 composable
 *
 * 支持 list (master-detail) 和 grid (full grid) 两种视图
 */
import { ref } from 'vue'

export type ViewMode = 'list' | 'grid'

export function useViewMode(defaultMode: ViewMode = 'list') {
  const viewMode = ref<ViewMode>(defaultMode)

  function switchTo(mode: ViewMode) {
    viewMode.value = mode
  }

  function toggle() {
    viewMode.value = viewMode.value === 'list' ? 'grid' : 'list'
  }

  return {
    viewMode,
    switchTo,
    toggle,
  }
}
