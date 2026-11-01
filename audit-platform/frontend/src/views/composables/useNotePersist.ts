/**
 * useNotePersist — 保存 / 自动保存脏标记
 *
 * 从 DisclosureEditor.vue 抽取，保持原有语义不变。
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { updateDisclosureNote, type DisclosureNoteDetail } from '@/services/auditPlatformApi'
import { createSaveCoordinator, type SaveAttempt } from '@/composables/saveCoordinator'

export interface UseNotePersistOptions {
  currentNote: Ref<DisclosureNoteDetail | null>
  textContent: Ref<string>
  editMode: Ref<boolean>
  clearEditDirty: () => void
  autoSaveClearDirty: () => void
  clearAutoSaveDraft: () => void
  /** 保存前把投影编辑提交回 raw table_data；未提供时保持旧保存语义。 */
  prepareTableData?: (tableData: any) => any
}

export interface NoteSaveOptions {
  /** 定时自动保存：只存，不退出编辑、不弹「保存成功」。函数形态供并发手工保存提升本轮语义。 */
  keepEditing?: boolean | (() => boolean)
}

export interface UseNotePersistReturn {
  saveLoading: Ref<boolean>
  justSaved: Ref<boolean>
  markEdited: () => number
  discardEdits: (noteId?: string) => void
  onSave: (opts?: NoteSaveOptions) => Promise<boolean>
}

export function useNotePersist(options: UseNotePersistOptions): UseNotePersistReturn {
  const { currentNote, textContent, editMode, clearEditDirty, autoSaveClearDirty, clearAutoSaveDraft, prepareTableData } = options
  const saveCoordinator = createSaveCoordinator<string>()
  const saveLoading = ref(false)
  const justSaved = ref(false)
  let loadingCount = 0

  function currentNoteId(): string | null {
    const id = currentNote.value?.id
    return id == null ? null : String(id)
  }

  function markEdited(): number {
    const noteId = currentNoteId()
    return noteId ? saveCoordinator.markEdited(noteId) : 0
  }

  function discardEdits(noteId = currentNoteId() ?? undefined): void {
    if (noteId) saveCoordinator.discard(noteId)
  }

  function shouldKeepEditing(opts: NoteSaveOptions): boolean {
    return typeof opts.keepEditing === 'function'
      ? opts.keepEditing()
      : opts.keepEditing === true
  }

  async function saveRevision(
    attempt: SaveAttempt<string>,
    initialNote: DisclosureNoteDetail,
    opts: NoteSaveOptions,
  ): Promise<boolean> {
    const liveNote = currentNoteId() === attempt.documentKey ? currentNote.value : initialNote
    if (!liveNote || String(liveNote.id) !== attempt.documentKey) return false

    const body: Record<string, any> = {}
    // 三种正文类型都必须显式发送 text_content；空串表示用户确认清空。
    if (liveNote.content_type === 'text' || liveNote.content_type === 'mixed' || liveNote.content_type === 'table') {
      body.text_content = currentNoteId() === attempt.documentKey
        ? textContent.value
        : liveNote.text_content
    }
    if (liveNote.content_type === 'table' || liveNote.content_type === 'mixed') {
      const tableDataInput = liveNote.table_data == null
        ? liveNote.table_data
        : JSON.parse(JSON.stringify(liveNote.table_data))
      body.table_data = prepareTableData
        ? prepareTableData(tableDataInput)
        : tableDataInput
    }

    await updateDisclosureNote(liveNote.id, body)
    // 保存期间又有编辑时，旧请求只确认服务端已收，不得回放旧快照或清 dirty；协调器会立即补存。
    if (!attempt.isCurrent()) return true

    if (body.text_content !== undefined) liveNote.text_content = body.text_content
    if (body.table_data !== undefined) liveNote.table_data = body.table_data
    liveNote.status = 'confirmed'
    // 保存期间切章时只更新被保存章节缓存，不清理新章节状态，也不显示旧章节成功提示。
    if (currentNoteId() !== attempt.documentKey) return true

    const keepEditing = shouldKeepEditing(opts)
    if (!keepEditing) {
      editMode.value = false
      ElMessage.success('保存成功')
    }
    clearEditDirty()
    autoSaveClearDirty()
    clearAutoSaveDraft()
    justSaved.value = true
    setTimeout(() => { justSaved.value = false }, 2500)
    return true
  }

  async function onSave(opts: NoteSaveOptions = {}): Promise<boolean> {
    const initialNote = currentNote.value
    const noteId = currentNoteId()
    if (!initialNote || !noteId) return false
    loadingCount += 1
    saveLoading.value = true
    try {
      const saved = await saveCoordinator.run(
        noteId,
        attempt => saveRevision(attempt, initialNote, opts),
      )
      return saved && currentNoteId() === noteId
    } finally {
      loadingCount = Math.max(0, loadingCount - 1)
      saveLoading.value = loadingCount > 0
    }
  }

  return {
    saveLoading,
    justSaved,
    markEdited,
    discardEdits,
    onSave,
  }
}
