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
  /** 当前 sheet 编码，如 D2-1 / D2-2 / 附注上市 */
  currentSheet: Ref<string>
  reloadAllResponses: () => Promise<void>
}

export interface OOConfig {
  documentUrl: string
  token?: string
  [key: string]: any
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2DualMode(options: UseD2DualModeOptions) {
  const { wpId, currentSheet, reloadAllResponses } = options

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
        const sheetName = getSheetNameFromCode(currentSheet.value)
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
   * 将 sheet 编码映射到 xlsx sheet 名
   */
  function getSheetNameFromCode(code: string): string {
    const SHEET_MAP: Record<string, string> = {
      D2: 'D2',
      目录: 'D2',
      D2A: 'D2A',
      'D2-1': 'D2-1',
      'D2-2': 'D2-2',
      'D2-3': 'D2-3',
      'D2-4': 'D2-4',
      'D2-5': 'D2-5',
      'D2-6': 'D2-6',
      'D2-7': 'D2-7',
      'D2-8': 'D2-8',
      'D2-9': 'D2-9',
      'D2-10': 'D2-10',
      'D2-11': 'D2-11',
      'D2-12': 'D2-12',
      'D2-13': 'D2-13',
      附注上市: '附注披露信息(上市公司)',
      附注国企: '附注披露信息(国企)',
      截止测试: '截止测试',
    }
    if (SHEET_MAP[code]) return SHEET_MAP[code]
    if (code.includes('截止')) return code
    return code
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
    getSheetNameFromCode,
  }
}

export default useD2DualMode
