/**
 * useWorkpaperGenerate — 底稿生成流程 composable
 *
 * 封装"生成底稿"按钮的完整流程：
 * 1. 点击 → 弹出裁剪确认弹窗
 * 2. 用户确认 → 调用 POST /api/projects/{id}/working-papers/generate
 * 3. 刷新列表
 *
 * Requirements: 3.1, 3.5
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

export interface GenerateOptions {
  projectId: string
  templateSetId: string
  year: number
  onSuccess?: (count: number) => void
}

export function useWorkpaperGenerate(options: GenerateOptions) {
  const { projectId, templateSetId, year, onSuccess } = options

  const showTrimDialog = ref(false)
  const generating = ref(false)

  /** 触发生成流程：先弹裁剪确认弹窗 */
  function triggerGenerate() {
    showTrimDialog.value = true
  }

  /** 裁剪确认后调用生成 API */
  async function onTrimConfirm(selectedCodes: string[]) {
    if (!selectedCodes.length) {
      ElMessage.warning('请至少选择一项底稿')
      return
    }

    generating.value = true
    try {
      const result = await api.post<{ count: number }>(
        `/api/projects/${projectId}/working-papers/generate`,
        {
          template_set_id: templateSetId,
          year,
          selected_templates: selectedCodes,
        },
      )
      ElMessage.success(`已生成 ${result.count} 个底稿`)
      onSuccess?.(result.count)
    } catch (e: any) {
      ElMessage.error(e?.message || '生成失败')
    } finally {
      generating.value = false
    }
  }

  return {
    showTrimDialog,
    generating,
    triggerGenerate,
    onTrimConfirm,
  }
}
