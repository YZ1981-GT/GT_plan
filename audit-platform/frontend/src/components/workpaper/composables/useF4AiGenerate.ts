/**
 * useF4AiGenerate — F4 应付账款 AI 辅助生成。
 */
import { onMounted, ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

export type F4AiSection =
  | 'adjudication-reason'
  | 'adjudication-note'
  | 'adjudication-conclusion'
  | 'detail-note'
  | 'detail-conclusion'
  | 'adjustment-note'
  | 'adjustment-conclusion'
  | 'substantive-turnover-note'
  | 'substantive-creditor-note'
  | 'substantive-conclusion'
  | 'long-outstanding-note'
  | 'long-outstanding-conclusion'
  | 'related-party-note'
  | 'related-party-conclusion'
  | 'unrecorded-conclusion'
  | 'unrecorded-note'
  | 'voucher-check-note'
  | 'voucher-check-conclusion'
  | 'voucher-check-issue'
  | 'financing-note'
  | 'financing-conclusion'
  | 'disclosure-listed'
  | 'disclosure-listed-note'
  | 'disclosure-listed-conclusion'
  | 'disclosure-soe'
  | 'disclosure-soe-note'
  | 'disclosure-soe-conclusion'

export function useF4AiGenerate(wpId: Ref<string>) {
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
    section: F4AiSection,
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
        `/api/workpapers/${wpId.value}/f4/ai-generate`,
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

export default useF4AiGenerate
