/**
 * useJ3DualMode — J3 股份支付双模式（HTML结构化 / OnlyOffice降级）
 *
 * Spec: .kiro/specs/j3-share-based-payment/
 * Requirements: 1.1
 */
import { ref, computed } from 'vue'
import http from '@/utils/http'

export type J3RenderMode = 'html' | 'onlyoffice'

export function useJ3DualMode(wpId: string) {
  const mode = ref<J3RenderMode>('html')

  function switchMode(newMode: J3RenderMode) {
    mode.value = newMode
  }

  const isHtml = computed(() => mode.value === 'html')
  const isOO = computed(() => mode.value === 'onlyoffice')

  // OO 健康检查
  async function checkOOHealth(): Promise<boolean> {
    try {
      const res = await http.get('/api/workpapers/onlyoffice/health')
      return res.data?.data?.healthy ?? res.data?.healthy ?? false
    } catch {
      return false
    }
  }

  return {
    mode,
    isHtml,
    isOO,
    switchMode,
    checkOOHealth,
  }
}
