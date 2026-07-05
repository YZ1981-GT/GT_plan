/**
 * useD2AiGenerate — D2 应收账款 AI 辅助生成（POST /d2/ai-generate）
 */
import { ref, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

export type D2AiSection =
  | 'adj-note'
  | 'adj-conclusion'
  | 'policy-evaluation'
  | 'analysis-note'
  | 'detail-note'
  | 'writeoff-analysis'

export interface D2AiGenerateParams {
  section: D2AiSection
  existingContent?: string
  relatedContext?: Record<string, unknown>
}

export function useD2AiGenerate(wpId: Ref<string>) {
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

  async function generate(params: D2AiGenerateParams): Promise<string> {
    const res = await http.post(
      `/api/workpapers/${wpId.value}/d2/ai-generate`,
      {
        section: params.section,
        existingContent: params.existingContent ?? '',
        relatedContext: params.relatedContext ?? {},
      },
      { _silent: true } as any,
    )
    return res.data?.data?.content ?? res.data?.content ?? ''
  }

  async function generateAndConfirm(
    section: D2AiSection,
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
      const text = await generate({ section, existingContent, relatedContext })
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

  return { aiAvailable, loading, generate, generateAndConfirm, checkAiHealth }
}

export default useD2AiGenerate
