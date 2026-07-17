/** F2 监盘 — AI 辅助生成 + 差异分析摘要 */
import { ref, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

export type F2StAiSection =
  | 'stocktake-questionnaire'
  | 'stocktake-questionnaire-field'
  | 'stocktake-plan'
  | 'stocktake-plan-field'
  | 'stocktake-summary'
  | 'stocktake-summary-field'
  | 'stocktake-reconcile'
  | 'stocktake-reconcile-field'
  | 'stocktake-sample'
  | 'stocktake-sample-field'
  | 'stocktake-rollforward'
  | 'stocktake-rollforward-field'

export interface StocktakeDiffItem {
  itemName: string
  bookQty: number
  actualQty: number
  reason?: string
}

export function useF2StocktakeAiGenerate(options: {
  wpId: Ref<string>
  projectId: Ref<string>
}) {
  const { wpId, projectId } = options
  const aiAvailable = ref(false)
  const loading = ref(false)
  const diffLoading = ref(false)

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
    section: F2StAiSection,
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
        `/api/workpapers/${wpId.value}/f2-st/ai-generate`,
        { section, existingContent, relatedContext },
        { _silent: true } as any,
      )
      const text = res.data?.data?.content ?? res.data?.content ?? ''
      if (!text) {
        ElMessage.warning('AI 未生成内容')
        return null
      }
      const preview = text.length > 600 ? `${text.slice(0, 600)}…` : text
      const confirmHint =
        section === 'stocktake-plan'
          ? `${preview}\n\n（确认后将写入结论框）`
          : section.endsWith('-field')
            ? `${preview}\n\n（确认后写入当前文本框，可再编辑）`
            : preview
      await ElMessageBox.confirm(confirmHint, title, {
        confirmButtonText: '填入',
        cancelButtonText: '取消',
        type: 'info',
        customStyle: { maxWidth: '640px', whiteSpace: 'pre-wrap' },
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

  async function generateDiffSummary(
    differences: StocktakeDiffItem[],
    conclusion: string,
  ): Promise<{ summary: string; riskAlerts: string[] } | null> {
    if (!projectId.value || !wpId.value) return null
    diffLoading.value = true
    try {
      const res = await http.post(
        `/api/projects/${projectId.value}/workpapers/${wpId.value}/ai/stocktake-summary`,
        { differences, conclusion },
        { _silent: true } as any,
      )
      const data = res.data?.data ?? res.data
      const summary = data?.summary ?? ''
      const riskAlerts = data?.risk_alerts ?? data?.riskAlerts ?? []
      if (!summary) {
        ElMessage.warning('未生成差异分析摘要')
        return null
      }
      const preview = summary.length > 400 ? `${summary.slice(0, 400)}…` : summary
      await ElMessageBox.confirm(preview, 'LLM 监盘差异分析', {
        confirmButtonText: '填入结论',
        cancelButtonText: '取消',
        type: 'info',
        customStyle: { maxWidth: '600px' },
      })
      return { summary, riskAlerts: Array.isArray(riskAlerts) ? riskAlerts : [] }
    } catch (err: any) {
      if (err !== 'cancel' && err?.message !== 'cancel') {
        ElMessage.warning('差异分析生成失败')
      }
      return null
    } finally {
      diffLoading.value = false
    }
  }

  onMounted(() => { void checkAiHealth() })

  return {
    aiAvailable,
    loading,
    diffLoading,
    generateAndConfirm,
    generateDiffSummary,
    checkAiHealth,
  }
}

export default useF2StocktakeAiGenerate
