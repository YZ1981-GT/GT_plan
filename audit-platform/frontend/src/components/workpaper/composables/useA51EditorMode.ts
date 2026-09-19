/**
 * useA51EditorMode — A5-1 现金流量表审计 双模式管理
 *
 * Spec: .kiro/specs/a5-1-cashflow-audit/
 * Task: 3.1
 *
 * 职责：
 * - mode: 'structured' | 'excel'（默认 structured）
 * - switching: boolean（切换中 loading 态）
 * - onlyofficeHealthy: boolean（健康状态）
 * - checkHealth(): GET /api/workpapers/onlyoffice/health
 * - switchToExcel(flushFn): flush → mode='excel'
 * - switchToStructured(wpId, refreshFn): refreshData → mode='structured'
 */
import { ref, type Ref } from 'vue'
import { api } from '@/services/apiProxy'

export interface UseA51EditorModeReturn {
  mode: Ref<'structured' | 'excel'>
  switching: Ref<boolean>
  onlyofficeHealthy: Ref<boolean>
  checkHealth: () => Promise<void>
  switchToExcel: (flushFn: () => Promise<void>) => Promise<void>
  switchToStructured: (wpId: string, refreshFn: (wpId: string) => Promise<void>) => Promise<void>
}

export function useA51EditorMode(): UseA51EditorModeReturn {
  const mode = ref<'structured' | 'excel'>('structured')
  const switching = ref(false)
  const onlyofficeHealthy = ref(false)

  async function checkHealth(): Promise<void> {
    try {
      const res = await api.get<any>(
        '/api/workpapers/onlyoffice/health',
        { _silent: true } as any,
      )
      onlyofficeHealthy.value = !!res?.healthy
    } catch {
      onlyofficeHealthy.value = false
    }
  }

  async function switchToExcel(flushFn: () => Promise<void>): Promise<void> {
    if (switching.value) return
    switching.value = true
    try {
      await flushFn()
      mode.value = 'excel'
    } finally {
      switching.value = false
    }
  }

  async function switchToStructured(
    wpId: string,
    refreshFn: (wpId: string) => Promise<void>,
  ): Promise<void> {
    if (switching.value) return
    switching.value = true
    try {
      await refreshFn(wpId)
      mode.value = 'structured'
    } finally {
      switching.value = false
    }
  }

  return {
    mode,
    switching,
    onlyofficeHealthy,
    checkHealth,
    switchToExcel,
    switchToStructured,
  }
}
