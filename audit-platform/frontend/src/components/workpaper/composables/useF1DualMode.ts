/**
 * useF1DualMode — F1 预付账款双模式切换（HTML ↔ OnlyOffice）
 *
 * 管理 OO 健康检查 + 模式切换逻辑。
 * OO 模式打开完整 xlsx，通过 SetVisible(false) 隐藏非当前 sheet。
 *
 * Spec: .kiro/specs/f1-prepayment/
 * Task: 28.1
 * Requirements: 16.1-16.5
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import http from '@/utils/http'

export type D3ViewMode = 'structured' | 'onlyoffice'

export interface D3SheetMapping {
  tabName: string
  sheetName: string
}

/** F1 Tab → OO sheet 名称映射 */
const D3_SHEET_MAP: D3SheetMapping[] = [
  { tabName: 'procedure', sheetName: '预付账款审计程序表F1A' },
  { tabName: 'adjudication', sheetName: '预付账款审定表F1-1' },
  { tabName: 'detail', sheetName: '预付账款明细表F1-2' },
  { tabName: 'adjustment', sheetName: '预付账款调整分录汇总F1-3' },
  { tabName: 'analysis', sheetName: '预付账款分析表F1-4' },
  { tabName: 'longterm', sheetName: '账龄1年以上检查表F1-5' },
  { tabName: 'related-party', sheetName: '关联关系及交易检查表F1-6' },
  { tabName: 'comprehensive-check', sheetName: '预付账款检查表F1-7' },
  { tabName: 'disclosure', sheetName: '附注披露信息（上市公司）' },
]

export interface UseD3DualModeOptions {
  wpId: Ref<string>
  activeTab: Ref<string>
}

export function useF1DualMode(options: UseD3DualModeOptions) {
  const { wpId, activeTab } = options

  const currentMode = ref<D3ViewMode>('structured')
  const ooHealthy = ref<boolean | null>(null)
  const ooConfig = ref<any>(null)
  const isCheckingHealth = ref(false)

  const modeOptions = computed(() => [
    { label: '结构化视图', value: 'structured' },
    { label: '在线编辑', value: 'onlyoffice', disabled: !ooHealthy.value },
  ])

  const ooDisabledTooltip = computed(() =>
    ooHealthy.value === false ? 'OnlyOffice服务不可用' : ''
  )

  /** 当前 Tab 对应的 OO sheet 名称 */
  const currentSheetName: ComputedRef<string> = computed(() => {
    const mapping = D3_SHEET_MAP.find(m => m.tabName === activeTab.value)
    return mapping?.sheetName || ''
  })

  /** 检查 OnlyOffice 健康状态 */
  async function checkOOHealth(): Promise<void> {
    if (isCheckingHealth.value) return
    isCheckingHealth.value = true
    try {
      const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
      const data = res.data?.data ?? res.data
      ooHealthy.value = data?.healthy ?? data?.data?.healthy ?? false
    } catch {
      ooHealthy.value = false
    } finally {
      isCheckingHealth.value = false
    }
  }

  /** 切换到 OnlyOffice 模式 */
  async function switchToOO(): Promise<void> {
    if (!ooHealthy.value) return

    const sheetName = currentSheetName.value
    if (!sheetName) return

    try {
      const res = await http.get(
        `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sheetName)}/onlyoffice-config`,
        { _silent: true } as any,
      )
      ooConfig.value = res.data?.data ?? res.data
      currentMode.value = 'onlyoffice'
    } catch {
      currentMode.value = 'structured'
    }
  }

  /** 切换回 HTML 结构化视图 */
  function switchToStructured(): void {
    currentMode.value = 'structured'
    ooConfig.value = null
  }

  /** 模式切换处理器 */
  async function onModeChange(mode: D3ViewMode): Promise<void> {
    if (mode === 'onlyoffice') {
      await switchToOO()
    } else {
      switchToStructured()
    }
  }

  /**
   * OO 文档就绪回调 —— 隐藏非当前 sheet
   * 使用 OO API: spreadsheet.SetVisible(sheetName, false)
   */
  function onDocumentReady(api: any): void {
    if (!api) return
    const targetSheet = currentSheetName.value
    try {
      // 获取所有 sheet 名称并隐藏非当前的
      const sheets = api.GetSheets?.() || []
      for (const sheet of sheets) {
        if (sheet.name !== targetSheet) {
          api.SetVisible?.(sheet.name, false)
        }
      }
      // 激活当前 sheet
      if (targetSheet) {
        api.SetActiveSheet?.(targetSheet)
      }
    } catch (e) {
      console.warn('[F1 DualMode] onDocumentReady hide sheets failed:', e)
    }
  }

  return {
    currentMode,
    modeOptions,
    ooHealthy,
    ooConfig,
    ooDisabledTooltip,
    currentSheetName,
    isCheckingHealth,
    checkOOHealth,
    switchToOO,
    switchToStructured,
    onModeChange,
    onDocumentReady,
  }
}

export default useF1DualMode
