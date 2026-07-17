/**
 * useEvidenceMetrics — 证据治理可观测性指标 composable（Wave 6/9 前端接线）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * Requirements: R12, R15, R16
 * Design: §9.3 可观测性
 *
 * 后端路由（evidence_governance observability_router）：
 *  - GET /api/evidence-governance/metrics   全局低基数指标 + 近期告警（admin/manager/partner）
 *
 * 指标为进程内聚合、非项目 scope，故走全局前缀（无 project/year 路径）。
 */

import { ref } from 'vue'
import http from '@/utils/http'

export function useEvidenceMetrics() {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const metrics = ref<Record<string, any> | null>(null)

  async function loadMetrics(): Promise<Record<string, any> | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get('/api/evidence-governance/metrics')
      metrics.value = (res.data?.data ?? res.data) as Record<string, any>
      return metrics.value
    } catch (e: any) {
      const data = e?.response?.data
      const payload = data?.data || data
      if (payload?.error_code === 'SCOPE_NOT_FOUND_OR_FORBIDDEN') {
        error.value = '无权查看治理指标（仅 admin/manager/partner）'
      } else {
        error.value = payload?.message || e?.message || '加载指标失败'
      }
      metrics.value = null
      return null
    } finally {
      loading.value = false
    }
  }

  return { loading, error, metrics, loadMetrics }
}
