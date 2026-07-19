/**
 * useG10AiGenerate — G10 交易性金融负债 AI 辅助
 * POST /api/workpapers/{wpId}/g10/ai/{section}
 */
import { onMounted, ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

export type G10AiSection =
  | 'adjudication-analysis'
  | 'adjudication-note'
  | 'adjudication-conclusion'
  | 'detail-note'
  | 'detail-conclusion'
  | 'adjustment-note'
  | 'adjustment-conclusion'
  | 'classification-conclusion'
  | 'classification-note'
  | 'fair-value-conclusion'
  | 'fair-value-note'
  | 'l3-note'
  | 'l3-conclusion'
  | 'derivative-conclusion'
  | 'derivative-note'
  | 'voucher-conclusion'
  | 'voucher-note'
  | 'disclosure-listed-note'
  | 'disclosure-soe-note'
  | 'disclosure-conclusion'

export function useG10AiGenerate(wpId: Ref<string>) {
  const aiAvailable = ref(false)
  const loading = ref(false)

  async function checkAiHealth(): Promise<void> {
    try {
      const response = await http.get('/api/ai/health', { _silent: true } as any)
      const status = response.data?.data?.status ?? response.data?.status
      aiAvailable.value = status === 'healthy' || status === 'degraded'
    } catch {
      aiAvailable.value = false
    }
  }

  async function generateAndConfirm(
    section: G10AiSection,
    existingContent: string,
    relatedContext: Record<string, unknown>,
    title: string,
  ): Promise<string | null> {
    if (!wpId.value) {
      ElMessage.warning('底稿未就绪')
      return null
    }
    if (!aiAvailable.value) {
      ElMessage.warning('AI 服务暂不可用')
      return null
    }
    loading.value = true
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/g10/ai/${section}`,
        { existingContent, relatedContext },
        { _silent: true } as any,
      )
      const content = response.data?.data?.content ?? response.data?.content ?? ''
      if (!content) {
        ElMessage.warning('AI 未生成内容')
        return null
      }
      const preview = content.length > 500 ? `${content.slice(0, 500)}…` : content
      await ElMessageBox.confirm(preview, title, {
        confirmButtonText: '填入',
        cancelButtonText: '取消',
        type: 'info',
        customStyle: { maxWidth: '640px' },
      })
      return content
    } catch (error: any) {
      if (error !== 'cancel' && error?.message !== 'cancel') {
        ElMessage.warning('AI 生成失败')
      }
      return null
    } finally {
      loading.value = false
    }
  }

  onMounted(() => { void checkAiHealth() })

  return { aiAvailable, loading, generateAndConfirm, checkAiHealth }
}

export default useG10AiGenerate
