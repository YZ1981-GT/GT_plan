/**
 * useF5AiGenerate — F5 营业成本 AI 辅助生成。
 */
import { onMounted, ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

export type F5AiSection =
  | 'adjudication-note'
  | 'adjudication-conclusion'
  | 'monthly-detail-note'
  | 'monthly-detail-conclusion'
  | 'other-cost-note'
  | 'other-cost-conclusion'
  | 'cost-analysis'
  | 'comparison-note'
  | 'comparison-conclusion'
  | 'quantity-reconciliation'
  | 'quantity-reconciliation-note'
  | 'quantity-reconciliation-conclusion'
  | 'rollforward-note'
  | 'rollforward-evaluation'
  | 'adjustment-note'
  | 'adjustment-evaluation'
  | 'adjustment-entry-note'
  | 'adjustment-entry-conclusion'

export function useF5AiGenerate(wpId: Ref<string>) {
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
    section: F5AiSection,
    existingContent: string,
    relatedContext: Record<string, unknown>,
    title: string,
  ): Promise<string | null> {
    if (!aiAvailable.value) {
      ElMessage.warning('AI 服务暂不可用')
      return null
    }
    loading.value = true
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/f5/ai-generate`,
        { section, existingContent, relatedContext },
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

export default useF5AiGenerate
