/**
 * useF3AiGenerate — F3 AI 辅助生成（POST /f3/ai-generate）
 * Spec: .kiro/specs/f3-notes-payable/ Task 8.1
 */
import { ref, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

export type F3AiSection =
    | 'adjudication-note'
    | 'adjudication-conclusion'
    | 'detail-note'
    | 'detail-conclusion'
    | 'adjustment-note'
    | 'adjustment-conclusion'
    | 'interest-note'
    | 'interest-conclusion'
    | 'overdue-note'
    | 'overdue-evaluation'
    | 'related-note'
    | 'related-conclusion'
    | 'related-evaluation'
    | 'debit-check-conclusion'
    | 'credit-check-conclusion'
    | 'voucher-check-note'
    | 'voucher-check-conclusion'
    | 'voucher-check-issue'
    | 'listed-note'
    | 'soe-note'

export function useF3AiGenerate(wpId: Ref<string>) {
  const aiAvailable = ref(false)
  const loading = ref(false)

  async function checkAiHealth(): Promise<void> {
    try {
      const r = await http.get('/api/ai/health', { _silent: true } as any)
      const status = r.data?.data?.status ?? r.data?.status
      aiAvailable.value = status === 'healthy' || status === 'degraded'
    } catch {
      aiAvailable.value = false
    }
  }

  async function generateAndConfirm(
    section: F3AiSection,
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
      const res = await http.post(
        `/api/workpapers/${wpId.value}/f3/ai-generate`,
        { section, existingContent, relatedContext },
        { _silent: true } as any,
      )
      const text = res.data?.data?.content ?? res.data?.content ?? ''
      if (!text) {
        ElMessage.warning('AI 未生成内容')
        return null
      }
      const preview = text.length > 400 ? `${text.slice(0, 400)}…` : text
      await ElMessageBox.confirm(preview, title, {
        confirmButtonText: '填入',
        cancelButtonText: '取消',
        type: 'info',
        customStyle: { maxWidth: '600px' },
      })
      return text
    } catch (err: any) {
      if (err !== 'cancel' && err?.message !== 'cancel') {
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

export default useF3AiGenerate
