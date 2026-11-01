import { getCurrentScope, onScopeDispose, ref, type Ref } from 'vue'

export type NoteSaveStatus = 'idle' | 'saving' | 'saved' | 'error'

export interface NoteSaveFlowOptions {
  currentNoteId: () => string | undefined
  save: (options: { keepEditing: boolean }) => Promise<void>
  onSaved?: (auto: boolean) => void
}

export interface SaveCurrentNoteOptions {
  auto?: boolean
}

/**
 * 附注一次保存的状态与章节竞态边界。
 *
 * 保存期间切换章节时，旧请求可以完成自己的持久化，但不得把新章节标成“已保存”、
 * 调用跳转回调或覆盖新章节的状态。手工保存退出编辑，自动保存保持编辑态。
 */
export function useNoteSaveFlow(options: NoteSaveFlowOptions): {
  saveStatus: Ref<NoteSaveStatus>
  saveCurrentNote: (options?: SaveCurrentNoteOptions) => Promise<boolean>
} {
  const saveStatus = ref<NoteSaveStatus>('idle')
  let resetTimer: ReturnType<typeof setTimeout> | null = null
  let generation = 0

  function clearResetTimer(): void {
    if (resetTimer !== null) clearTimeout(resetTimer)
    resetTimer = null
  }

  async function saveCurrentNote(request: SaveCurrentNoteOptions = {}): Promise<boolean> {
    const noteId = options.currentNoteId()
    if (!noteId) return false
    const auto = request.auto === true
    const ownGeneration = ++generation
    clearResetTimer()
    saveStatus.value = 'saving'
    try {
      await options.save({ keepEditing: auto })
      if (ownGeneration !== generation || options.currentNoteId() !== noteId) {
        if (ownGeneration === generation) saveStatus.value = 'idle'
        return true
      }
      saveStatus.value = 'saved'
      options.onSaved?.(auto)
      resetTimer = setTimeout(() => {
        if (ownGeneration === generation && saveStatus.value === 'saved') saveStatus.value = 'idle'
      }, 2500)
      return true
    } catch {
      if (ownGeneration === generation) {
        saveStatus.value = options.currentNoteId() === noteId ? 'error' : 'idle'
      }
      return false
    }
  }

  if (getCurrentScope()) onScopeDispose(clearResetTimer)
  return { saveStatus, saveCurrentNote }
}
