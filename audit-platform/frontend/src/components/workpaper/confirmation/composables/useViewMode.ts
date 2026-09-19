/**
 * useViewMode — 列表/完整表格视图切换 composable
 *
 * 两种视图共享 useConfirmationData.rows，编辑互通。
 * 视图偏好 localStorage 持久化。
 */
import { ref, watch } from 'vue'

export type ViewMode = 'list' | 'grid'

const STORAGE_KEY = 'confirmation-view-mode'

export function useViewMode() {
  // 从 localStorage 恢复，默认 list
  const saved = localStorage.getItem(STORAGE_KEY)
  const viewMode = ref<ViewMode>((saved === 'grid' || saved === 'list') ? saved : 'list')

  // 持久化变化
  watch(viewMode, (mode) => {
    localStorage.setItem(STORAGE_KEY, mode)
  })

  function toggleView() {
    viewMode.value = viewMode.value === 'list' ? 'grid' : 'list'
  }

  return { viewMode, toggleView }
}
