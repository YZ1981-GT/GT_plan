/**
 * useD4DualMode — D4 双模式切换 composable (structured ↔ OnlyOffice)
 *
 * Spec: .kiro/specs/d4-operating-revenue/
 * Task: 19.2
 *
 * 职责：
 * - currentMode ref ('structured' | 'onlyoffice')
 * - OO 健康检查（GET /api/workpapers/onlyoffice/health）
 * - isOoAvailable ref
 * - switchMode: 切OO→获取config+隐藏非当前sheet；切HTML→重新加载allResponses
 * - OO不可用时禁用切换 + tooltip
 * - 8个源xlsx对应8个OO配置
 *
 * Requirements: 23.1-23.6
 */
import { ref, onMounted, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export type D4RenderMode = 'structured' | 'onlyoffice'

export interface UseD4DualModeOptions {
  wpId: Ref<string>
  activeTab?: Ref<string>
  reloadAllResponses?: () => Promise<void>
}

export interface D4OOConfig {
  documentUrl: string
  token?: string
  [key: string]: any
}

// ─── Tab → Sheet Name Mapping ────────────────────────────────────────────────

/**
 * D4 Tab Name → xlsx中对应的sheet名称
 * 8个xlsx源文件，按当前二级Tab确定打开哪个xlsx
 */
const D4_TAB_SHEET_MAP: Record<string, string> = {
  'index': 'D4-目录',
  'procedure': 'D4A',
  'adjudication': 'D4-1',
  'revenue-detail': 'D4-2',
  'other-revenue': 'D4-3',
  'adjustment': 'D4-4',
  'disclosure-listed': 'D4-附注上市',
  'disclosure-soe': 'D4-附注国企',
  'policy-check': 'D4-5',
  'indicator': 'D4-6',
  'margin-monthly': 'D4-7',
  'product-margin': 'D4-8',
  'customer-structure': 'D4-9',
  'customer-price': 'D4-10',
  'product-price': 'D4-11',
  'contract': 'D4-12',
  'erp-check': 'D4-13',
  'occurrence': 'D4-14',
  'completeness': 'D4-15',
  'export-check': 'D4-16',
  'cutoff-forward': 'D4-17',
  'cutoff-backward': 'D4-18',
  'discount': 'D4-19',
  'return-check': 'D4-20',
  'related-price': 'D4-21',
  'ipo-procedure': 'D4-22A',
  'ipo-indicator': 'D4-22',
  'invoice-compare': 'D4-23',
  'third-party': 'D4-24',
  'dealer': 'D4-25',
  'overseas': 'D4-26',
  'undisclosed-rp': 'D4-27',
  'customer-checklist': 'D4-28',
  'customer-detail': 'D4-29',
  'interview-summary': 'D4-30',
  'interview-detail': 'D4-31',
  'interview-template': 'D4-访谈模板',
  'fund-flow': 'D4-32',
  'other-margin': 'D4-33',
  'other-contract': 'D4-34',
  'other-check': 'D4-35',
  'other-cutoff': 'D4-36',
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD4DualMode(options: UseD4DualModeOptions) {
  const { wpId, activeTab, reloadAllResponses } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const currentMode = ref<D4RenderMode>('structured')
  const isOoAvailable = ref<boolean>(false)
  const ooConfig = ref<D4OOConfig | null>(null)
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
        isOoAvailable.value = false
        return false
      }
      const result = await response.json()
      // 兼容 ResponseWrapperMiddleware 信封
      const healthy = result.data?.healthy ?? result.healthy ?? false
      isOoAvailable.value = healthy
      return healthy
    } catch {
      isOoAvailable.value = false
      return false
    } finally {
      checking.value = false
    }
  }

  // ─── Switch Mode ───────────────────────────────────────────────────────

  /**
   * 切换渲染模式
   *
   * - 切OO：获取当前sheet的OO配置，使用SetVisible隐藏非当前sheet
   * - 切HTML：重新加载allResponses确保数据同步
   */
  async function switchMode(target: D4RenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return

    if (target === 'onlyoffice') {
      try {
        const sheetName = getSheetNameFromTab(activeTab?.value || 'adjudication')
        const response = await fetch(
          `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sheetName)}/onlyoffice-config`
        )
        if (response.ok) {
          const result = await response.json()
          ooConfig.value = result.data || result
          currentMode.value = 'onlyoffice'
        }
      } catch {
        // 降级保持结构化模式
        isOoAvailable.value = false
      }
    } else {
      // 切回结构化视图: 重新加载数据（OO 编辑可能通过 callback 已回写）
      currentMode.value = 'structured'
      ooConfig.value = null
      if (reloadAllResponses) {
        await reloadAllResponses()
      }
    }
  }

  // ─── Helpers ───────────────────────────────────────────────────────────

  /**
   * 将 Tab name 映射到 xlsx 中的 sheet name
   */
  function getSheetNameFromTab(tab: string): string {
    return D4_TAB_SHEET_MAP[tab] || 'D4-1'
  }

  /**
   * OO 不可用时的 tooltip 文本
   */
  function getDisabledTooltip(): string {
    if (!isOoAvailable.value) {
      return 'OnlyOffice 服务不可用，仅支持结构化视图'
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
    currentMode,
    isOoAvailable,
    ooConfig,
    checking,

    // 操作
    switchMode,
    checkOOHealth,
    getDisabledTooltip,
    getSheetNameFromTab,
  }
}

export default useD4DualMode
