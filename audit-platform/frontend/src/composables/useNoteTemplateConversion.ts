/**
 * Sprint C.3 — useNoteTemplateConversion composable (C.3.1)
 * 
 * Manages template type conversion (D14 国企↔上市).
 */
import { ref } from 'vue'
import { api } from '@/services/apiProxy'
import { ElMessage } from 'element-plus'

export interface ConversionPreview {
  common_sections: number
  to_archive_sections: number
  to_create_sections: number
  format_changed_sections: number
  user_edits_preserved: number
  warnings: string[]
}

export function useNoteTemplateConversion(projectId: () => string, year: () => number) {
  const previewing = ref(false)
  const converting = ref(false)
  const preview = ref<ConversionPreview | null>(null)

  async function previewConversion(targetType: string): Promise<ConversionPreview | null> {
    previewing.value = true
    try {
      const resp: any = await api.post(
        `/api/disclosure-notes/${projectId()}/${year()}/template-conversion/preview`,
        { target_type: targetType }
      )
      preview.value = resp
      return resp
    } catch (e: any) {
      ElMessage.error(e?.message || '预览失败')
      return null
    } finally {
      previewing.value = false
    }
  }

  async function executeConversion(targetType: string): Promise<boolean> {
    converting.value = true
    try {
      await api.post(
        `/api/disclosure-notes/${projectId()}/${year()}/template-conversion/execute`,
        { target_type: targetType, confirmed: true }
      )
      ElMessage.success('准则切换完成')
      return true
    } catch (e: any) {
      ElMessage.error(e?.message || '切换失败')
      return false
    } finally {
      converting.value = false
    }
  }

  return { previewing, converting, preview, previewConversion, executeConversion }
}
