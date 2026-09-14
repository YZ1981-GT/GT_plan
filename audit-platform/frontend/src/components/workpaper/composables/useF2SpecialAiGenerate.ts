/**
 * useF2SpecialAiGenerate — F2 特殊组 AI（POST /f2-spe/ai-generate）
 */
import { ref, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

export type F2SpeAiSection =
  | 'contract-cost-note'
  | 'contract-cost-conclusion'
  | 'contract-check-note'
  | 'contract-check-conclusion'
  | 'contract-check-issue'
  | 'contract-impairment-note'
  | 'contract-impairment-conclusion'
  | 'loss-contract-note'
  | 'loss-contract-conclusion'
  | 'purchase-price-variance-note'
  | 'purchase-price-market-note'
  | 'purchase-price-conclusion'
  | 'unit-price-note'
  | 'unit-price-conclusion'
  | 'capacity-utilization-note'
  | 'storage-capacity-note'
  | 'energy-consumption-note'
  | 'capacity-energy-conclusion'
  | 'production-cost-structure-note'
  | 'production-cost-flow-note'
  | 'product-unit-cost-note'
  | 'material-consumption-note'
  | 'unit-consumption-conclusion'
  | 'related-inquiry-note'
  | 'related-inquiry-conclusion'
  | 'related-market-note'
  | 'related-market-conclusion'
  | 'undisclosed-party-note'
  | 'undisclosed-party-conclusion'
  | 'supplier-structure-note'
  | 'supplier-structure-conclusion'
  | 'supplier-checklist-note'
  | 'supplier-checklist-conclusion'
  | 'supplier-info-note'
  | 'supplier-info-conclusion'
  | 'interview-summary-note'
  | 'interview-summary-conclusion'
  | 'interview-detail-note'
  | 'interview-detail-conclusion'
  | 'impairment-analysis'
  | 'loss-analysis'
  | 'price-analysis'
  | 'capacity-analysis'
  | 'consumption-analysis'
  | 'related-party-conclusion'
  | 'supplier-analysis'

export function useF2SpecialAiGenerate(wpId: Ref<string>) {
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
    section: F2SpeAiSection,
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
        `/api/workpapers/${wpId.value}/f2-spe/ai-generate`,
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

export default useF2SpecialAiGenerate
