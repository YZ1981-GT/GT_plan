/**
 * useNotePersist — 保存 / 自动保存脏标记
 *
 * 从 DisclosureEditor.vue 抽取，保持原有语义不变。
 *
 * 2026-11-26（穿透复盘 P0/P1/P2）：
 * - 跨会话 CAS：保存携带编辑起点 content_digest（GET / 上次保存响应下发）；服务端 409
 *   NOTE_CONTENT_CONFLICT 时弹二选一（查看最新内容 / 放弃本次），不再静默覆盖。
 * - 稳定 mutation id：一次保存请求起一个 X-Mutation-Id，网络层重试沿用同一 id；
 *   协调器补存（内容已变）或换章后自然换新 id。
 * - 保存成功后采用服务端返回的 status / content_digest，不再把「已保存」本地写成「已确认」。
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { updateDisclosureNote, type DisclosureNoteDetail } from '@/services/auditPlatformApi'
import { createSaveCoordinator, type SaveAttempt } from '@/composables/saveCoordinator'
import { newUuid } from '@/utils/uuid'

export interface UseNotePersistOptions {
  currentNote: Ref<DisclosureNoteDetail | null>
  textContent: Ref<string>
  editMode: Ref<boolean>
  clearEditDirty: () => void
  autoSaveClearDirty: () => void
  clearAutoSaveDraft: () => void
  /** 保存前把投影编辑提交回 raw table_data；未提供时保持旧保存语义。 */
  prepareTableData?: (tableData: any) => any
  /** 409 冲突点「查看最新内容」时重载当前章节；未提供时退化为提示刷新。 */
  reloadCurrentNote?: () => Promise<void>
}

export interface NoteSaveOptions {
  /** 定时自动保存：只存，不退出编辑、不弹「保存成功」。函数形态供并发手工保存提升本轮语义。 */
  keepEditing?: boolean | (() => boolean)
}

/** 409 NOTE_CONTENT_CONFLICT 的结构化 detail（服务端 note_content_digest.note_content_conflict）。 */
interface NoteConflictDetail {
  error_code?: string
  message?: string
  current_digest?: string
}

function extractConflictDetail(err: any): NoteConflictDetail | null {
  const detail = err?.response?.data?.detail ?? err?.detail
  if (detail && typeof detail === 'object'
    && (detail.error_code === 'NOTE_CONTENT_CONFLICT' || detail.current_digest)) {
    return detail as NoteConflictDetail
  }
  return null
}

export function useNotePersist(options: UseNotePersistOptions): UseNotePersistReturn {
  const { currentNote, textContent, editMode, clearEditDirty, autoSaveClearDirty, clearAutoSaveDraft, prepareTableData, reloadCurrentNote } = options
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
    // 跨会话 CAS：带上本会话已知的编辑起点摘要（GET / 上次保存响应下发）。
    if (liveNote.content_digest) body.expected_digest = liveNote.content_digest

    try {
      const saved = await updateDisclosureNote(liveNote.id, body, {
        // 一次保存请求一个稳定幂等键：网络层重试沿用；补存/新保存自然换新。
        mutationId: newUuid(),
        silent: true, // 409 冲突由本函数统一弹窗，不走全局 toast
      })
      // 保存期间又有编辑时，旧请求只确认服务端已收，不得回放旧快照或清 dirty；协调器会立即补存。
      if (!attempt.isCurrent()) return true

      if (body.text_content !== undefined) liveNote.text_content = body.text_content
      if (body.table_data !== undefined) liveNote.table_data = body.table_data
      // 采用服务端返回的状态与最新摘要：不再把「已保存」本地写成「已确认」（P1 状态一致性）。
      if (saved?.status) liveNote.status = saved.status
      if (saved?.content_digest) liveNote.content_digest = saved.content_digest
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
    } catch (err: any) {
      const conflict = extractConflictDetail(err)
      if (conflict) {
        // 本会话起点已失效：旧 digest 作废（重载后 GET 会发新值）。
        if (liveNote) liveNote.content_digest = undefined
        try {
          await ElMessageBox.confirm(
            conflict.message || '该章节已被其他会话修改，请先查看最新内容后再保存',
            '保存冲突',
            {
              distinguishCancelAndClose: true,
              confirmButtonText: '查看最新内容',
              cancelButtonText: '放弃本次保存',
              type: 'warning',
            },
          )
          if (reloadCurrentNote) await reloadCurrentNote()
          else ElMessage.info('请刷新章节后基于最新内容重新编辑')
        } catch (_cancelled) {
          // 放弃本次保存：不清 dirty，用户可自行再改再存。
        }
        return false
      }
      // 其他错误按失败上抛（useNoteSaveFlow 置 error、保留 dirty）。
      throw err
    }
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

export interface UseNotePersistReturn {
  saveLoading: Ref<boolean>
  justSaved: Ref<boolean>
  markEdited: () => number
  discardEdits: (noteId?: string) => void
  onSave: (opts?: NoteSaveOptions) => Promise<boolean>
}
