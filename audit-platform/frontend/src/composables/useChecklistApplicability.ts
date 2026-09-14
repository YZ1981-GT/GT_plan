/**
 * useChecklistApplicability — 核对表章节适用性（spec workpaper-frontend-large-component-split, Req 2）
 *
 * 从 GtChecklistTable.vue 抽出：
 * - sectionApplicability state + showApplicabilityDialog state
 * - isSectionApplicable / toggleSectionApplicability / confirmApplicability / openApplicabilityDialog
 *
 * 铁律：行为零变更、保响应式（ref/computed）；依赖单向；composable 之间不互相 import
 *       （confirmApplicability 标记 pending 并触发自动保存的回调由主组件 wire 传入）。
 */
import { ref, type Ref } from 'vue'

export function useChecklistApplicability(options: {
  /** readonly 取值（getter，保持响应式） */
  readonly: () => boolean
  /** 标记某 itemId 为待保存（主组件 pendingChanges.add） */
  markPending: (itemId: string) => void
  /** 触发自动保存（主组件 scheduleSave） */
  scheduleSave: () => void
}) {
  // ─── State ───
  const sectionApplicability = ref<Record<string, boolean>>({})
  const showApplicabilityDialog = ref(false)

  // ─── Methods ───
  function isSectionApplicable(sectionId: string): boolean {
    if (sectionId in sectionApplicability.value) {
      return sectionApplicability.value[sectionId]
    }
    return true // default applicable
  }

  function openApplicabilityDialog() {
    showApplicabilityDialog.value = true
  }

  function toggleSectionApplicability(sectionId: string) {
    if (options.readonly()) return
    const current = sectionApplicability.value[sectionId]
    sectionApplicability.value[sectionId] = current === undefined ? false : !current
  }

  function confirmApplicability() {
    showApplicabilityDialog.value = false
    // Mark all applicability changes as pending
    for (const sectionId of Object.keys(sectionApplicability.value)) {
      options.markPending(`TOC-${sectionId}`)
    }
    options.scheduleSave()
  }

  return {
    // state
    sectionApplicability,
    showApplicabilityDialog,
    // methods
    isSectionApplicable,
    openApplicabilityDialog,
    toggleSectionApplicability,
    confirmApplicability,
  }
}
