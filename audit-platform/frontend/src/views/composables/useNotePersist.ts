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
}

export interface UseNotePersistReturn {
  saveLoading: Ref<boolean>
  justSaved: Ref<boolean>
  onSave: () => Promise<void>
}

export function useNotePersist(options: UseNotePersistOptions): UseNotePersistReturn {
  const { currentNote, textContent, editMode, clearEditDirty, autoSaveClearDirty, clearAutoSaveDraft } = options

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
        body.table_data = currentNote.value!.table_data
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
