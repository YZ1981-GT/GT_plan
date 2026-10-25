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

export interface UseNotePersistReturn {
  saveLoading: Ref<boolean>
  justSaved: Ref<boolean>
  onSave: () => Promise<void>
}

export function useNotePersist(options: UseNotePersistOptions): UseNotePersistReturn {
  const { currentNote, textContent, editMode, clearEditDirty, autoSaveClearDirty, clearAutoSaveDraft, prepareTableData } = options

  const saveLoading = ref(false)
  const justSaved = ref(false)

  async function onSave() {
    if (!currentNote.value) return
    await withLoading(saveLoading, async () => {
      const body: Record<string, any> = {}
      if (currentNote.value!.content_type === 'text' || currentNote.value!.content_type === 'mixed') {
        body.text_content = textContent.value
      }
      if (currentNote.value!.content_type === 'table' || currentNote.value!.content_type === 'mixed') {
        const prepared = prepareTableData
          ? prepareTableData(currentNote.value!.table_data)
          : currentNote.value!.table_data
        if (prepared !== currentNote.value!.table_data) {
          currentNote.value!.table_data = prepared
        }
        body.table_data = prepared
      }
      await updateDisclosureNote(currentNote.value!.id, body)
      ElMessage.success('保存成功')
      editMode.value = false
      clearEditDirty()
      autoSaveClearDirty()
      clearAutoSaveDraft()
      currentNote.value!.status = 'confirmed'
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
