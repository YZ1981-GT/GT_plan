/**
 * useG5AiGenerate — G5 长期应收款 AI 辅助
 * POST /api/workpapers/{wpId}/g5/ai/{section}
 */
import { onMounted, ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

export type G5AiSection =
  | 'adjudication-analysis'
  | 'adjudication-note'
  | 'adjudication-conclusion'
  | 'detail-note'
  | 'detail-conclusion'
  | 'baddebt-note'
  | 'baddebt-conclusion'
  | 'adjustment-note'
  | 'adjustment-conclusion'
  | 'lease-amortization-conclusion'
  | 'sales-amortization-conclusion'
  | 'factoring-conclusion'
  | 'ecl-policy-eval-1'
  | 'ecl-policy-eval-2'
  | 'ecl-policy-eval-3'
  | 'ecl-policy-eval-4'
  | 'ecl-policy-conclusion'
  | 'stage-classification-conclusion'
  | 'impairment-calc-conclusion'
  | 'reversal-writeoff-conclusion'
  | 'voucher-conclusion'
  | 'disclosure-conclusion'
  | 'disclosure-listed-note'
  | 'disclosure-soe-note'

export function useG5AiGenerate(wpId: Ref<string>) {
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
    section: G5AiSection,
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
        `/api/workpapers/${wpId.value}/g5/ai/${section}`,
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

export default useG5AiGenerate
