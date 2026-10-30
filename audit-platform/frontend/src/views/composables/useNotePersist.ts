/**
 * useNotePersist — 保存 / 自动保存脏标记
 *
 * 从 DisclosureEditor.vue 抽取，保持原有语义不变。
 */
import { ref, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { updateDisclosureNote, type DisclosureNoteDetail } from '@/services/auditPlatformApi'
import { withLoading } from '@/composables/useLoading'

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
  /** 定时自动保存：只存，不退出编辑、不弹「保存成功」（用户可能正在本章连续编辑） */
  keepEditing?: boolean
}

export interface UseNotePersistReturn {
  saveLoading: Ref<boolean>
  justSaved: Ref<boolean>
  onSave: (opts?: NoteSaveOptions) => Promise<void>
}

export function useNotePersist(options: UseNotePersistOptions): UseNotePersistReturn {
  const { currentNote, textContent, editMode, clearEditDirty, autoSaveClearDirty, clearAutoSaveDraft, prepareTableData } = options

  const saveLoading = ref(false)
  const justSaved = ref(false)

  async function onSave(opts: NoteSaveOptions = {}) {
    const keepEditing = opts.keepEditing === true
    const note = currentNote.value
    if (!note) return
    await withLoading(saveLoading, async () => {
      const body: Record<string, any> = {}
      // 三种正文类型都必须显式发送 text_content；空串表示用户确认清空。
      if (note.content_type === 'text' || note.content_type === 'mixed' || note.content_type === 'table') {
        body.text_content = textContent.value
      }
      if (note.content_type === 'table' || note.content_type === 'mixed') {
        // table_data 是 JSON 载荷；给投影转换器独立副本，防止其原地修改缓存。
        const tableDataInput = note.table_data == null
          ? note.table_data
          : JSON.parse(JSON.stringify(note.table_data))
        body.table_data = prepareTableData
          ? prepareTableData(tableDataInput)
          : tableDataInput
      }
      await updateDisclosureNote(note.id, body)
      if (!keepEditing) ElMessage.success('保存成功')
      // 仅在请求成功后回写被保存章节的快照，失败时保留原值。
      if (body.text_content !== undefined) {
        note.text_content = body.text_content
      }
      if (body.table_data !== undefined) {
        note.table_data = body.table_data
      }
      note.status = 'confirmed'
      // 保存期间若已切章，不得关闭或清理新章节的编辑状态。
      if (currentNote.value?.id !== note.id) return
      // 定时保存不收起编辑态：原先 2 分钟一到就退出编辑，正在填的格子直接消失（2026-10-26 浏览器实测）
      if (!keepEditing) editMode.value = false
      clearEditDirty()
      autoSaveClearDirty()
      clearAutoSaveDraft()
      justSaved.value = true
      setTimeout(() => { justSaved.value = false }, 2500)
    })()
  }

  return {
    saveLoading,
    justSaved,
    onSave,
  }
}
