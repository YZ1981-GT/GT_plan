/**
 * useNoteExport — Word 导出 / 离线导入导出触发
 *
 * 从 DisclosureEditor.vue 抽取，保持原有语义不变。
 */
import { ref, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import * as P from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

export interface UseNoteExportOptions {
  projectId: ComputedRef<string> | Ref<string>
  year: ComputedRef<number> | Ref<number>
}

export interface UseNoteExportReturn {
  exportLoading: Ref<boolean>
  onExportWord: () => Promise<void>
}

export function useNoteExport(options: UseNoteExportOptions): UseNoteExportReturn {
  const { projectId, year } = options

  const exportLoading = ref(false)

  async function onExportWord() {
    exportLoading.value = true
    try {
      const { default: http } = await import('@/utils/http')
      const resp = await http.post(
        P.disclosureNotes.exportWord(projectId.value, year.value),
        {},
        { responseType: 'blob' }
      )
      // 下载 blob
      const blob = new Blob([resp.data], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `附注_${year.value}.docx`
      a.click()
      URL.revokeObjectURL(url)
      ElMessage.success('附注 Word 导出成功')
    } catch (e: any) {
      handleApiError(e, '导出附注 Word')
    } finally { exportLoading.value = false }
  }

  return {
    exportLoading,
    onExportWord,
  }
}
