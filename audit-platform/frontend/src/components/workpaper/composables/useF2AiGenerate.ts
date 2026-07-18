/**
 * useF2AiGenerate — F2 AI 辅助生成（POST /f2/ai-generate）
 * Spec: .kiro/specs/f2-inventory-main/ Task 20.2
 */
import { ref, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

export type F2AiSection =
  | 'adj-note'
  | 'adj-conclusion'
  | 'summary-note'
  | 'summary-conclusion'
  | 'summary-objective'
  | 'summary-process'
  | 'summary-change-reason'
  | 'detail-valuation'
  | 'detail-change'
  | 'detail-long-aging'
  | 'detail-impairment'
  | 'detail-conclusion'
  | 'analysis-conclusion'
  | 'cutoff-conclusion'
  | 'cutoff-process-note'
  | 'cutoff-audit-note'
  | 'cutoff-standard-conclusion'
  | 'policy-evaluation'
  | 'production-sales-conclusion'
  | 'cost-comparison-conclusion'
  | 'f2-14-note'
  | 'f2-14-conclusion'
  | 'f2-14-summary'
  | 'f2-16-note'
  | 'f2-16-conclusion'
  | 'f2-16-process'
  | 'f2-18-note-a'
  | 'f2-18-note-b'
  | 'f2-18-note-c'
  | 'f2-18-note-d'
  | 'f2-18-abnormal'
  | 'f2-18-conclusion'
  | 'f2-19-note'
  | 'f2-19-conclusion'
  | 'f2-20-note'
  | 'f2-20-abnormal'
  | 'f2-20-conclusion'

export function useF2AiGenerate(wpId: Ref<string>) {
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
    section: F2AiSection,
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
        `/api/workpapers/${wpId.value}/f2/ai-generate`,
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

  onMounted(() => {
    // 延后探测，避免与底稿 checklist 首屏请求抢带宽
    const run = () => { void checkAiHealth() }
    if (typeof requestIdleCallback === 'function') {
      requestIdleCallback(run, { timeout: 2500 })
    } else {
      setTimeout(run, 800)
    }
  })

  return { aiAvailable, loading, generateAndConfirm, checkAiHealth }
}

export default useF2AiGenerate
