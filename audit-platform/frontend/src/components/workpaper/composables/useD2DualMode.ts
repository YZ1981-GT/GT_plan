/**
 * useD2DualMode — D2 双模式切换 composable (HTML ↔ OnlyOffice)
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Task: 38.1
 *
 * 职责：
 * - mode ref ('html' | 'onlyoffice')
 * - OO 健康检查（GET /api/workpapers/onlyoffice/health）
 * - ooAvailable ref
 * - switchMode: 切OO→获取config+隐藏非当前sheet；切HTML→重新加载allResponses
 * - OO不可用时禁用切换 + tooltip
 *
 * Requirements: 17.1-17.5
 */
import { ref, onMounted, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export type D2RenderMode = 'html' | 'onlyoffice'

export interface UseD2DualModeOptions {
  wpId: Ref<string>
  activeTab: Ref<string>
  reloadAllResponses: () => Promise<void>
}

export interface OOConfig {
  documentUrl: string
  token?: string
  [key: string]: any
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2DualMode(options: UseD2DualModeOptions) {
  const { wpId, activeTab, reloadAllResponses } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const mode = ref<D2RenderMode>('html')
  const ooAvailable = ref<boolean>(false)
  const ooConfig = ref<OOConfig | null>(null)
  const checking = ref<boolean>(false)

  // ─── Health Check ──────────────────────────────────────────────────────

  /**
   * 检查 OnlyOffice 服务是否可用
   * GET /api/workpapers/onlyoffice/health → { data: { healthy: true } }
   */
  async function checkOOHealth(): Promise<boolean> {
    checking.value = true
    try {
      const response = await fetch('/api/workpapers/onlyoffice/health')
      if (!response.ok) {
        ooAvailable.value = false
        return false
      }
      const result = await response.json()
      // 兼容 ResponseWrapperMiddleware 信封
      const healthy = result.data?.healthy ?? result.healthy ?? false
      ooAvailable.value = healthy
      return healthy
    } catch {
      ooAvailable.value = false
      return false
    } finally {
      checking.value = false
    }
  }

  // ─── Switch Mode ───────────────────────────────────────────────────────

  /**
   * 切换渲染模式
   *
   * - 切OO：获取当前sheet的OO配置，隐藏非当前sheet
   * - 切HTML：重新加载allResponses确保数据同步
   */
  async function switchMode(target: D2RenderMode): Promise<void> {
    if (target === mode.value) return
    if (target === 'onlyoffice' && !ooAvailable.value) return

    if (target === 'onlyoffice') {
      // 获取 OO 配置
      try {
        const sheetName = getSheetNameFromTab(activeTab.value)
        const response = await fetch(
          `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sheetName)}/onlyoffice-config`
        )
        if (response.ok) {
          const result = await response.json()
          ooConfig.value = result.data || result
          mode.value = 'onlyoffice'
        }
      } catch {
        // 降级保持 HTML 模式
        ooAvailable.value = false
      }
    } else {
      // 切回 HTML: 重新加载数据（OO 编辑可能通过 callback 已回写）
      mode.value = 'html'
      ooConfig.value = null
      await reloadAllResponses()
    }
  }

  // ─── Helpers ───────────────────────────────────────────────────────────

  /**
   * 将 Tab name 映射到 xlsx 中的 sheet name
   */
  function getSheetNameFromTab(tab: string): string {
    const TAB_SHEET_MAP: Record<string, string> = {
      'directory': 'D2-目录',
      'procedure': 'D2A',
      'adjudication': 'D2-1',
      'detail-d2-2': 'D2-2',
      'bad-debt': 'D2-3',
      'adjustment': 'D2-4',
      'analysis': 'D2-5',
      'related-party': 'D2-6',
      'general-check': 'D2-7',
      'policy-check': 'D2-8',
      'ecl-calculation': 'D2-9',
      'ecl-measurement': 'D2-10',
      'writeoff-check': 'D2-11',
      'factoring': 'D2-12',
      'bizmodel-check': 'D2-13',
      'disclosure': 'D2-14',
      'cutoff-test': 'D2-17',
    }
    return TAB_SHEET_MAP[tab] || 'D2-1'
  }

  /**
   * OO 不可用时的 tooltip 文本
   */
  function getDisabledTooltip(): string {
    if (!ooAvailable.value) {
      return 'OnlyOffice 服务不可用，仅支持 HTML 模式'
    }
    return ''
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  onMounted(() => {
    checkOOHealth()
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 状态
    mode,
    ooAvailable,
    ooConfig,
    checking,

    // 操作
    switchMode,
    checkOOHealth,
    getDisabledTooltip,
    getSheetNameFromTab,
  }
}

export default useD2DualMode
