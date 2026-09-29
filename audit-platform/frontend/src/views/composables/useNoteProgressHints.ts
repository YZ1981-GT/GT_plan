/**
 * useNoteProgressHints — 附注编制进度统计 + 首次同步引导横幅
 *
 * 从 `DisclosureEditor.vue` 抽出（该宿主 HARD_CAPS ceiling 1800）。纯派生 + 一处
 * localStorage 记忆（按 projectId 分区，避免跨项目串记忆）。
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'

export interface NoteProgress {
  complete: number
  textOnly: number
  tableOnly: number
  empty: number
  total: number
}

export interface UseNoteProgressHintsOptions {
  projectId: Ref<string> | ComputedRef<string>
  noteList: Ref<any[]> | ComputedRef<any[]>
}

export function useNoteProgressHints(options: UseNoteProgressHintsOptions) {
  const { projectId, noteList } = options

  const storageKey = () => `gt_note_sync_hint_dismissed_${projectId.value}`

  // #20: 首次同步引导横幅（从未同步过的项目一次性提示）
  const syncHintDismissed = ref(localStorage.getItem(storageKey()) === 'true')

  const showSyncHint = computed(() => {
    if (syncHintDismissed.value) return false
    // noteList 全部无 last_sync_at 时视为从未同步
    const list = noteList.value || []
    if (!list.length) return false
    return !list.some((n: any) => n.last_sync_at || n.last_sync_source)
  })

  function dismissSyncHint() {
    syncHintDismissed.value = true
    localStorage.setItem(storageKey(), 'true')
  }

  // #22: 编制进度统计（四态互斥：完整 / 仅文字 / 仅表格 / 空）
  const noteProgress = computed<NoteProgress>(() => {
    const list = (noteList.value || []) as any[]
    if (!list.length) return { complete: 0, textOnly: 0, tableOnly: 0, empty: 0, total: 0 }
    let complete = 0, textOnly = 0, tableOnly = 0, empty = 0
    for (const n of list) {
      const hasText = !!(n.text_content && n.text_content.trim())
      const hasData = !!n.has_data
      if (hasText && hasData) complete++
      else if (hasText) textOnly++
      else if (hasData) tableOnly++
      else empty++
    }
    return { complete, textOnly, tableOnly, empty, total: list.length }
  })

  return { showSyncHint, dismissSyncHint, noteProgress, syncHintDismissed }
}
